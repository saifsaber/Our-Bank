"""
DonchianBreakoutBaseline -- classic channel-breakout trend follower (spot, long only, 1h).

Purpose: a deliberately simple, *non-optimised* reference strategy in the
spirit of the Turtle rules (enter on an N-period high, exit on an M-period
low, M < N). Values chosen a priori, NOT hyperopted, NOT tuned on the holdout.

On 1h candles: N = 55 bars (~2.3 days), M = 20 bars (~0.8 days) -- the
original Turtle "System 2" lengths, simply applied to the 1h bar.

Rules
-----
Entry (closed candle):
  * close > highest high of the PREVIOUS 55 candles (current candle excluded,
    via shift(1) -> no look-ahead)
  * close > EMA(200) trend filter
  * volume > 0
Exit:
  * close < lowest low of the PREVIOUS 20 candles
Risk:
  * fixed stoploss -10% (wider, since breakouts are volatile), no ROI table,
    no trailing stop.
"""

from pandas import DataFrame

import talib.abstract as ta
from freqtrade.strategy import IStrategy


class DonchianBreakoutBaseline(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False

    minimal_roi = {"0": 100.0}  # effectively disabled
    stoploss = -0.10
    trailing_stop = False

    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    startup_candle_count: int = 400

    # A priori parameters (not optimised).
    entry_period = 55
    exit_period = 20
    ema_trend = 200

    # Default (limit) order types are kept so the shared config
    # (entry/exit price_side = "same") validates. In backtesting, signals from a
    # closed candle are filled at the OPEN of the next candle either way.

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # shift(1): channel built only from *completed prior* candles.
        dataframe["dc_upper"] = dataframe["high"].rolling(self.entry_period).max().shift(1)
        dataframe["dc_lower"] = dataframe["low"].rolling(self.exit_period).min().shift(1)
        dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=self.ema_trend)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] > dataframe["dc_upper"])
                & (dataframe["close"] > dataframe["ema_trend"])
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "donchian_breakout")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["dc_lower"])
                & (dataframe["volume"] > 0)
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "donchian_breakdown")
        return dataframe
