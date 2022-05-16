# A guide to using quick_trade, from drawing up a strategy to selecting the best parameters and launching on the exchange:

## How can I create my own strategy?

To create a strategy, you will need to generate values for:

- `Trader.returns` - Directly the results of the strategy.
- `Trader.stop_losses` - Stop-loss list.
- `Trader.take_profits` - Take-profit list.
- `Trader.credit_leverages` - Not really leverages, but rather the values by which need to multiply the trade amount.
- `Trader.open_lot_prices` - List of prices at which deals were opened.

?> Lengths of all these variables are equal to the length of the dataframe with the prices of the traded currency.

If your strategy does not provide for the use of anything from this list, quick_trade provides methods for setting default values (as if the trader and tester would not use them).

If your strategy does not generate stop loss or take profit, there is the
[`Trader.set_open_stop_and_take`](https://quick-trade.github.io/quick_trade/#/docs/quick_trade/trading_sys?id=set_open_stop_and_take)
method. It automatically generates trade entry prices and, if necessary, stop-losses and take-profits.

If you need to generate stop-loss and take-profit:

```python
self.set_open_stop_and_take()
```

If your strategy PROVIDES a stop loss, then you need to set the value `set_stop` equal to `False`:

```python
self.set_open_stop_and_take(set_stop=False)  # The method does not change or set stop-loss.
```

Likewise with take profit and `set_take`.

If you want to set take-profit or stop-loss, you can specify the `take_profit` and `stop_loss` arguments in points.

?> tip: pips (aka point) = 1/10_000 of price

If you want to enter a trade not for the entire deposit, but for a part or more (leverage), you can use the
[`set_credit_leverages`](https://quick-trade.github.io/quick_trade/#/docs/quick_trade/trading_sys?id=set_credit_leverages)
method. It places the same `self.credit_leverages` for all candles.

```python
self.set_credit_leverages(credit_lev=0.25)  # 1/4 of deposit for trade
```

```python
self.set_credit_leverages(credit_lev=5)  # 5X credit leverage
```

The 3 variables from utils.py should be used as the strategy results:

- `utils.BUY`
- `utils.SELL`
- `utils.EXIT`

#### Example:

?> Keep in mind: use `strategy` decorator to strategies, it can fixes some minor bugs.

```python
import quick_trade.trading_sys as qtr
from quick_trade import utils
from ta.trend import MACD
from ta.volatility import AverageTrueRange
from quick_trade import strategy


class MyTrader(qtr.Trader):
    @strategy
    def new_macd_strategy(self, slow=21, fast=12, ATR_win=14, ATR_multiplier=5):
        self.stop_losses = []
        self.returns = []

        macd_indicator = MACD(close=self.df['Close'],
                              window_slow=slow,
                              window_fast=fast,
                              fillna=True)  # MACD indicator from ta module
        histogram = macd_indicator.macd_diff()

        atr = AverageTrueRange(high=self.df['High'],
                               low=self.df['Low'],
                               close=self.df['Close'],
                               window=ATR_win,
                               fillna=True)  # ATR for custom stop-loss

        for diff, price, stop_indicator in zip(histogram.values,
                                               self.df['Close'].values,
                                               atr.average_true_range().values):
            stop_indicator *= ATR_multiplier

            if diff > 0:
                self.returns.append(utils.BUY)
                self.stop_losses.append(price - stop_indicator)  # custom ATR stop-loss
            else:
                self.returns.append(utils.SELL)
                self.stop_losses.append(price + stop_indicator)  # same

        self.set_open_stop_and_take(set_stop=False)
        self.set_credit_leverages(1)  # trading without any leverage but for all deposit
        return self.returns  # It's not obligatory

```

## How can I test it?

There are two methods for testing in quick_trade:

- [`backtest`](https://quick-trade.github.io/quick_trade/#/docs/quick_trade/trading_sys?id=backtest) - A method for testing a strategy on a single dataframe. This method will show you a graph of the dataframe,
  deposit and its changes
- [`multi_backtest`](https://quick-trade.github.io/quick_trade/#/docs/quick_trade/trading_sys?id=multi_backtest) - A method for testing a strategy on multiple dataframes. This method will show you a graph of the
  deposit and its changes, but without any dataframe, because there are a lot of them

Code:

```python
# initializing a trader, connecting the exchange and the graph and using the strategy.
from quick_trade.brokers import TradingClient
from quick_trade.plots import TraderGraph, make_trader_figure
from ccxt import ftx

client = TradingClient(ftx())
trader = MyTrader(ticker='ETH/BTC',
                  df=client.get_data_historical('ETH/BTC', interval='5m'),
                  interval='5m')

fig = make_trader_figure()
graph = TraderGraph(figure=fig)
trader.connect_graph(graph)
trader.set_client(client)

trader.new_macd_strategy()

# BACKTESTING
trader.backtest(deposit=1000,
                commission=0.075)
```

Result:

```commandline
losses: 64
trades: 97
profits: 27
mean year percentage profit: -99.99999998327092%
winrate: 27.835051546391753%
mean deviation: 2.624118103674615%
Sharpe ratio: -44.291604314886655
Sortino ratio: -52.11339011671788
calmar ratio: -4.920697866228742
max drawdown: 20.322320675199602%
```

![image](https://raw.githubusercontent.com/quick-trade/quick_trade/main/img/simple_backtest_example.png)

To use [`multi_backtest`](https://quick-trade.github.io/quick_trade/#/docs/quick_trade/trading_sys?id=multi_backtest), you do not need to apply the strategy before the test, you do not even need to set the `df`
and `ticker` when [initializing the trader](https://quick-trade.github.io/quick_trade/#/docs/quick_trade/trading_sys?id=trader).

```python
client = TradingClient(ftx())
trader = MyTrader(ticker='ETH/BTC',
                  interval='5m')

fig = make_trader_figure()
graph = TraderGraph(figure=fig)
trader.connect_graph(graph)
trader.set_client(client)

# BACKTESTING
strategy = dict(
    new_macd_strategy=dict(
        slow=100,
        fast=30)
)

trader.multi_backtest(test_config={
    'ETH/USDT': [strategy],
    'BTC/USDT': [strategy],
},
    deposit=1000,
    commission=0.075)
```

Result:

```commandline
losses: 54
trades: 80
profits: 22
mean year percentage profit: -93.08433705679062%
winrate: 27.5%
mean deviation: 1.6403124394477397%
Sharpe ratio: -0.599092330855509
Sortino ratio: -0.9589200009261966
calmar ratio: -9.081044783748151
max drawdown: 10.250399516075348%
```

![image](https://github.com/quick-trade/quick_trade/blob/main/img/multi_backtest_example.png?raw=true)

?> If your strategy does not provide for exit conditions or provides for the ability to enter several trades at once, you can
use [`multi_trades`](https://quick-trade.github.io/quick_trade/#/docs/quick_trade/trading_sys?id=multi_trades). This method processes the strategist's prediction data and generates leverage.

## What if I combine the two strategies?

### More strategies?

## My strategy is good! How can I start it?
