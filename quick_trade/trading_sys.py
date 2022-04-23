# !/usr/bin/python
# -*- coding: utf-8 -*-
# used ta by Darío López Padial (Bukosabino https://github.com/bukosabino/ta)

# TODO:
#   scalper and dca bot
#   more docs and examples
#   decimal
#   add meta-data in tuner's returns
#   add "tradingview backtest"
#   multi-timeframe backtest
#   telegram bot
#   https://smart-lab.ru/company/www-marketstat-ru/blog/502764.php
#   SOLID, DRY
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from re import fullmatch
from threading import Thread
from time import ctime, sleep, time
from typing import Any, Union, List, Iterable, Tuple, Dict
from warnings import warn

import numpy as np
import pandas as pd
import ta.momentum
import ta.trend
import ta.volatility

from . import indicators
from . import utils
from .brokers import TradingClient
from .plots import TraderGraph
from . import strategy


class Trader(object):
    _profit_calculate_coef: Union[float, int]
    returns: utils.PREDICT_TYPE_LIST = []
    _df: pd.DataFrame
    ticker: str
    interval: str
    _prev_predict: str = 'Exit'
    _stop_loss: Union[float, int]
    _take_profit: Union[float, int]
    _open_price: float
    trades: int = 0
    profits: int = 0
    losses: int = 0
    stop_losses: List[float] = []
    take_profits: List[float] = []
    credit_leverages: List[Union[float, int]] = []
    deposit_history: List[Union[float, int]] = []
    year_profit: float
    _info: str
    backtest_out: pd.DataFrame
    open_lot_prices: List[float] = []
    client: TradingClient
    __last_stop_loss: float
    __last_take_profit: float
    _sec_interval: int
    supports: Dict[int, float]
    resistances: Dict[int, float]
    fig: TraderGraph
    _multi_converted_: bool = False
    _entry_start_trade: bool
    average_growth: Union[np.ndarray, List]
    _converted: utils.CONVERTED_TYPE_LIST
    mean_deviation: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float
    net_returns: pd.Series
    profit_deviation_ratio: float
    _registered_strategy: str

    def returns_update(self):
        self._converted = utils.convert(self.returns)

    def deposit_history_update(self):
        all_characteristics = utils.strategy_characteristics(equity=self.deposit_history,
                                                             trades=self.trades,
                                                             profit_trades=self.profits,
                                                             timeframe=self.interval)
        self.average_growth = utils.get_exponential_growth(self.deposit_history)
        for name, param in {**utils.TUNER_CODECONF,
                            **utils.ADDITIONAL_TRADER_ATTRIBUTES}.items():
            setattr(self, param, all_characteristics[name])

    @property
    def df(self) -> pd.DataFrame:
        return self._df

    @df.setter
    def df(self, frame: pd.DataFrame):
        self._df = frame

    @property
    def _info(self):
        return utils.INFO_TEXT.format(self.losses,
                                      self.trades,
                                      self.profits,
                                      self.year_profit,
                                      self.winrate,
                                      self.mean_deviation,
                                      self.sharpe_ratio,
                                      self.sortino_ratio,
                                      self.calmar_ratio,
                                      self.max_drawdown,
                                      self.profit_deviation_ratio)

    def __init__(self,
                 ticker: str = 'BTC/USDT',
                 df: pd.DataFrame = pd.DataFrame(),
                 interval: str = '1d'):
        ticker = ticker.upper()
        assert isinstance(ticker, str), 'The ticker can only be of type <str>.'
        assert fullmatch(utils.TICKER_PATTERN, ticker), f'Ticker must match the pattern <{utils.TICKER_PATTERN}>'
        assert isinstance(df, pd.DataFrame), 'Dataframe can only be of type <DataFrame>.'
        assert isinstance(interval, str), 'interval can only be of the <str> type.'

        self.df = df.reset_index(drop=True)
        self.ticker = ticker
        self.interval = interval
        self._profit_calculate_coef, self._sec_interval = utils.get_coef_sec(interval)

    def __repr__(self):
        return f'{self.ticker} {self.interval} trader'

    def _get_attr(self, attr: str):
        return getattr(self, attr)

    @classmethod
    def _get_this_instance(cls, *args, **kwargs):
        return cls(*args, **kwargs)

    def __get_stop_take(self, sig: utils.PREDICT_TYPE) -> Dict[str, float]:
        """
        calculating stop loss and take profit.
        sig:        |     PREDICT_TYPE     |  signal to sell/buy/exit:
            EXIT -- exit.
            BUY -- buy.
            SELL -- sell.
        """

        _stop_loss: float
        take: float
        if self._stop_loss is not np.inf:
            _stop_loss = self._stop_loss / 10_000 * self._open_price
        else:
            _stop_loss = np.inf
        if self._take_profit is not np.inf:
            take = self._take_profit / 10_000 * self._open_price
        else:
            take = np.inf

        if sig == utils.BUY:
            _stop_loss = self._open_price - _stop_loss
            take = self._open_price + take
        elif sig == utils.SELL:
            take = self._open_price - take
            _stop_loss = self._open_price + _stop_loss
        else:
            if self._take_profit is not np.inf:
                take = self._open_price
            if self._stop_loss is not np.inf:
                _stop_loss = self._open_price

        return {'stop': _stop_loss,
                'take': take}

    def sl_tp_adder(self,
                    add_stop_loss: Union[float, int] = 0.0,
                    add_take_profit: Union[float, int] = 0.0) -> Tuple[List[float], List[float]]:
        """

        :param add_stop_loss: add stop loss points
        :param add_take_profit: add take profit points
        :return: (stop losses, take profits)
        """
        assert isinstance(add_stop_loss, (int, float)) and isinstance(add_take_profit, (int, float)), \
            'Arguments to this function can only be <float> or <int>.'

        stop_losses = []
        take_profits = []
        for stop_loss_price, take_profit_price, price, sig in zip(self.stop_losses,
                                                                  self.take_profits,
                                                                  self.open_lot_prices,
                                                                  self.returns):
            add_sl = (price / 10_000) * add_stop_loss
            add_tp = (price / 10_000) * add_take_profit

            if sig == utils.BUY:
                stop_losses.append(stop_loss_price - add_sl)
                take_profits.append(take_profit_price + add_tp)
            elif sig == utils.SELL:
                stop_losses.append(stop_loss_price + add_sl)
                take_profits.append(take_profit_price - add_tp)
            else:
                stop_losses.append(stop_loss_price)
                take_profits.append(take_profit_price)

        self.stop_losses = stop_losses
        self.take_profits = take_profits
        return self.stop_losses, self.take_profits

    def multi_trades(self):
        self.returns, self.credit_leverages = utils.make_multi_trade_returns(self.returns)
        self._multi_converted_ = True

    def get_heikin_ashi(self, df: pd.DataFrame = pd.DataFrame()) -> pd.DataFrame:
        """
        :param df: dataframe, default: self.df
        :return: heikin ashi
        """
        if 'Close' not in df.columns:
            df: pd.DataFrame = self.df.copy()
        df['HA_Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
        df['HA_Open'] = (df['Open'].shift(1) + df['Open'].shift(1)) / 2
        df.iloc[0, df.columns.get_loc("HA_Open")] = (df.iloc[0]['Open'] + df.iloc[0]['Close']) / 2
        df['HA_High'] = df[['High', 'Low', 'HA_Open', 'HA_Close']].max(axis=1)
        df['HA_Low'] = df[['High', 'Low', 'HA_Open', 'HA_Close']].min(axis=1)
        df = df.drop(['Open', 'High', 'Low', 'Close'], axis=1)
        df = df.rename(
            columns={"HA_Open": "Open",
                     "HA_High": "High",
                     "HA_Low": "Low",
                     "HA_Close": "Close"})

        return df

    def crossover(self, fast: Iterable, slow: Iterable):
        assert isinstance(fast, Iterable) and isinstance(slow, Iterable), \
            'The arguments to this function must be iterable.'

        self.returns = []
        for s, f in zip(slow, fast):
            if s < f:
                self.returns.append(utils.BUY)
            elif s > f:
                self.returns.append(utils.SELL)
            else:
                self.returns.append(utils.EXIT)
        self.set_credit_leverages()
        self.set_open_stop_and_take()
        return self.returns

    def inverse_strategy(self, swap_stop_take: bool = True) -> utils.PREDICT_TYPE_LIST:
        """
        makes signals inverse:
        buy = sell.
        sell = buy.
        exit = exit.
        """
        assert isinstance(swap_stop_take, bool), 'swap_stop_take can only be <bool>'

        returns = []
        flag: utils.PREDICT_TYPE = utils.EXIT
        for signal_key in self.returns:
            if signal_key == utils.BUY:
                flag = utils.SELL
            elif signal_key == utils.SELL:
                flag = utils.BUY
            elif signal_key == utils.EXIT:
                flag = utils.EXIT
            returns.append(flag)
        self.returns = returns
        self.returns_update()
        if swap_stop_take:
            self.stop_losses, self.take_profits = self.take_profits, self.stop_losses
        return self.returns

    def backtest(self,
                 deposit: Union[float, int] = 10_000.0,
                 bet: Union[float, int] = np.inf,
                 commission: Union[float, int] = 0.0,
                 plot: bool = True,
                 print_out: bool = True,
                 show: bool = True) -> pd.DataFrame:
        """
        testing the strategy.
        :param deposit: start deposit.
        :param bet: fixed bet to quick_trade. np.inf = all moneys.
        :param commission: percentage commission (0 -- 100).
        :param plot: plotting.
        :param print_out: printing.
        :param show: show the graph
        returns: pd.DataFrame with data of test
        """
        assert isinstance(deposit, (float, int)), 'deposit must be of type <int> or <float>'
        assert deposit > 0, 'deposit can\'t be 0 or less'
        assert isinstance(bet, (float, int)), 'bet must be of type <int> or <float>'
        assert bet > 0, 'bet can\'t be 0 or less'
        assert isinstance(commission, (float, int)), 'commission must be of type <int> or <float>'
        assert 0 <= commission < 100, 'commission cannot be >=100% or less then 0'
        assert isinstance(plot, bool), 'plot must be of type <bool>'
        assert isinstance(print_out, bool), 'print_out must be of type <bool>'
        assert isinstance(show, bool), 'show must be of type <bool>'

        self.returns_update()
        pass_math: bool = False
        data_column: pd.Series = self.df['Close']
        exit_take_stop: bool
        no_order: bool
        stop_loss: float
        take_profit: float
        converted_element: utils.CONVERTED_TYPE
        diff: float
        lin_calc_df: pd.DataFrame
        high: float
        low: float
        credit_lev: Union[float, int]

        start_bet: Union[float, int] = bet
        data_high: pd.Series = self.df['High']
        data_low: pd.Series = self.df['Low']
        self.deposit_history = [deposit]
        self.trades = 0
        self.profits = 0
        self.losses = 0
        moneys_open_bet: Union[float, int] = deposit
        money_start: Union[float, int] = deposit
        prev_sig = utils.EXIT

        ignore_breakout: bool = False
        next_not_breakout: bool
        e: int
        sig: utils.PREDICT_TYPE
        stop_loss: float
        take_profit: float
        converted_element: utils.CONVERTED_TYPE
        credit_lev: Union[float, int]
        high: float
        low: float
        next_h: float
        next_l: float
        normal: bool
        for e, (sig,
                stop_loss,
                take_profit,
                converted_element,
                credit_lev,
                high,
                low,
                next_h,
                next_l) in enumerate(zip(self.returns[:-1],
                                         self.stop_losses[:-1],
                                         self.take_profits[:-1],
                                         self._converted[:-1],
                                         self.credit_leverages[:-1],
                                         data_high[:-1],
                                         data_low[:-1],
                                         data_high[1:],
                                         data_low[1:])):

            if not np.isnan(converted_element):
                # count the number of profitable and unprofitable trades.
                if prev_sig != utils.EXIT:
                    self.trades += 1
                    if deposit > moneys_open_bet:
                        self.profits += 1
                    elif deposit < moneys_open_bet:
                        self.losses += 1

                # calculating commission
                if prev_sig != utils.EXIT:
                    commission_reuse = 2
                else:
                    commission_reuse = 1
                bet = start_bet
                if bet > deposit:
                    bet = deposit
                for i in range(commission_reuse):
                    deposit -= bet * (commission / 100) * credit_lev
                    if bet > deposit:
                        bet = deposit

                # reset service variables
                open_price = data_column[e]
                moneys_open_bet = deposit
                no_order = False
                exit_take_stop = False
                ignore_breakout = True

                if sig != utils.EXIT and not min(stop_loss, take_profit) <= open_price <= max(stop_loss, take_profit) and e > 0:
                    pass_math = True
                    break

            if sig != utils.EXIT:
                next_not_breakout = min(stop_loss, take_profit) < next_l <= next_h < max(stop_loss, take_profit)

                stop_loss = self.stop_losses[e - 1]
                take_profit = self.take_profits[e - 1]
                # be careful with e=0
                # haha))) no)
                now_not_breakout = min(stop_loss, take_profit) < low <= high < max(stop_loss, take_profit)

                normal = ignore_breakout or (now_not_breakout and next_not_breakout)

                if credit_lev != self.credit_leverages[e - 1] and not ignore_breakout:
                    deposit -= bet * (commission / 100) * abs(self.credit_leverages[e - 1] - credit_lev)
                    # Commission when changing the leverage.
                    if bet > deposit:
                        bet = deposit

                    if self._multi_converted_:
                        if prev_sig != utils.EXIT:
                            self.trades += 1
                            if deposit > moneys_open_bet:
                                self.profits += 1
                            elif deposit < moneys_open_bet:
                                self.losses += 1
                        moneys_open_bet = deposit

                if normal:
                    diff = data_column[e + 1] - data_column[e]
                else:
                    # Here I am using the previous value,
                    # because we do not know the value at this point
                    # (it is generated only when the candle is closed).
                    exit_take_stop = True

                    if (not now_not_breakout) and not ignore_breakout:
                        stop_loss = self.stop_losses[e - 1]
                        take_profit = self.take_profits[e - 1]
                        diff = utils.get_diff(price=data_column[e],
                                              low=low,
                                              high=high,
                                              stop_loss=stop_loss,
                                              take_profit=take_profit,
                                              signal=sig)

                    elif not next_not_breakout:
                        stop_loss = self.stop_losses[e]
                        take_profit = self.take_profits[e]
                        diff = utils.get_diff(price=data_column[e],
                                              low=next_l,
                                              high=next_h,
                                              stop_loss=stop_loss,
                                              take_profit=take_profit,
                                              signal=sig)
            else:
                diff = 0.0
            if sig == utils.SELL:
                diff = -diff
            if moneys_open_bet < 0:
                diff = -diff
            if not no_order:
                deposit += bet * credit_lev * diff / open_price
            self.deposit_history.append(deposit)

            no_order = exit_take_stop
            if self.returns[e + 1] != sig:
                prev_sig = sig
            ignore_breakout = False

        self.deposit_history_update()

        if pass_math:
            warn('The deal was opened out of range!')
            self.winrate = 0.0
            self.year_profit = 0.0
            self.losses = 0
            self.profits = 0
            self.trades = 0

        if print_out:
            print(self._info)
        self.backtest_out = pd.DataFrame(
            (self.deposit_history, self.stop_losses, self.take_profits, self.returns,
             self.open_lot_prices, data_column, self.average_growth, self.net_returns),
            index=[
                'deposit', 'stop loss', 'take profit',
                'predictions', 'open trade', 'Close',
                "average growth deposit data",
                "returns"
            ]).T
        if plot:
            self.fig.plot_candlestick()
            self.fig.plot_trade_triangles()
            self.fig.plot_SL_TP_OPN()

            self.fig.plot_deposit()

            self.fig.plot_returns()
        if show:
            self.fig.show()

        self._multi_converted_ = False
        return self.backtest_out

    def multi_backtest(self,
                       test_config: Dict[str, List[Dict[str, Dict[str, Any]]]],
                       limit: int = 1000,
                       deposit: Union[float, int] = 10_000.0,
                       bet: Union[float, int] = np.inf,
                       commission: Union[float, int] = 0.0,
                       plot: bool = True,
                       print_out: bool = True,
                       show: bool = True,
                       _dataframes: Dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
        for el in test_config.keys():
            assert isinstance(el, str), 'tickers must be of type <Iterable[str]>'
            assert fullmatch(utils.TICKER_PATTERN, el), f'all tickers must match the pattern <{utils.TICKER_PATTERN}>'
        for k1 in test_config.values():
            for k in k1:
                for strategy_name in k.keys():
                    assert isinstance(strategy_name, str), 'strategy parameter must be of type <str>'
                    assert strategy_name in self.__dir__(), 'There is no such strategy'
        assert isinstance(limit, int), 'limit must be of type <int>'
        assert limit > 0, 'limit can\'t be 0 or less'
        assert isinstance(deposit, (float, int)), 'deposit must be of type <int> or <float>'
        assert deposit > 0, 'deposit can\'t be 0 or less'
        assert isinstance(bet, (float, int)), 'bet must be of type <int> or <float>'
        assert bet > 0, 'bet can\'t be 0 or less'
        assert isinstance(commission, (float, int)), 'commission must be of type <int> or <float>'
        assert 0 <= commission < 100, 'commission cannot be >=100% or less then 0'
        assert isinstance(plot, bool), 'plot must be of type <bool>'
        assert isinstance(print_out, bool), 'print_out must be of type <bool>'
        assert isinstance(show, bool), 'show must be of type <bool>'

        winrates: List[float] = []
        losses: List[int] = []
        trades: List[int] = []
        profits: List[int] = []
        depos: List[pd.Series] = []
        lens_dep: List[int] = []
        self.deposit_history = []

        for ticker, strat_l in test_config.items():
            for strat in strat_l:
                for strategy_kwargs in strat.items():
                    if _dataframes is None:
                        df = self.client.get_data_historical(ticker=ticker, limit=limit, interval=self.interval)
                    else:
                        df = _dataframes[ticker]
                    new_trader = self._get_this_instance(interval=self.interval, df=df, ticker=ticker)
                    new_trader.set_client(client=self.client)
                    try:
                        new_trader.connect_graph(deepcopy(self.fig))
                    except Exception as e:
                        if isinstance(e, KeyboardInterrupt):
                            raise e
                        pass
                    new_trader._get_attr(strategy_kwargs[0])(**strategy_kwargs[1])
                    new_trader.backtest(deposit=deposit / len(test_config.keys()),
                                        bet=bet,
                                        commission=commission,
                                        plot=False,
                                        print_out=False,
                                        show=False)
                    winrates.append(new_trader.winrate)
                    losses.append(new_trader.losses)
                    trades.append(new_trader.trades)
                    profits.append(new_trader.profits)
                    depos.append(pd.Series(new_trader.deposit_history))
                    lens_dep.append(len(new_trader.deposit_history))
        self._registered_strategy = str(test_config)
        self.losses = sum(losses)
        self.trades = sum(trades)  # all time
        self.profits = sum(profits)
        self.winrate = float(np.mean(winrates))

        for enum, elem in enumerate(depos):
            depos[enum] = utils.get_multipliers(
                pd.Series(elem[-min(lens_dep):])
            )

        multipliers: pd.Series = sum(depos) / len(depos)
        multipliers[0] = deposit
        self.deposit_history = list(np.cumprod(multipliers.values))
        self.deposit_history_update()
        self.backtest_out = pd.DataFrame(
            (self.deposit_history, self.average_growth, self.net_returns),
            index=[
                'deposit',
                "average growth deposit data",
                "returns",
            ]).T

        if print_out:
            print(self._info)
        if plot:
            self.fig.plot_deposit()
            self.fig.plot_returns()
        if show:
            self.fig.show()
        return self.backtest_out

    def connect_graph(self,
                      graph: TraderGraph | None = None):
        """
        connect TraderGraph
        """

        if graph is None:
            graph = TraderGraph()

        self.fig = graph
        self.fig.connect_trader(self)

    def strategy_collider(self,
                          first_returns: utils.PREDICT_TYPE_LIST,
                          second_returns: utils.PREDICT_TYPE_LIST,
                          mode: str = 'minimalist') -> utils.PREDICT_TYPE_LIST:
        """
        :param second_returns: returns of strategy
        :param first_returns: returns of strategy
        :param mode:  mode of combining:

            example :
                mode = 'minimalist':
                    1,1 = 1

                    0,0 = 0

                    2,2 = 2

                    0,1 = 2

                    1,0 = 2

                    2,1 = 2

                    1,2 = 2

                    ...

                    first_returns = [1,1,0,0,2,0,2,2,0,0,1]

                    second_returns = [1,2,2,2,2,2,0,0,0,0,1]

                        [1,2,2,2,2,2,2,2,0,0,1]

                mode = 'maximalist':
                    1,1 = 1

                    0,0 = 0

                    2,2 = 2

                    0,1 = last sig

                    1,0 = last sig

                    2,1 = last sig

                    1,2 = last sig

                    ...

                    first_returns =  [1,1,0,0,2,0,2,2,0,0,1]

                    second_returns = [1,2,2,2,2,2,0,0,0,0,1]

                        [1,1,1,1,2,2,2,2,0,0,1]

                mode = 'super':
                    ...

                    first_returns =  [1,1,1,2,2,2,0,0,1]

                    second_returns = [1,0,0,0,1,1,1,0,0]

                        [1,0,0,2,1,1,0,0,1]

        :return: combining of 2 strategies
        """

        if mode == 'minimalist':
            self.returns = []
            for ret1, ret2 in zip(first_returns, second_returns):
                if ret1 == ret2:
                    self.returns.append(ret1)
                else:
                    self.returns.append(utils.EXIT)
        elif mode == 'maximalist':
            self.returns = self._maximalist(first_returns, second_returns)
        elif mode == 'super':
            self.returns = self._collide_super(first_returns, second_returns)
        else:
            raise ValueError(f'incorrect mode: {mode}')
        return self.returns

    @staticmethod
    def _maximalist(returns1: utils.PREDICT_TYPE_LIST,
                    returns2: utils.PREDICT_TYPE_LIST) -> utils.PREDICT_TYPE_LIST:
        return_list: utils.PREDICT_TYPE_LIST = []
        flag = utils.EXIT
        for a, b in zip(returns1, returns2):
            if a == b:
                return_list.append(a)
                flag = a
            else:
                return_list.append(flag)
        return return_list

    @staticmethod
    def _collide_super(l1: utils.PREDICT_TYPE_LIST,
                       l2: utils.PREDICT_TYPE_LIST) -> utils.PREDICT_TYPE_LIST:
        return_list: utils.PREDICT_TYPE_LIST = []
        for first, sec in zip(utils.convert(l1), utils.convert(l2)):
            if ((not np.isnan(first)) and
                    (not np.isnan(sec))
                    and first is not sec):
                return_list.append(utils.EXIT)
            elif first is sec:
                return_list.append(first)
            elif np.isnan(first):
                return_list.append(sec)
            else:
                return_list.append(first)
        return list(map(lambda x: utils.PREDICT_TYPE(x),
                        utils.anti_convert(return_list)))

    def multi_strategy_collider(self,
                                *strategies,
                                mode: str = 'minimalist') -> utils.PREDICT_TYPE_LIST:
        self.strategy_collider(strategies[0], strategies[1], mode=mode)
        if len(strategies) >= 3:
            for ret in strategies[2:]:
                self.strategy_collider(self.returns, ret, mode=mode)
        return self.returns

    def get_trading_predict(self,
                            bet_for_trading_on_client: Union[float, int] = np.inf,
                            ) -> Dict[str, Union[str, float]]:
        """
        predict and trading.

        :param bet_for_trading_on_client: standard: all deposit
        :return: dict with prediction
        """

        moneys: float
        bet: Union[float, int]
        close: np.ndarray = self.df["Close"].values
        open_new_order: bool

        # getting prediction
        predict: str = utils.convert_signal_str(self.returns[-1])

        # trading
        self.__last_stop_loss = self.stop_losses[-1]
        self.__last_take_profit = self.take_profits[-1]

        conv_cred_lev = utils.convert(self.credit_leverages)

        if self._entry_start_trade:
            open_new_order = predict != self._prev_predict or not np.isnan(conv_cred_lev[-1])
        else:
            open_new_order = (not np.isnan(self._converted[-1])) or (not np.isnan(conv_cred_lev[-1]))

        if open_new_order:
            if self.client.trading:
                with utils.locker:
                    if predict == 'Exit':
                        self.client.exit_last_order()

                    else:
                        self.client.exit_last_order()  # exit from previous trade (signal)

                        moneys = self.client.get_balance(
                            self.ticker.split('/')[1]
                        )
                        ticker_price = self.client.get_ticker_price(self.ticker)
                        if bet_for_trading_on_client is not np.inf:
                            bet = bet_for_trading_on_client
                        else:
                            bet = moneys
                        if bet > moneys:
                            bet = moneys
                        bet /= ticker_price
                        bet *= utils.RESERVE

                        self.client.order_create(predict,
                                                 self.ticker,
                                                 bet * self.credit_leverages[-1])  # entry new position
        return {
            'predict': predict,
            'open trade price': self._open_price,
            'stop loss': self.__last_stop_loss,
            'take profit': self.__last_take_profit,
            'close price': close[-1],
            'credit leverage': self.credit_leverages[-1]
        }

    def realtime_trading(self,
                         strategy,
                         start_time: datetime,
                         ticker: str = 'BTC/USDT',
                         print_out: bool = True,
                         bet_for_trading_on_client: Union[float, int] = np.inf,
                         wait_sl_tp_checking: Union[float, int] = 5,
                         limit: int = 1000,
                         strategy_in_sleep: bool = False,
                         entry_start_trade: bool = False,
                         *strategy_args,
                         **strategy_kwargs):
        """
        :param entry_start_trade: Entering a trade at the first new candlestick. If False - enter when a new signal appears.
        :param start_time: time to start
        :param strategy_in_sleep: reuse strategy in one candle for new S/L, T/P or leverage
        :param limit: client.get_data_historical's limit argument
        :param wait_sl_tp_checking: sleeping time after stop-loss and take-profit checking (seconds)
        :param ticker: ticker for trading.
        :param strategy: trading strategy.
        :param print_out: printing.
        :param bet_for_trading_on_client: trading bet, standard: all deposit
        :param strategy_kwargs: named arguments to -strategy.
        :param strategy_args: arguments to -strategy.
        """
        assert fullmatch(utils.TICKER_PATTERN, ticker), f'ticker must match the pattern <{utils.TICKER_PATTERN}>'
        assert isinstance(print_out, bool), 'print_out must be of type <bool>'
        assert isinstance(bet_for_trading_on_client,
                          (float, int)), 'bet_for_trading_on_client must be of type <float> or <int>'
        assert isinstance(wait_sl_tp_checking, (float, int)), 'wait_sl_tp_checking must be of type <float> or <int>'
        assert wait_sl_tp_checking < self._sec_interval, \
            'wait_sl_tp_checking cannot be greater than or equal to the timeframe'
        assert isinstance(limit, int), 'limit must be of type <int>'
        assert isinstance(strategy_in_sleep, bool), 'strategy_in_sleep must be of type <bool>'
        assert isinstance(entry_start_trade, bool), 'entry_start_trade must be of type <bool>'

        self.ticker = ticker
        self._entry_start_trade = entry_start_trade
        while True:
            if datetime.now() >= start_time:
                break
        open_time = time()
        while True:
            self.df = self.client.get_data_historical(ticker=self.ticker, limit=limit, interval=self.interval)

            strategy(*strategy_args, **strategy_kwargs)

            prediction = self.get_trading_predict(
                bet_for_trading_on_client=bet_for_trading_on_client)

            index = f'{self.ticker}, {ctime()}'
            if print_out:
                print(index, prediction)
            while True:
                if self.client.ordered and time() + wait_sl_tp_checking <= open_time + self._sec_interval:
                    sleep(wait_sl_tp_checking)
                    with utils.locker:
                        price = self.client.get_ticker_price(ticker)
                        min_ = min(self.__last_stop_loss, self.__last_take_profit)
                        max_ = max(self.__last_stop_loss, self.__last_take_profit)
                        if (not (min_ < price < max_)) and prediction["predict"] != 'Exit':
                            index = f'{self.ticker}, {ctime()}'
                            if print_out:
                                print("(%s) trading prediction exit in sleeping at %s: %s" % (self, index, prediction))
                            if self.client.trading:
                                self.client.exit_last_order()
                if time() >= (open_time + self._sec_interval):
                    self._prev_predict = utils.convert_signal_str(self.returns[-1])
                    open_time += self._sec_interval
                    break
                elif strategy_in_sleep:
                    break

    def multi_realtime_trading(self,
                               trade_config: Dict[str, List[Dict[str, Dict[str, Any]]]],
                               start_time: datetime,  # LOCAL TIME
                               print_out: bool = True,
                               bet_for_trading_on_client: Union[float, int] = np.inf,  # for 1 trade
                               wait_sl_tp_checking: Union[float, int] = 5,
                               limit: int = 1000,
                               strategy_in_sleep: bool = False,
                               deposit_part: Union[float, int] = 1.0,  # for all trades,
                               entry_start_trade: bool = False):
        """

        :param trade_config: Configurations to start trading. {ticker: [{strategy: {parameter: value}}]}
        """
        tickers: List[str] = list(trade_config.keys())
        for el in tickers:
            assert isinstance(el, str), 'tickers must be of type <Iterable[str]>'
            assert fullmatch(utils.TICKER_PATTERN, el), f'all tickers must match the pattern <{utils.TICKER_PATTERN}>'
        assert isinstance(print_out, bool), 'print_out must be of type <bool>'
        assert isinstance(bet_for_trading_on_client,
                          (float, int)), 'bet_for_trading_on_client must be of type <float> or <int>'
        assert isinstance(wait_sl_tp_checking, (float, int)), 'wait_sl_tp_checking must be of type <float> or <int>'
        assert wait_sl_tp_checking < self._sec_interval, \
            'wait_sl_tp_checking cannot be greater than or equal to the timeframe'
        assert isinstance(limit, int), 'limit must be of type <int>'
        assert isinstance(strategy_in_sleep, bool), 'strategy_in_sleep must be of type <bool>'
        assert isinstance(start_time, datetime), 'start_time must be of type <datetime.datetime>'
        assert start_time > datetime.now(), 'start_time cannot be earlier than the present time'
        for k1 in trade_config.values():
            for k in k1:
                for strat_name in k.keys():
                    assert isinstance(strat_name, str), 'strategy parameter must be of type <str>'
                    assert strat_name in self.__dir__(), 'There is no such strategy'
        assert isinstance(deposit_part, (int, float)), 'deposit_part must be of type <int> or <float>'
        assert 1 >= deposit_part > 0, 'deposit_part cannot be greater than 1 or less than 0(inclusively)'

        can_orders: int = sum([len(x) for x in trade_config.values()])
        bet_for_trading_on_client_copy: Union[float, int] = bet_for_trading_on_client
        client = self.client

        class MultiRealTimeTrader(self.__class__):
            def get_trading_predict(self,
                                    bet_for_trading_on_client: Union[float, int] = np.inf,
                                    ) -> Dict[str, Union[str, float]]:
                with utils.locker:
                    balance = self.client.get_balance(
                        self.ticker.split('/')[1]
                    )
                    bet = bet_for_trading_on_client_copy
                    if bet_for_trading_on_client is np.inf:
                        if TradingClient.cls_open_orders != can_orders:
                            bet = (balance * 10) / (can_orders / deposit_part - TradingClient.cls_open_orders)
                            bet /= 10  # decimal analog
                            self.__prev_bet = bet
                        else:
                            bet = self.__prev_bet
                return super().get_trading_predict(bet_for_trading_on_client=bet)

        def start_trading(pair, strat):
            trader = MultiRealTimeTrader(ticker=pair,
                                         interval=self.interval)
            trader.connect_graph(graph=deepcopy(self.fig))
            trader.set_client(deepcopy(client))

            items = tuple(strat.items())
            item = items[0]

            trader.realtime_trading(strategy=trader._get_attr(item[0]),
                                    start_time=start_time,
                                    ticker=pair,
                                    print_out=print_out,
                                    wait_sl_tp_checking=wait_sl_tp_checking,
                                    limit=limit,
                                    strategy_in_sleep=strategy_in_sleep,
                                    entry_start_trade=entry_start_trade,
                                    **item[1])

        for ticker, strats in trade_config.items():
            for strat in strats:
                thread = Thread(target=start_trading, args=(ticker, strat))
                thread.start()

    def log_data(self):
        self.fig.log_y(_row=self.fig.data_row,
                       _col=self.fig.data_col)

    def log_deposit(self):
        self.fig.log_y(_row=self.fig.deposit_row,
                       _col=self.fig.deposit_col)

    def log_returns(self):
        self.fig.log_y(_row=self.fig.returns_row,
                       _col=self.fig.returns_col)

    def set_client(self, client: TradingClient):
        """
        :param client: trading client
        """
        assert isinstance(client, TradingClient), 'client must be of type <TradingClient>'

        self.client = client

    def convert_signal(self,
                       old: utils.PREDICT_TYPE = utils.SELL,
                       new: utils.PREDICT_TYPE = utils.EXIT) -> utils.PREDICT_TYPE_LIST:
        assert isinstance(old, utils.PREDICT_TYPE) and isinstance(new, utils.PREDICT_TYPE), \
            'Arguments to this function can only be <utils.PREDICT_TYPE>.'

        pos: int
        val: utils.PREDICT_TYPE
        for pos, val in enumerate(self.returns):
            if val == old:
                self.returns[pos] = new
        return self.returns

    def set_open_stop_and_take(self,
                               take_profit: Union[float, int] = np.inf,
                               stop_loss: Union[float, int] = np.inf,
                               set_stop: bool = True,
                               set_take: bool = True):
        """
        :param set_take: create new take profits.
        :param set_stop: create new stop losses.
        :param take_profit: take profit in points
        :param stop_loss: stop loss in points
        """
        assert isinstance(take_profit, (float, int)), 'take_profit must be of type <float> or <int>'
        assert isinstance(stop_loss, (float, int)), 'stop_loss must be of type <float> or <int>'
        assert isinstance(set_stop, bool), 'set_stop must be of type <bool>'
        assert isinstance(set_take, bool), 'set_stop must be of type <bool>'

        self.returns_update()
        self._take_profit = take_profit
        self._stop_loss = stop_loss
        take_flag: float = np.inf
        stop_flag: float = np.inf
        self.open_lot_prices = []
        if set_stop:
            self.stop_losses = []
        if set_take:
            self.take_profits = []
        closes: np.ndarray = self.df['Close'].values
        sig: utils.PREDICT_TYPE
        close: float
        converted: utils.CONVERTED_TYPE
        ts: Dict[str, float]
        for e, (sig, close, converted) in enumerate(zip(self.returns, closes, self._converted)):
            if not np.isnan(converted):
                self._open_price = close
                if sig != utils.EXIT:
                    if set_take or set_stop:
                        ts = self.__get_stop_take(sig)
                    if set_take:
                        take_flag = ts['take']
                    if set_stop:
                        stop_flag = ts['stop']
                else:
                    take_flag = stop_flag = self._open_price

            self.open_lot_prices.append(self._open_price)
            if set_take:
                self.take_profits.append(take_flag)
            if set_stop:
                self.stop_losses.append(stop_flag)

    def set_credit_leverages(self, credit_lev: Union[float, int] = 1.0):
        """
        Sets the leverage for bets.
        :param credit_lev: leverage in points
        """
        assert isinstance(credit_lev, (float, int)), 'credit_lev must be of type <float> or <int>'

        self.credit_leverages = [credit_lev for i in range(len(self.df['Close']))]

    def get_support_resistance(self) -> Dict[str, Dict[int, float]]:
        lows = self.df['Low'].values
        highs = self.df['High'].values
        for i in range(2, len(lows) - 2):
            if lows[i - 2] >= lows[i - 1] >= lows[i] <= lows[i + 1] <= lows[i + 2]:
                self.supports[i] = lows[i]
            if highs[i - 2] <= highs[i - 1] <= highs[i] >= highs[i + 1] >= highs[i + 2]:
                self.resistances[i] = highs[i]
        return {'resistance': self.resistances,
                'supports': self.supports}

    def strategy_diff(self, frame_to_diff: pd.Series) -> utils.PREDICT_TYPE_LIST:
        """
        frame_to_diff:  |   pd.pd.Series  |  example:  Trader.df['Close']
        """
        assert isinstance(frame_to_diff, pd.Series), 'frame_to_diff must be of type <pd.pd.Series>'

        self.returns = list(np.digitize(frame_to_diff.diff(), bins=[0]))
        self.convert_signal(1, utils.BUY)
        self.convert_signal(0, utils.SELL)
        self.set_open_stop_and_take()
        self.set_credit_leverages()
        return self.returns

    def correct_sl_tp(self,
                      sl_correction: Union[float, int] = 50,
                      tp_correction: Union[float, int] = 50):
        stop_losses_before = self.stop_losses
        take_profits_before = self.take_profits
        for e, (sl, tp, p, sig, conv) in enumerate(zip(stop_losses_before, take_profits_before, self.df['Close'], self.returns, self._converted)):
            if sig == utils.SELL:
                if not np.isnan(conv):
                    correct_sl = p * (1 + sl_correction / 10_000)
                    correct_tp = p * (1 - tp_correction / 10_000)
                    correct_sl_use = False
                    correct_tp_use = False

                if p < sl:
                    correct_sl_use = True
                if p > tp:
                    correct_tp_use = True

                if correct_sl_use:
                    self.stop_losses[e] = sl
                else:
                    self.stop_losses[e] = correct_sl
            elif sig == utils.BUY:
                if not np.isnan(conv):
                    correct_sl = p * (1 - sl_correction / 10_000)
                    correct_tp = p * (1 + tp_correction / 10_000)
                    correct_sl_use = False
                    correct_tp_use = False

                if p > sl:
                    correct_sl_use = True
                if p < tp:
                    correct_tp_use = True

                if correct_sl_use:
                    self.stop_losses[e] = sl
                else:
                    self.stop_losses[e] = correct_sl

    def trailing_stop(self):
        for (i,
             (price,
              high,
              low,
              entry,
              signal,
              sl_before,
              open_trade)
             ) in enumerate(zip(self.df['Close'],
                                self.df['High'].values,
                                self.df['Low'].values,
                                self._converted,
                                self.returns,
                                self.stop_losses,
                                self.open_lot_prices)):
            if entry is not np.nan:
                diff_open_sl = sl_before - open_trade
                trade_high = high
                trade_low = low
            trade_low = min(low, trade_low)
            trade_high = max(high, trade_high)
            if signal == utils.BUY:
                sl = trade_high + diff_open_sl
            elif signal == utils.SELL:
                sl = trade_low + diff_open_sl
            else:
                sl = sl_before
            self.stop_losses[i] = sl

    def profit_distribution(self, steps: int = 100) -> pd.Series:
        equity = np.array(self.deposit_history)
        x_returns = equity[:-1] / equity[1:]

        hist = np.histogram(x_returns, steps)
        return pd.Series(hist[0], index=hist[1][:-1])


class ExampleStrategies(Trader):

    def _window_(self,
                 column: str,
                 n: int = 2,
                 *args,
                 **kwargs) -> List[Any]:
        return utils.get_window(self.df[column].values, n)

    @strategy
    def find_pip_bar(self,
                     min_diff_coef: float = 2.0,
                     body_coef: float = 10.0) -> utils.PREDICT_TYPE_LIST:
        self.returns = []
        flag = utils.EXIT
        e: int
        high: float
        low: float
        open_price: float
        close: float

        body: float
        shadow_high: float
        shadow_low: float
        for e, (high, low, open_price, close) in enumerate(
                zip(self.df['High'], self.df['Low'], self.df['Open'],
                    self.df['Close']), 1):
            body = abs(open_price - close)
            shadow_high = high - max(open_price, close)
            shadow_low = min(open_price, close) - low
            if body < (max(shadow_high, shadow_low) * body_coef):
                if shadow_low > (shadow_high * min_diff_coef):
                    flag = utils.BUY
                elif shadow_high > (shadow_low * min_diff_coef):
                    flag = utils.SELL
                self.returns.append(flag)
            else:
                self.returns.append(flag)
        self.set_credit_leverages()
        self.set_open_stop_and_take()
        return self.returns

    @strategy
    def find_DBLHC_DBHLC(self) -> utils.PREDICT_TYPE_LIST:
        self.returns = [utils.EXIT]
        flag: utils.PREDICT_TYPE = utils.EXIT

        flag_stop_loss: float = np.inf
        self.stop_losses = [flag_stop_loss]
        high: List[float]
        low: List[float]
        open_pr: List[float]
        close: List[float]

        for high, low, open_pr, close in zip(
                self._window_('High'),
                self._window_('Low'),
                self._window_('Open'),
                self._window_('Close')
        ):
            if low[0] == low[1] and close[1] > high[0]:
                flag = utils.BUY
                flag_stop_loss = min(low[0], low[1])
            elif high[0] == high[1] and close[0] > low[1]:
                flag = utils.SELL
                flag_stop_loss = max(high[0], high[1])

            self.returns.append(flag)
            self.stop_losses.append(flag_stop_loss)
        self.set_credit_leverages()
        self.set_open_stop_and_take(set_stop=False)
        return self.returns

    @strategy
    def find_TBH_TBL(self) -> utils.PREDICT_TYPE_LIST:
        self.returns = [utils.EXIT]
        flag: utils.PREDICT_TYPE = utils.EXIT
        high: List[float]
        low: List[float]
        open_: List[float]
        close: List[float]

        for e, (high, low, open_, close) in enumerate(
                zip(
                    self._window_('High'), self._window_('Low'),
                    self._window_('Open'), self._window_('Close')
                ), 1):
            if high[0] == high[1]:
                flag = utils.BUY
            elif low[0] == low[1]:
                flag = utils.SELL
            self.returns.append(flag)
        self.set_credit_leverages()
        self.set_open_stop_and_take()
        return self.returns

    @strategy
    def find_PPR(self) -> utils.PREDICT_TYPE_LIST:
        self.returns = [utils.EXIT] * 2
        flag: utils.PREDICT_TYPE = utils.EXIT
        high: List[float]
        low: List[float]
        opn: List[float]
        close: List[float]
        for e, (high, low, opn, close) in enumerate(
                zip(
                    self._window_('High', 3), self._window_('Low', 3),
                    self._window_('Open', 3), self._window_('Close', 3)), 1):
            if min(low) == low[1] and close[1] < close[2] and high[2] < high[0]:
                flag = utils.BUY
            elif max(high
                     ) == high[1] and close[2] < close[1] and low[2] > low[0]:
                flag = utils.SELL
            self.returns.append(flag)
        self.set_credit_leverages()
        self.set_open_stop_and_take()
        return self.returns

    @strategy
    def strategy_ichimoku(self,
                          tenkansen: int = 9,
                          kijunsen: int = 26,
                          senkouspan: int = 52,
                          chinkouspan: int = 26,
                          stop_loss_plus: Union[float, int] = 40.0,  # sl_tp_adder
                          plot: bool = True) -> utils.PREDICT_TYPE_LIST:
        cloud = ta.trend.IchimokuIndicator(self.df["High"],
                                           self.df["Low"],
                                           tenkansen,
                                           kijunsen,
                                           senkouspan,
                                           visual=True,
                                           fillna=True)
        tenkan_sen: np.ndarray = cloud.ichimoku_conversion_line().values
        kinjun_sen: np.ndarray = cloud.ichimoku_base_line().values
        senkou_span_a: np.ndarray = cloud.ichimoku_a().values
        senkou_span_b: np.ndarray = cloud.ichimoku_b().values
        prices: pd.Series = self.df['Close']
        chinkou_span: np.ndarray = prices.shift(-chinkouspan).values
        flag1: utils.PREDICT_TYPE = utils.EXIT
        flag2: utils.PREDICT_TYPE = utils.EXIT
        flag3: utils.PREDICT_TYPE = utils.EXIT
        trade: utils.PREDICT_TYPE = utils.EXIT
        name: str
        data: np.ndarray
        e: int
        close: float
        tenkan: float
        kijun: float
        A: float
        B: float
        chickou: float

        if plot:
            for name, data, color in zip(['tenkan-sen',
                                          'kijun-sen',
                                          'chinkou-span'],
                                         [tenkan_sen,
                                          kinjun_sen,
                                          chinkou_span],
                                         ['red',
                                          'blue',
                                          'green']):
                self.fig.plot_line(
                    line=data,
                    name=name,
                    width=utils.ICHIMOKU_LINES_WIDTH,
                    color=color,
                    _row=self.fig.data_row,
                    _col=self.fig.data_col
                )

            self.fig.plot_area(fast=senkou_span_a,
                               slow=senkou_span_b,
                               name_fast=utils.SENKOU_SPAN_A_NAME,
                               name_slow=utils.SENKOU_SPAN_B_NAME)

            self.returns = [utils.EXIT for i in range(chinkouspan)]
            self.stop_losses = [self.df['Close'].values[0]] * chinkouspan
            for e, (close, tenkan, kijun, A, B) in enumerate(zip(
                    prices.values[chinkouspan:],
                    tenkan_sen[chinkouspan:],
                    kinjun_sen[chinkouspan:],
                    senkou_span_a[chinkouspan:],
                    senkou_span_b[chinkouspan:],
            ), chinkouspan):
                max_cloud = max((A, B))
                min_cloud = min((A, B))

                if not min_cloud < close < max_cloud:
                    if tenkan > kijun:
                        flag1 = utils.BUY
                    elif tenkan < kijun:
                        flag1 = utils.SELL

                    if close > max_cloud:
                        flag2 = utils.BUY
                    elif close < min_cloud:
                        flag2 = utils.SELL

                    if close > prices[e - chinkouspan]:
                        flag3 = utils.BUY
                    elif close < prices[e - chinkouspan]:
                        flag3 = utils.SELL

                    if flag3 == flag1 == flag2:
                        trade = flag1
                    if (trade == utils.BUY and flag1 == utils.SELL) or (trade == utils.SELL and flag1 == utils.BUY):
                        trade = utils.EXIT

                self.returns.append(trade)
                min_cloud_now = min(senkou_span_a[e], senkou_span_b[e])
                max_cloud_now = max(senkou_span_a[e], senkou_span_b[e])
                if trade == utils.BUY:
                    self.stop_losses.append(min_cloud_now)
                elif trade == utils.SELL:
                    self.stop_losses.append(max_cloud_now)
                elif trade == utils.EXIT:
                    self.stop_losses.append(0.0)
                else:
                    raise ValueError('What???')

        self.set_open_stop_and_take(set_stop=False)
        self.set_credit_leverages()
        self.sl_tp_adder(add_stop_loss=stop_loss_plus)
        return self.returns

    @strategy
    def strategy_buy_hold(self) -> utils.PREDICT_TYPE_LIST:
        self.returns = [utils.BUY for _ in range(len(self.df))]
        self.set_credit_leverages()
        self.set_open_stop_and_take()
        return self.returns

    @strategy
    def strategy_2_sma(self,
                       slow: int = 100,
                       fast: int = 30,
                       plot: bool = True) -> utils.PREDICT_TYPE_LIST:
        self.returns = []
        SMA1 = ta.trend.sma_indicator(self.df['Close'], fast)
        SMA2 = ta.trend.sma_indicator(self.df['Close'], slow)
        if plot:
            self.fig.plot_line(line=SMA1.values,
                               width=utils.MA_FAST_WIDTH,
                               color=utils.MA_FAST_COLOR,
                               name=utils.MA_FAST_NAME.format(fast),
                               opacity=utils.MA_FAST_ALPHA,
                               _row=self.fig.data_row,
                               _col=self.fig.data_col)

            self.fig.plot_line(line=SMA2.values,
                               width=utils.MA_SLOW_WIDTH,
                               color=utils.MA_SLOW_COLOR,
                               name=utils.MA_SLOW_NAME.format(slow),
                               opacity=utils.MA_SLOW_ALPHA,
                               _row=self.fig.data_row,
                               _col=self.fig.data_col)

        for SMA13, SMA26 in zip(SMA1, SMA2):
            if SMA26 < SMA13:
                self.returns.append(utils.BUY)
            elif SMA13 < SMA26:
                self.returns.append(utils.SELL)
            else:
                self.returns.append(utils.EXIT)
        self.set_open_stop_and_take()
        self.set_credit_leverages()
        return self.returns

    @strategy
    def strategy_3_sma(self,
                       slow: int = 100,
                       mid: int = 26,
                       fast: int = 13,
                       plot: bool = True) -> utils.PREDICT_TYPE_LIST:
        self.returns = []
        SMA1 = ta.trend.sma_indicator(self.df['Close'], fast)
        SMA2 = ta.trend.sma_indicator(self.df['Close'], mid)
        SMA3 = ta.trend.sma_indicator(self.df['Close'], slow)

        if plot:
            for SMA, color, speed, name, alpha, size in zip([SMA1, SMA2, SMA3],
                                                            [utils.MA_FAST_COLOR, utils.MA_MID_COLOR, utils.MA_SLOW_COLOR],
                                                            [fast, mid, slow],
                                                            [utils.MA_FAST_NAME, utils.MA_MID_NAME, utils.MA_SLOW_NAME],
                                                            [utils.MA_FAST_ALPHA, utils.MA_MID_ALPHA, utils.MA_SLOW_ALPHA],
                                                            [utils.MA_FAST_WIDTH, utils.MA_MID_WIDTH, utils.MA_SLOW_WIDTH]):
                self.fig.plot_line(line=SMA.values,
                                   width=size,
                                   color=color,
                                   name=name.format(speed),
                                   opacity=alpha,
                                   _row=self.fig.data_row,
                                   _col=self.fig.data_col)

        for SMA13, SMA26, SMA100 in zip(SMA1, SMA2, SMA3):
            if SMA100 < SMA26 < SMA13:
                self.returns.append(utils.BUY)
            elif SMA100 > SMA26 > SMA13:
                self.returns.append(utils.SELL)
            else:
                self.returns.append(utils.EXIT)

        self.set_credit_leverages()
        self.set_open_stop_and_take()
        return self.returns

    @strategy
    def strategy_3_ema(self,
                       slow: int = 46,
                       mid: int = 21,
                       fast: int = 3,
                       plot: bool = True) -> utils.PREDICT_TYPE_LIST:
        self.returns = []
        ema3 = ta.trend.ema_indicator(self.df['Close'], fast)
        ema21 = ta.trend.ema_indicator(self.df['Close'], mid)
        ema46 = ta.trend.ema_indicator(self.df['Close'], slow)

        if plot:
            for SMA, color, speed, name, alpha, size in zip([ema3.values, ema21.values, ema46.values],
                                                            [utils.MA_FAST_COLOR, utils.MA_MID_COLOR, utils.MA_SLOW_COLOR],
                                                            [fast, mid, slow],
                                                            [utils.MA_FAST_NAME, utils.MA_MID_NAME, utils.MA_SLOW_NAME],
                                                            [utils.MA_FAST_ALPHA, utils.MA_MID_ALPHA, utils.MA_SLOW_ALPHA],
                                                            [utils.MA_FAST_WIDTH, utils.MA_MID_WIDTH, utils.MA_SLOW_WIDTH]):
                self.fig.plot_line(line=SMA.values,
                                   width=size,
                                   color=color,
                                   name=name.format(speed),
                                   opacity=alpha,
                                   _row=self.fig.data_row,
                                   _col=self.fig.data_col)

        for EMA1, EMA2, EMA3 in zip(ema3, ema21, ema46):
            if EMA1 > EMA2 > EMA3:
                self.returns.append(utils.BUY)
            elif EMA1 < EMA2 < EMA3:
                self.returns.append(utils.SELL)
            else:
                self.returns.append(utils.EXIT)
        self.set_credit_leverages()
        self.set_open_stop_and_take()
        return self.returns

    @strategy
    def strategy_macd(self,
                      slow: int = 100,
                      fast: int = 30) -> utils.PREDICT_TYPE_LIST:
        diff = ta.trend.macd_diff(self.df['Close'], slow, fast)

        for j in diff:
            if j > 0:
                self.returns.append(utils.BUY)
            elif 0 > j:
                self.returns.append(utils.SELL)
            else:
                self.returns.append(utils.EXIT)
        self.set_credit_leverages()
        self.set_open_stop_and_take()
        return self.returns

    @strategy
    def strategy_rsi(self,
                     minimum: Union[float, int] = 13,
                     maximum: Union[float, int] = 87,
                     max_mid: Union[float, int] = 13,
                     min_mid: Union[float, int] = 87,
                     **rsi_kwargs) -> utils.PREDICT_TYPE_LIST:
        self.returns = []
        rsi = ta.momentum.rsi(close=self.df['Close'], **rsi_kwargs)
        flag: utils.PREDICT_TYPE = utils.EXIT

        for val in rsi.values:
            if val < minimum:
                flag = utils.BUY
            elif val > maximum:
                flag = utils.SELL
            elif flag == utils.BUY and val < max_mid:
                flag = utils.EXIT
            elif flag == utils.SELL and val > min_mid:
                flag = utils.EXIT
            self.returns.append(flag)

        self.set_credit_leverages()
        self.set_open_stop_and_take()
        return self.returns

    @strategy
    def strategy_parabolic_SAR(self, plot: bool = True, **sar_kwargs) -> utils.PREDICT_TYPE_LIST:
        self.returns = []
        sar: ta.trend.PSARIndicator = ta.trend.PSARIndicator(self.df['High'], self.df['Low'],
                                                             self.df['Close'], **sar_kwargs)
        sardown: np.ndarray = sar.psar_down().values
        sarup: np.ndarray = sar.psar_up().values
        self.stop_losses = sar.psar().values.tolist()
        if plot:
            self.fig.plot_line(line=sarup,
                               width=utils.SAR_UP_WIDTH,
                               color=utils.SAR_UP_COLOR,
                               name=utils.SAR_UP_NAME,
                               opacity=utils.SAR_UP_ALPHA,
                               _row=self.fig.data_row,
                               _col=self.fig.data_col)

            self.fig.plot_line(line=sardown,
                               width=utils.SAR_DOWN_WIDTH,
                               color=utils.SAR_DOWN_COLOR,
                               name=utils.SAR_DOWN_NAME,
                               opacity=utils.SAR_DOWN_ALPHA,
                               _row=self.fig.data_row,
                               _col=self.fig.data_col)

        for price, up, down in zip(
                list(self.df['Close'].values), list(sarup), list(sardown)):
            numup = np.nan_to_num(up, nan=-9999)
            numdown = np.nan_to_num(down, nan=-9999)
            if numup != -9999:
                self.returns.append(utils.BUY)
            elif numdown != -9999:
                self.returns.append(utils.SELL)
            else:
                self.returns.append(utils.EXIT)
        self.set_credit_leverages()
        self.set_open_stop_and_take(set_stop=False)
        self.correct_sl_tp()
        return self.returns

    @strategy
    def strategy_macd_histogram_diff(self,
                                     slow: int = 23,
                                     fast: int = 12,
                                     **macd_kwargs) -> utils.PREDICT_TYPE_LIST:
        _MACD_ = ta.trend.MACD(self.df['Close'], slow, fast, **macd_kwargs)
        signal_ = _MACD_.macd_signal()
        macd_ = _MACD_.macd()
        histogram: pd.DataFrame = pd.DataFrame(macd_.values - signal_.values)
        for element in histogram.diff().values:
            if element == 0:
                self.returns.append(utils.EXIT)
            elif element > 0:
                self.returns.append(utils.BUY)
            else:
                self.returns.append(utils.SELL)
        self.set_credit_leverages()
        self.set_open_stop_and_take()
        return self.returns

    @strategy
    def strategy_supertrend(self,
                            plot: bool = True,
                            multiplier: float = 3.0,
                            length: int = 10) -> utils.PREDICT_TYPE_LIST:
        st: indicators.SuperTrendIndicator = indicators.SuperTrendIndicator(self.df['Close'],
                                                                            self.df['High'],
                                                                            self.df['Low'],
                                                                            multiplier=multiplier,
                                                                            length=length)
        if plot:
            self.fig.plot_line(line=st.get_supertrend_upper(),
                               width=utils.ST_UP_WIDTH,
                               color=utils.ST_UP_COLOR,
                               name=utils.ST_UP_NAME,
                               opacity=utils.ST_UP_ALPHA,
                               _row=self.fig.data_row,
                               _col=self.fig.data_col)

            self.fig.plot_line(line=st.get_supertrend_upper(),
                               width=utils.ST_DOWN_WIDTH,
                               color=utils.ST_DOWN_COLOR,
                               name=utils.ST_DOWN_NAME,
                               opacity=utils.ST_DOWN_ALPHA,
                               _row=self.fig.data_row,
                               _col=self.fig.data_col)
        self.returns = list(st.get_supertrend_strategy_returns())
        self.returns[:length + 1] = [utils.EXIT] * (length + 1)
        self.stop_losses = list(st.get_supertrend())
        self.stop_losses[0] = np.inf if self.returns[0] == utils.SELL else -np.inf
        self.set_open_stop_and_take(set_stop=False)
        self.set_credit_leverages()
        return self.returns

    @strategy
    def strategy_bollinger(self,
                           plot: bool = True,
                           to_mid: bool = False,
                           *bollinger_args,
                           **bollinger_kwargs) -> utils.PREDICT_TYPE_LIST:
        self.returns = []
        flag: utils.PREDICT_TYPE = utils.EXIT
        bollinger: ta.volatility.BollingerBands = ta.volatility.BollingerBands(self.df['Close'],
                                                                               fillna=True,
                                                                               *bollinger_args,
                                                                               **bollinger_kwargs)

        mid_: pd.Series = bollinger.bollinger_mavg()
        upper: pd.Series = bollinger.bollinger_hband()
        lower: pd.Series = bollinger.bollinger_lband()
        if plot:
            self.fig.plot_line(line=upper.values,
                               width=utils.UPPER_BB_WIDTH,
                               color=utils.UPPER_BB_COLOR,
                               name=utils.UPPER_BB_NAME,
                               opacity=utils.UPPER_BB_ALPHA,
                               _row=self.fig.data_row,
                               _col=self.fig.data_col)
            self.fig.plot_line(line=mid_.values,
                               width=utils.MID_BB_WIDTH,
                               color=utils.MID_BB_COLOR,
                               name=utils.MID_BB_NAME,
                               opacity=utils.MID_BB_ALPHA,
                               _row=self.fig.data_row,
                               _col=self.fig.data_col)
            self.fig.plot_line(line=lower.values,
                               width=utils.LOWER_BB_WIDTH,
                               color=utils.LOWER_BB_COLOR,
                               name=utils.LOWER_BB_NAME,
                               opacity=utils.LOWER_BB_ALPHA,
                               _row=self.fig.data_row,
                               _col=self.fig.data_col)
        close: float
        up: float
        mid: float
        low: float
        for close, up, mid, low in zip(self.df['Close'].values,
                                       upper,
                                       mid_,
                                       lower):
            if close <= low:
                flag = utils.BUY
            if close >= up:
                flag = utils.SELL

            self.returns.append(flag)
        self.set_open_stop_and_take()
        if to_mid:
            self.take_profits = mid_.tolist()
        self.set_credit_leverages()
        return self.returns

    @strategy
    def strategy_bollinger_breakout(self,
                                    plot: bool = True,
                                    to_mid: bool = False,
                                    to_opposite: bool = False,
                                    *bollinger_args,
                                    **bollinger_kwargs):
        self.strategy_bollinger(plot=plot,
                                to_mid=to_mid,
                                *bollinger_args,
                                **bollinger_kwargs)
        self.inverse_strategy()
        if to_opposite:
            bollinger: ta.volatility.BollingerBands = ta.volatility.BollingerBands(self.df['Close'],
                                                                                   fillna=True,
                                                                                   *bollinger_args,
                                                                                   **bollinger_kwargs)

            mid_: pd.Series = bollinger.bollinger_mavg()
            upper: pd.Series = bollinger.bollinger_hband()
            lower: pd.Series = bollinger.bollinger_lband()
            self.stop_losses = []
            for sig, high, low in zip(self.returns,
                                      upper,
                                      lower):
                if sig == utils.BUY:
                    self.stop_losses.append(low)
                else:
                    self.stop_losses.append(high)
        self.correct_sl_tp()
        return self.returns

    @strategy
    def strategy_idris(self, points=20):
        self.stop_losses = [np.inf] * 2
        self.take_profits = [np.inf] * 2
        flag = utils.EXIT
        self.returns = [flag] * 2
        for e in range(len(self.df) - 2):
            bar3price = self.df['Close'][e + 2]
            mid2bar = (self.df['High'][e + 1] + self.df['Low'][e + 1]) / 2
            if bar3price < mid2bar:
                flag = utils.SELL
            elif bar3price > mid2bar:
                flag = utils.BUY
            self.returns.append(flag)
        self.set_open_stop_and_take(stop_loss=points * 2, take_profit=points * 20)
        self.set_credit_leverages()
        return self.returns

    @strategy
    def DP_strategy(self,
                    length: int = 14,
                    s1: int = 3,
                    s2: int = 3,
                    sl: float = 300.0,
                    tp: float = 500.0):
        self.returns = []
        stoch = ta.momentum.StochRSIIndicator(close=(self.df['High'] + self.df['Low']) / 2,
                                              window=length,
                                              smooth1=s1,
                                              smooth2=s2)
        flag = utils.EXIT
        for fast, slow in zip(stoch.stochrsi_k() * 100,
                              stoch.stochrsi_d() * 100):
            if fast > 80 and slow > 80:
                flag = utils.SELL
            if fast < 20 and slow < 20:
                flag = utils.BUY
            self.returns.append(flag)
        self.set_credit_leverages()
        self.set_open_stop_and_take(take_profit=tp,
                                    stop_loss=sl)
        return self.returns

    @strategy
    def DP_2_strategy(self,
                      RSI_length: int = 14,
                      STOCH_length: int = 14,
                      STOCH_smooth: int = 3,
                      sl: float = 300.0,
                      tp: float = 500.0):
        self.returns = []
        stoch = ta.momentum.StochasticOscillator(close=self.df['Close'],
                                                 high=self.df['High'],
                                                 low=self.df['Low'],
                                                 window=STOCH_length,
                                                 smooth_window=STOCH_smooth)

        rsi = ta.momentum.RSIIndicator(close=self.df['Close'],
                                       window=RSI_length)

        flag = utils.EXIT
        for a, b, c in zip(stoch.stoch(),
                           stoch.stoch_signal(),
                           rsi.rsi()):
            if min(a, b) > 80 and c > 80:
                flag = utils.SELL
            if max(a, b) < 20 and c < 20:
                flag = utils.BUY
            self.returns.append(flag)
        self.set_credit_leverages()
        self.set_open_stop_and_take(take_profit=tp,
                                    stop_loss=sl)
        return self.returns

    @strategy
    def strategy_kst(self, sl=5000, **kst_kwargs):
        KST = ta.trend.KSTIndicator(close=self.df['Close'], **kst_kwargs)
        fast = KST.kst()
        slow = KST.kst_sig()
        self.returns = []
        for e, s in zip(fast, slow):
            if e > s:
                self.returns.append(utils.BUY)
            else:
                self.returns.append(utils.SELL)
        self.set_credit_leverages(1)
        self.set_open_stop_and_take(stop_loss=sl)
        return self.returns

    @strategy
    def strategy_cci(self, **cci_kwargs):
        self.returns = []
        CCI = ta.trend.CCIIndicator(self.df['High'],
                                    self.df['Low'],
                                    self.df['Close'],
                                    **cci_kwargs)
        RSI = ta.momentum.RSIIndicator(self.df['Close'])
        for price, cci, rsi in zip(self.df['Close'].values, CCI.cci(), RSI.rsi()):
            if cci < 10 and rsi < 43:
                self.returns.append(utils.BUY)
        self.set_credit_leverages()
        self.set_open_stop_and_take()

    @strategy
    def new_macd_strategy(self, slow=21, fast=12, ATR_win=14, ATR_multiplier=5):
        self.stop_losses = []
        self.returns = []

        macd_indicator = ta.trend.MACD(close=self.df['Close'],
                                       window_slow=slow,
                                       window_fast=fast,
                                       fillna=True)
        histogram = macd_indicator.macd_diff()

        atr = ta.volatility.AverageTrueRange(high=self.df['High'],
                                             low=self.df['Low'],
                                             close=self.df['Close'],
                                             window=ATR_win,
                                             fillna=True)

        for diff, price, stop_indicator in zip(histogram.values,
                                               self.df['Close'].values,
                                               atr.average_true_range().values):
            stop_indicator *= ATR_multiplier

            if diff > 0:
                self.returns.append(utils.BUY)
                self.stop_losses.append(price - stop_indicator)
            else:
                self.returns.append(utils.SELL)
                self.stop_losses.append(price + stop_indicator)

        self.set_open_stop_and_take(set_stop=False)
        self.set_credit_leverages()
        return self.returns

    @strategy
    def strategy_pump_detector(self,
                               period: int = 15,
                               points=300,
                               take_profit=300,
                               stop_loss=150):
        flag = utils.EXIT
        sl = np.inf
        tp = np.inf

        self.returns = [flag] * period
        self.stop_losses = [np.inf] * period
        self.take_profits = [np.inf] * period

        for curr_index in self.df.index[period:]:
            curr_period = self.df[curr_index-period:curr_index]
            max_ = curr_period['High'].max()
            min_ = curr_period['Low'].min()
            close = curr_period['Close'].values[-1]

            growth_in_points = (close - min_) / min_ * 10_000
            drawdown_in_points = (close - max_) / max_ * -10_000

            if max_ > sl and flag == utils.SELL:
                flag = utils.EXIT
            if min_ < sl and flag == utils.BUY:
                flag = utils.EXIT
            if max_ > tp and flag == utils.BUY:
                flag = utils.EXIT
            if min_ < tp and flag == utils.SELL:
                flag = utils.EXIT

            if growth_in_points > points and flag != utils.BUY:
                flag = utils.BUY
                if self.returns[-1] != flag:
                    sl = close - close*stop_loss/10_000
                    tp = close + close*take_profit/10_000
            elif drawdown_in_points > points and flag != utils.SELL:
                flag = utils.SELL
                if self.returns[-1] != flag:
                    sl = close + close*stop_loss/10_000
                    tp = close - close*take_profit/10_000

            self.returns.append(flag)
            self.stop_losses.append(sl)
            self.take_profits.append(tp)

    @strategy
    def strategy_price_channel(self,
                               support_period: int = 20,
                               resistance_period: int = 20,
                               channel_part: float = 0.8,
                               plot: bool = True):
        PC = indicators.PriceChannel(high=self.df['High'],
                                     low=self.df['Low'],
                                     support_period=support_period,
                                     resistance_period=resistance_period,
                                     channel_part=channel_part)
        flag = utils.EXIT
        for price, low, high in zip(self.df['Close'],
                                    PC.lower_line(),
                                    PC.higher_line()):
            if price > high:
                flag = utils.SELL
            elif price < low:
                flag = utils.BUY
            self.returns.append(flag)
        if plot:
            self.fig.plot_line(PC.lower_line(),
                               width=utils.PRICE_CHANNEL_LOWER_WIDTH,
                               color=utils.PRICE_CHANNEL_LOWER_COLOR,
                               name=utils.PRICE_CHANNEL_LOWER_NAME,
                               opacity=utils.PRICE_CHANNEL_LOWER_ALPHA,
                               _row=self.fig.data_row,
                               _col=self.fig.data_col)
            self.fig.plot_line(PC.higher_line(),
                               width=utils.PRICE_CHANNEL_UPPER_WIDTH,
                               color=utils.PRICE_CHANNEL_UPPER_COLOR,
                               name=utils.PRICE_CHANNEL_UPPER_NAME,
                               opacity=utils.PRICE_CHANNEL_UPPER_ALPHA,
                               _row=self.fig.data_row,
                               _col=self.fig.data_col)

    @strategy
    def strategy_adaptive_price_channel(
            self,
            support_period: int = 20,
            resistance_period: int = 20,
            channel_part: float = 0.8,
            atr_window: int = 14,
            multiplier_window: int = 30,
            plot: bool = True
    ):
        PC = indicators.AdaptivePriceChannel(high=self.df['High'],
                                             low=self.df['Low'],
                                             close=self.df['Close'],
                                             support_period=support_period,
                                             resistance_period=resistance_period,
                                             channel_part=channel_part,
                                             atr_window=atr_window,
                                             multiplier_window=multiplier_window)
        flag = utils.EXIT
        for price, low, high in zip(self.df['Close'],
                                    PC.lower_line(),
                                    PC.higher_line()):
            if price > high:
                flag = utils.SELL
            elif price < low:
                flag = utils.BUY
            self.returns.append(flag)
        if plot:
            self.fig.plot_line(PC.lower_line(),
                               width=utils.PRICE_CHANNEL_LOWER_WIDTH,
                               color=utils.PRICE_CHANNEL_LOWER_COLOR,
                               name=utils.PRICE_CHANNEL_LOWER_NAME,
                               opacity=utils.PRICE_CHANNEL_LOWER_ALPHA,
                               _row=self.fig.data_row,
                               _col=self.fig.data_col)
            self.fig.plot_line(PC.higher_line(),
                               width=utils.PRICE_CHANNEL_UPPER_WIDTH,
                               color=utils.PRICE_CHANNEL_UPPER_COLOR,
                               name=utils.PRICE_CHANNEL_UPPER_NAME,
                               opacity=utils.PRICE_CHANNEL_UPPER_ALPHA,
                               _row=self.fig.data_row,
                               _col=self.fig.data_col)
