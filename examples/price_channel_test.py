from quick_trade.quick_trade.trading_sys import ExampleStrategies
from quick_trade.quick_trade.plots import make_trader_figure, TraderGraph
from custom_client import BinanceTradingClient


ticker = 'BNB/USDT'
timeframe = '1h'

figure = make_trader_figure(height=2000, width=1400)
graph = TraderGraph(figure=figure)
client = BinanceTradingClient()

df = client.get_data_historical(ticker=ticker, interval=timeframe)

trader = ExampleStrategies(ticker=ticker, interval=timeframe, df=df)

trader.connect_graph(graph)
trader.log_data()
trader.log_deposit()

trader.strategy_adaptive_price_channel(75, 75)
trader.inverse_strategy()  # trend strategy
trader.backtest(deposit=300, commission=0.075)
