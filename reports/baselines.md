# Rule-based baselines (spot, long only, 1h, BTC/ETH/SOL, OKX data)

_Generated 2026-09-26 21:40 UTC by `scripts/summarize.py`. Price data: `user_data/data/okx`._

## Setup

- **Strategies** (`strategies/`, IStrategy v3, spot, long only, 1h, parameters fixed a priori, no hyperopt, no ROI table, no trailing stop):
  - `EmaCrossBaseline`: enter on EMA(20) crossing above EMA(50) while close > EMA(200); exit on the opposite cross; stoploss -8%.
  - `RsiMeanReversionBaseline`: enter when RSI(14) crosses back above 30 while close > EMA(200); exit when RSI(14) crosses above 60; stoploss -8%.
  - `DonchianBreakoutBaseline`: enter when close breaks the previous 55-bar high while close > EMA(200); exit when close breaks the previous 20-bar low; stoploss -10%.
- **Fixed time split** (set before any result was seen; the holdout was never used to choose anything):
  - development: 2022-01-01 -> 2024-12-31 (timerange `20220101-20250101`, end exclusive)
  - evaluation / holdout: 2025-01-01 -> 2026-09-25 (timerange `20250101-20260926`, end exclusive)
- **Account**: 100 USDT, `stake_amount: unlimited`, `max_open_trades: 3` (so each position is about 1/3 of equity and profits compound), BTC/USDT, ETH/USDT, SOL/USDT.
- **Costs**: fee 0.10% per side (base) and 0.20% per side (stress: fee + slippage proxy). Entries and exits fill at the next candle's open.
- **Data**: OKX spot 1h candles, used as a stand-in for Bybit (Bybit's API is geo-blocked from the machine that ran this).

## Period: dev

Backtested window: **2022-01-17 16:00 -> 2025-01-01 00:00 UTC** (timerange `20220101-20250101`; start may be later than requested because of the strategies' indicator warm-up), timeframe 1h, pairs: BTC/USDT, ETH/USDT, SOL/USDT, starting balance 100 USDT, max_open_trades 3.

| Strategy | Fee/side | Trades | Total profit % | CAGR % | Max DD % (MtM) | Max DD % (closed) | Win rate | Profit factor | Avg trade % | vs B&H (pp) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DonchianBreakoutBaseline | 0.10% | 467 | +28.4% | +8.8% | 36.7% | 34.1% | 35.1% | 1.11 | +0.25% | -23.5 |
| EmaCrossBaseline | 0.10% | 404 | +276.3% | +56.6% | 23.9% | 19.1% | 33.9% | 1.71 | +1.15% | +224.4 |
| RsiMeanReversionBaseline | 0.10% | 77 | -24.6% | -9.1% | 26.0% | 25.8% | 57.1% | 0.57 | -1.05% | -76.5 |
| DonchianBreakoutBaseline | 0.20% | 467 | -5.5% | -1.9% | 41.2% | 40.1% | 33.4% | 0.98 | +0.05% | -57.1 |
| EmaCrossBaseline | 0.20% | 404 | +189.0% | +43.2% | 29.1% | 24.3% | 32.7% | 1.52 | +0.94% | +137.4 |
| RsiMeanReversionBaseline | 0.20% | 77 | -28.3% | -10.7% | 28.6% | 28.3% | 53.2% | 0.51 | -1.25% | -79.9 |
| _Buy & hold, equal-weight_ | 0.10% | 3 | +51.9% | +15.2% | 75.4% | n/a | n/a | n/a | n/a | 0.0 |
| _Buy & hold, equal-weight_ | 0.20% | 3 | +51.6% | +15.1% | 75.4% | n/a | n/a | n/a | n/a | 0.0 |
| _Cash_ | - | 0 | 0.0% | 0.0% | 0.0% | 0.0% | n/a | n/a | n/a | -51.9 |

## Period: eval

Backtested window: **2025-01-01 00:00 -> 2026-09-26 00:00 UTC** (timerange `20250101-20260926`; start may be later than requested because of the strategies' indicator warm-up), timeframe 1h, pairs: BTC/USDT, ETH/USDT, SOL/USDT, starting balance 100 USDT, max_open_trades 3.

| Strategy | Fee/side | Trades | Total profit % | CAGR % | Max DD % (MtM) | Max DD % (closed) | Win rate | Profit factor | Avg trade % | vs B&H (pp) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DonchianBreakoutBaseline | 0.10% | 290 | -25.5% | -15.6% | 48.1% | 43.9% | 30.3% | 0.81 | -0.23% | -3.7 |
| EmaCrossBaseline | 0.10% | 272 | -26.3% | -16.1% | 40.3% | 36.8% | 27.2% | 0.80 | -0.27% | -4.5 |
| RsiMeanReversionBaseline | 0.10% | 46 | +2.5% | +1.4% | 8.4% | 6.8% | 69.6% | 1.17 | +0.18% | +24.3 |
| DonchianBreakoutBaseline | 0.20% | 290 | -38.5% | -24.4% | 56.4% | 52.6% | 29.0% | 0.72 | -0.43% | -16.5 |
| EmaCrossBaseline | 0.20% | 272 | -38.3% | -24.3% | 45.5% | 43.5% | 25.4% | 0.71 | -0.47% | -16.4 |
| RsiMeanReversionBaseline | 0.20% | 46 | -0.6% | -0.3% | 9.4% | 7.7% | 67.4% | 0.96 | -0.02% | +21.4 |
| _Buy & hold, equal-weight_ | 0.10% | 3 | -21.8% | -13.2% | 64.6% | n/a | n/a | n/a | n/a | 0.0 |
| _Buy & hold, equal-weight_ | 0.20% | 3 | -22.0% | -13.3% | 64.6% | n/a | n/a | n/a | n/a | 0.0 |
| _Cash_ | - | 0 | 0.0% | 0.0% | 0.0% | 0.0% | n/a | n/a | n/a | +21.8 |

## Market regime of each period (buy-and-hold)

Per-asset returns are gross (open of first candle -> close of last). Portfolio return is equal-weight and net of the first fee level. Regime label: > +20% bull, < -20% bear, otherwise sideways.

| Period | Window | Per-asset return | Portfolio (net) | Portfolio max DD | Regime |
|---|---|---|---:|---:|---|
| dev | 2022-01-17 -> 2025-01-01 | BTC/USDT +120.3%, ETH/USDT +3.1%, SOL/USDT +33.2% | +51.9% | 75.4% | bull |
|  | by calendar year (gross) | 2022: -72% (bear); 2023: +389% (bull); 2024: +85% (bull) | | | |
| eval | 2025-01-01 -> 2026-09-26 | BTC/USDT -10.1%, ETH/USDT -19.3%, SOL/USDT -35.5% | -21.8% | 64.6% | bear |
|  | by calendar year (gross) | 2025: -17% (sideways); 2026: -5% (sideways) | | | |

## Bias checks

### Look-ahead analysis (`freqtrade lookahead-analysis`)

| strategy | has bias | signals checked | biased entries | biased exits | biased indicators |
|---|---|---:|---:|---:|---|
| DonchianBreakoutBaseline | no | 60 | 0 | 0 | - |
| EmaCrossBaseline | no | 60 | 0 | 0 | - |
| RsiMeanReversionBaseline | no | 60 | 0 | 0 | - |

### Recursive-formula analysis (`freqtrade recursive-analysis`)

Relative difference of the last indicator values between runs with different startup-candle counts (`-` = no difference). Values near 0% at the strategy's own `startup_candle_count` mean indicators have converged (no warm-up bias).

**DonchianBreakoutBaseline**

```
Recursive Analysis                       
┏━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┓
┃ Indicators ┃     199 ┃ 400 (from strategy) ┃    499 ┃    999 ┃
┡━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━┩
│  ema_trend │ -0.396% │             -0.009% │ 0.007% │ 0.000% │
└────────────┴─────────┴─────────────────────┴────────┴────────┘
```

**EmaCrossBaseline**

```
Recursive Analysis                       
┏━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┓
┃ Indicators ┃     199 ┃ 400 (from strategy) ┃    499 ┃    999 ┃
┡━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━┩
│   ema_fast │ -0.000% │                   - │      - │      - │
│   ema_slow │  0.002% │             -0.000% │ 0.000% │      - │
│  ema_trend │ -0.396% │             -0.009% │ 0.007% │ 0.000% │
└────────────┴─────────┴─────────────────────┴────────┴────────┘
```

**RsiMeanReversionBaseline**

```
Recursive Analysis                       
┏━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┓
┃ Indicators ┃     199 ┃ 400 (from strategy) ┃    499 ┃    999 ┃
┡━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━┩
│        rsi │  0.000% │             -0.000% │      - │      - │
│  ema_trend │ -0.396% │             -0.009% │ 0.007% │ 0.000% │
└────────────┴─────────┴─────────────────────┴────────┴────────┘
```

## Caveats

- The development period starts about 2.5 weeks late (2022-01-17) because the EMA(200) warm-up (400 candles) is taken from the start of the downloaded data. The buy-and-hold benchmark uses the same window.
- Buy-and-hold is equal-weight with no rebalancing; the per-year breakdown excludes fees.
- These are small samples (46 to 467 trades per run) and one fixed split. A single good or bad period says little. The development period (2022 crash, then the 2023/24 rally, SOL up about 10x in 2023) is very different from the holdout.
- A backtest does not model partial fills, outages, or exchange differences between OKX and Bybit. The 0.20% fee run is only a rough proxy for slippage.
- Nothing here is a promise of future returns.

## Notes on metrics

- *Total profit %*: whole-account return on the starting balance (open trades are force-closed at the end of the backtest).
- *Max DD % (MtM)*: largest peak-to-trough fall of the mark-to-market wallet; *closed*: same on closed-trade equity only. Buy-and-hold DD uses hourly closes.
- *vs B&H (pp)*: strategy total profit minus buy-and-hold total profit at the same fee, in percentage points.
- Fees are applied on entry and exit. The higher fee level is a crude fee + slippage stress test; spot trading has no funding costs.

Sources:

- `user_data/backtest_results/baselines/dev_fee0.001/backtest-result-2026-09-26_21-39-35.zip`
- `user_data/backtest_results/baselines/dev_fee0.002/backtest-result-2026-09-26_21-39-47.zip`
- `user_data/backtest_results/baselines/eval_fee0.001/backtest-result-2026-09-26_21-39-56.zip`
- `user_data/backtest_results/baselines/eval_fee0.002/backtest-result-2026-09-26_21-40-06.zip`
