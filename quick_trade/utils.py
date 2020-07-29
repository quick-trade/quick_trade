import logging
import pandas as pd
import numpy as np
import itertools
import datetime
from iexfinance.stocks import get_historical_intraday
import os

R = '#ff0000'
G = '#55ff00'
B = '#0015ff'

os.environ['IEX_API_VERSION'] = 'iexcloud-sandbox'
os.environ['IEX_TOKEN'] = 'Tpk_a4bc3e95d4c94810a3b2d4138dc81c5d'
__author__ = 'Vlad Kochetov'
__credits__ = ["Hemerson Tacon -- Stack overflow",
               "hpaulj -- Stack overflow"]
__version__ = "1.9.1"


TICKER = '^DJI'
SCATTER_SIZE = 12
SCATTER_ALPHA = 1
TAKE_STOP_OPN_WIDTH = 1
TEXT_COLOR = 'white'
SUB_LINES_WIDTH = 3
STOP_TAKE_OPN_ALPHA = 1
COLOR_DEPOSIT = 'white'
SCATTER_DEPO_ALPHA = SCATTER_ALPHA
DEPO_COLOR_UP = 'green'
DEPO_COLOR_DOWN = 'red'
logger = logging.getLogger()
logger.setLevel(50)
logging.basicConfig(level=10, filename='trading.log')


def set_(plotter):
    ret = list(plotter.copy())
    for e, i in enumerate(plotter[1:]):
        if i == plotter[e]:
            ret[e + 1] = np.nan
    return ret


def to_4_col_df(data, *columns):
    """
    data:  |  array-like  |  data to converting

    returns:
    pd.DataFrame with 4 your columns

    """
    PREDICT = [[] for _ in range(4)]
    for it in range(4):
        for i in range(it, len(data), 4):
            PREDICT[it].append(data[i])
    return pd.DataFrame(PREDICT, index=columns).T


def inverse_4_col_df(df, columns):
    df = pd.DataFrame(df)
    ret = df.values
    rets = []
    for column in columns:
        rets.append(
            pd.DataFrame(itertools.chain.from_iterable(ret), columns=[column]))
    return pd.concat(rets, axis=1)


def get_data(ticker, undo_days):
    tuples = []
    end = datetime.datetime.today()
    date_list = [end - datetime.timedelta(days=d) for d in range(undo_days)]
    for i in range(len(date_list)):
        ret = str(np.array(date_list[::-1])[i])[:10]
        ret = ret.split('-')
        for e, dat in enumerate(ret):
            ret[e] = int(dat)
        tuples.append(tuple(ret))

    dataframes = []
    for date_ in tuples:
        dat = datetime.datetime(*date_)
        df_ = get_historical_intraday(ticker, date=dat, output_format='pandas')
        dataframes.append(df_)
    returns = pd.concat(dataframes, axis=0)
    returns = pd.DataFrame({
        'High': returns['high'].values,
        'Low': returns['low'].values,
        'Open': returns['open'].values,
        'Close': returns['close'].values,
        'Volume': returns['volume'].values
    })
    return returns.dropna()


def anti_set_(seted):
    ret = [seted[0]]
    flag = seted[0]
    for e, i in enumerate(seted[1:]):
        if i is np.nan:
            ret.append(flag)
        else:
            ret.append(i)
            flag = i
    return ret


def move_stop_to_breakeven(stop, open, sig, price, diff, *args, **kwargs):
    if sig == 1 and price > open and diff > 0:
        stop_loss = (price + open) / 2
    elif sig == 0 and price < open and diff < 0:
        stop_loss = (price + open) / 2
    else:
        stop_loss = stop
    return stop_loss


def digit(data):
    data = list(data)
    ret = []
    for i in list(data):
        if i == 0:
            ret.append(2)
        elif i > 0:
            ret.append(1)
        else:
            ret.append(0)
    return ret


def get_window(values, window):
    ret = []
    for e, i in enumerate(values[:len(values) - window + 1]):
        ret.append(values[e:e + window])
    return ret


def nothing(ret):
    return ret