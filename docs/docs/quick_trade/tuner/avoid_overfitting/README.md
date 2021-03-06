# avoid_overfitting
This part of quick_trade is needed to minimize overfitting.

## What is overfitting?

> Overfitting is a modeling error in statistics that occurs when a function 
> is too closely aligned to a limited set of data points. As a result, 
> the model is useful in reference only to its initial data set, and not 
> to any other data sets.
> 
> Overfitting the model generally takes the form of making an overly 
> complex model to explain idiosyncrasies in the data under study.
> In reality, the data often studied has some degree of error 
> or random noise within it. Thus, attempting to make the model conform 
> too closely to slightly inaccurate data can infect the model with 
> substantial errors and reduce its predictive power.
> 
> -[investopedia](https://www.investopedia.com/terms/o/overfitting.asp)

### overfitting problem-solving methods implemented in quick trade:
##### WalkForward analysis (recommended):
The bottom line is that we check the robustness of the strategy 
settings that we received during the optimization.

> What is walk-forward optimisation? Walk forward optimisation 
> is a process for testing a trading strategy by finding its optimal
> trading parameters in a certain time period (called the in-sample 
> or training data) and checking the performance of those parameters 
> in the following time period (called the out-of-sample or testing data).
> 
> -[algotrading101](https://algotrading101.com/learn/walk-forward-optimization/)

![WFA-visualization](https://i.stack.imgur.com/IUWuO.gif)

![WFA-visualization-2](https://www.tradelikeamachine.com/images/user-guide/interpreting-results/all-walk-forward-stages-in-wfa.png)

```python
from quick_trade.tuner.avoid_overfitting import WalkForward
from quick_trade.trading_sys import ExampleStrategies
from quick_trade.tuner import Arange
from quick_trade.brokers import TradingClient

from quick_trade.plots import BasePlotlyGraph, make_figure

config = {
    'strategy_bollinger_breakout':
        [
            {
                'plot': False,
                'window': Arange(10, 200, 20),
                'window_dev': 1
            }
        ]
}

graph = BasePlotlyGraph(make_figure(700, 1400))

client = TradingClient()
walkforward_optimizer = WalkForward(client=client)

walkforward_optimizer.run_analysis('ETH/USDT',
                                   '30m',
                                   config=config,
                                   trader_instance=ExampleStrategies,
                                   sort_by='profit/deviation ratio',
                                   commission=0.075)

print(walkforward_optimizer.info())

graph.plot_line(line=walkforward_optimizer.equity(),
                name='walk-forward analysis',
                width=2.5,
                color='white')
graph.log_y()
graph.show()
```
##### by volatility:
1. Group currency pairs by volatility
2. Within the group, we optimize the strategy parameters. simultaneously on all pairs (built-in cross-testing)
3. Take the best parameters for each group - this is the result of optimization.

?> Cross-testing allows you to identify ineffective (overfitted) strategies.

```python
from quick_trade.tuner.avoid_overfitting.volatility import split_tickers_volatility, Tuner
from quick_trade.brokers import TradingClient
from quick_trade.tuner.tuner import QuickTradeTuner, Arange, Choise
from quick_trade.trading_sys import ExampleStrategies
from quick_trade.tuner import bests_to_config


tickers = ['BTC/USDT',
           'MANA/USDT', 
           'ETH/USDT', 
           'LTC/USDT', 
           'LUNA/USDT', 
           'GALA/USDT', 
           'BNB/USDT',
           'XRP/USDT', 
           'ADA/USDT']


groups = split_tickers_volatility(tickers)

params = {
    'strategy_bollinger_breakout':
        [
            {
                'window': Arange(10, 200, 50),
                'window_dev': Choise([0.5, 1, 1.5]),
                'plot': False
            }
        ],
}

tuner = Tuner(client=TradingClient(),
              clusters=groups,
              intervals=['1h'],
              limits=[1000],
              tuner_instance=QuickTradeTuner,
              strategies_kwargs=params)
tuner.tune(ExampleStrategies,
           commission=0.075)
tuner.sort_tunes('profit/deviation ratio')

print(bests_to_config(tuner.get_best(5)))  # 5 best settings for each tuner

```

##### validation sample analysis
!> This functionality is not directly a tuner that reduces overfitting, it allows you to visually assess the fit.
1. Divide the frame of candles into test and validation sets.
2. Run the tuners on two samples with the same strategy parameters.
3. Compare results of the strategies on the test and validation sets.

```python
from quick_trade.tuner.avoid_overfitting.validation_analysis import ValidationTuner, Analyzer
from quick_trade.tuner.tuner import Arange
from quick_trade.plots import ValidationAnalysisGraph
from quick_trade.brokers import TradingClient
from quick_trade.trading_sys import ExampleStrategies


params = {
    'strategy_bollinger_breakout':
        [
            dict(
                window=Arange(1, 300, 5),
                window_dev=1
            )
        ],
}

t = ValidationTuner(TradingClient(),
                    tickers=['BTC/USDT', 'ETH/USDT', 'ETC/USDT', 'LTC/USDT'],
                    intervals=['1h'],
                    limits=[1000],
                    strategies_kwargs=params,
                    multi_backtest=True,
                    validation_split=1/3)
t.tune(ExampleStrategies, commission=0.075, val_json_path='val.json', train_json_path='train.json')
validator = Analyzer(train='train.json',
                     val='val.json',
                     sort_by='calmar ratio')
fig = ValidationAnalysisGraph()
fig.connect_analyzer(validator)
validator.generate_frame()
validator.plot_frame()
validator.fig.show()
```
