"""
FreqAIStrategy - long-only spot strategy driven by a FreqAI LightGBM regressor.

How it works
------------
* Target (label): mean close over the next `label_period_candles` (1h) candles divided by the
  current close, minus 1  -> "expected average forward return". Rows whose label would need
  candles after the end of a training window are NaN and are dropped by FreqAI, so training
  never sees prices from the prediction window.
* Features: stationary-ish transforms only (oscillators, returns, volatility, volume ratios,
  EMA / Bollinger distances, calendar). Unlike the FreqAI example we do NOT feed raw price or
  raw volume, which are non-stationary and let a tree model memorise price levels.
  FreqAI expands each `%-` feature over indicator periods x timeframes (1h, 4h) x
  correlated pairs (BTC, ETH) x 1 shifted candle.
* Model: retrained walk-forward every `backtest_period_days` on the previous
  `train_period_days` (see config/config.freqai.json).
* Entry: prediction > entry_threshold AND do_predict == 1 (SVM outlier filter says the
  current candle looks like the training data).
* Exit: prediction < exit_threshold (default 0), hard stoploss -8%. No ROI table.

Thresholds are read from the top-level config key
    "freqai_strategy": {"entry_threshold": 0.006, "exit_threshold": 0.0}
so they can be changed per run with an extra --config file without touching FreqAI's
identifier (cached predictions are then reused, which makes threshold sweeps cheap).

This is research code for backtesting / dry-run only.
"""

import logging

import numpy as np
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


logger = logging.getLogger(__name__)


class FreqAIStrategy(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False
    process_only_new_candles = True

    # Exits are driven by the model; ROI disabled, fixed catastrophic stop.
    minimal_roi = {"0": 100.0}
    stoploss = -0.08
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False

    # Largest indicator period is 32 on the 4h timeframe = 128 1h candles; keep a margin.
    startup_candle_count: int = 200

    plot_config = {
        "main_plot": {},
        "subplots": {
            "prediction": {"&-fwd_ret": {"color": "blue"}},
            "do_predict": {"do_predict": {"color": "brown"}},
        },
    }

    # ------------------------------------------------------------------ helpers
    def _thr(self, key: str, default: float) -> float:
        return float(self.config.get("freqai_strategy", {}).get(key, default))

    # --------------------------------------------------------- feature engineering
    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
        """Expanded over indicator_periods_candles x timeframes x corr pairs x shifts."""
        close = dataframe["close"]
        ret = close.pct_change()

        dataframe["%-rsi-period"] = ta.RSI(dataframe, timeperiod=period)
        dataframe["%-mfi-period"] = ta.MFI(dataframe, timeperiod=period)
        dataframe["%-adx-period"] = ta.ADX(dataframe, timeperiod=period)
        # Return over the period (momentum)
        dataframe["%-roc-period"] = close / close.shift(period) - 1
        # Realised volatility of 1-candle returns
        dataframe["%-vol-period"] = ret.rolling(period).std()
        # Volume relative to its own rolling mean
        dataframe["%-relvol-period"] = dataframe["volume"] / (
            dataframe["volume"].rolling(period).mean() + 1e-12
        )
        # Distance from EMA, normalised by price
        ema = ta.EMA(dataframe, timeperiod=period)
        dataframe["%-ema_dist-period"] = close / ema - 1
        # Position inside a rolling high/low channel (0 = at low, 1 = at high)
        hh = dataframe["high"].rolling(period).max()
        ll = dataframe["low"].rolling(period).min()
        dataframe["%-chan_pos-period"] = (close - ll) / (hh - ll + 1e-12)
        return dataframe

    def feature_engineering_expand_basic(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """Expanded over timeframes x corr pairs x shifts (not over periods)."""
        dataframe["%-ret_1"] = dataframe["close"].pct_change()
        dataframe["%-range_pct"] = (dataframe["high"] - dataframe["low"]) / dataframe["close"]
        dataframe["%-body_pct"] = (dataframe["close"] - dataframe["open"]) / dataframe["open"]
        dataframe["%-logvol_chg"] = np.log1p(dataframe["volume"]).diff()
        return dataframe

    def feature_engineering_standard(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """Base timeframe only; calendar features encoded cyclically."""
        dow = dataframe["date"].dt.dayofweek
        hour = dataframe["date"].dt.hour
        dataframe["%-dow_sin"] = np.sin(2 * np.pi * dow / 7)
        dataframe["%-dow_cos"] = np.cos(2 * np.pi * dow / 7)
        dataframe["%-hour_sin"] = np.sin(2 * np.pi * hour / 24)
        dataframe["%-hour_cos"] = np.cos(2 * np.pi * hour / 24)
        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """&-fwd_ret[t] = mean(close[t+1 .. t+L]) / close[t] - 1  (NaN for the last L rows)."""
        label_len = self.freqai_info["feature_parameters"]["label_period_candles"]
        fwd_mean = dataframe["close"].shift(-label_len).rolling(label_len).mean()
        dataframe["&-fwd_ret"] = fwd_mean / dataframe["close"] - 1
        return dataframe

    # ------------------------------------------------------------------ signals
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # All feature engineering, training and prediction is handled by FreqAI.
        dataframe = self.freqai.start(dataframe, metadata, self)
        return dataframe

    def populate_entry_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        thr = self._thr("entry_threshold", 0.006)
        cond = (df["do_predict"] == 1) & (df["&-fwd_ret"] > thr) & (df["volume"] > 0)
        df.loc[cond, ["enter_long", "enter_tag"]] = (1, "ai_long")
        return df

    def populate_exit_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        thr = self._thr("exit_threshold", 0.0)
        df.loc[df["&-fwd_ret"] < thr, ["exit_long", "exit_tag"]] = (1, "ai_neg")
        return df
