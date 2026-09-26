"""
RsiMeanReversionBaseline -- "buy the dip in an uptrend" baseline (spot, long only, 1h).

Purpose: a deliberately simple, *non-optimised* reference strategy. Parameters
are the classic textbook RSI values chosen a priori; they were NOT hyperopted
and were NOT tuned on the evaluation (holdout) period.

Rules
-----
Entry (closed candle):
  * RSI(14) crosses above 30 (i.e. was oversold, now turning back up)
  * close > EMA(200)          -> only buy dips inside a long-term uptrend
  * volume > 0
Exit:
  * RSI(14) crosses above 60  -> the bounce has happened, take it
Risk:
  * fixed stoploss -8%, no ROI table, no trailing stop.
  * No time-based exit: a failed dip either recovers (RSI > 60) or hits the stop.
"""

from pandas import DataFrame

import talib.abstract as ta
from freqtrade.strategy import IStrategy
from technical import qtpylib


class RsiMeanReversionBaseline(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False

    minimal_roi = {"0": 100.0}  # effectively disabled
    stoploss = -0.08
    trailing_stop = False

    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    startup_candle_count: int = 400

    # A priori parameters (not optimised).
    rsi_period = 14
    rsi_entry = 30
    rsi_exit = 60
    ema_trend = 200

    # Default (limit) order types are kept so the shared config
    # (entry/exit price_side = "same") validates. In backtesting, signals from a
    # closed candle are filled at the OPEN of the next candle either way.

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=self.rsi_period)
        dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=self.ema_trend)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                qtpylib.crossed_above(dataframe["rsi"], self.rsi_entry)
                & (dataframe["close"] > dataframe["ema_trend"])
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "rsi_oversold_rebound")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                qtpylib.crossed_above(dataframe["rsi"], self.rsi_exit)
                & (dataframe["volume"] > 0)
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "rsi_recovered")
        return dataframe
