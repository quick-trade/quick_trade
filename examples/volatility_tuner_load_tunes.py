from quick_trade.quick_trade_tuner.avoid_overfitting.volatility import Tuner
from ccxt import binance
from quick_trade.brokers import TradingClient
from quick_trade.quick_trade_tuner.tuner import QuickTradeTuner


tuner = Tuner(client=TradingClient(binance()),
              intervals=['1h'],
              limits=[1000],
              tuner_instance=QuickTradeTuner)
tuner.load_tunes()
tuner.resorting('profit/deviation ratio')
print(tuner.get_best(3))