"""
EmaCrossBaseline -- simple trend-following baseline (spot, long only, 1h).

Purpose: a deliberately simple, *non-optimised* reference strategy that any
smarter model (e.g. FreqAI) must beat after costs. Parameters are textbook
values chosen a priori; they were NOT hyperopted and were NOT tuned on the
evaluation (holdout) period.

Rules
-----
Entry (all on the closed candle):
  * EMA(20) crosses above EMA(50)          -> short-term momentum turns up
  * close > EMA(200)                       -> only trade with the long-term trend
  * volume > 0                             -> skip empty candles
Exit:
  * EMA(20) crosses below EMA(50)
Risk:
  * fixed stoploss -8%, no ROI table (minimal_roi is effectively disabled),
    no trailing stop.
"""

from pandas import DataFrame

import talib.abstract as ta
from freqtrade.strategy import IStrategy
from technical import qtpylib


class EmaCrossBaseline(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False

    # No ROI tricks: a single, unreachable ROI target => exits are signal/stoploss only.
    minimal_roi = {"0": 100.0}
    stoploss = -0.08
    trailing_stop = False

    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # EMA(200) needs a long warm-up; 2-3x the period makes the EMA converge.
    startup_candle_count: int = 400

    # A priori parameters (not optimised).
    ema_fast = 20
    ema_slow = 50
    ema_trend = 200

    # Default (limit) order types are kept so the shared config
    # (entry/exit price_side = "same") validates. In backtesting, signals from a
    # closed candle are filled at the OPEN of the next candle either way.

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.ema_fast)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=self.ema_slow)
        dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=self.ema_trend)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                qtpylib.crossed_above(dataframe["ema_fast"], dataframe["ema_slow"])
                & (dataframe["close"] > dataframe["ema_trend"])
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "ema_cross_up")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                qtpylib.crossed_below(dataframe["ema_fast"], dataframe["ema_slow"])
                & (dataframe["volume"] > 0)
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "ema_cross_down")
        return dataframe
