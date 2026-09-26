# FreqAI LightGBM strategy: walk-forward evaluation

**Result:** after costs, the strategy made no real money. On the untouched 2025-01-01 → 2026-09-25 holdout it made **+0.14 %** at a 0.1 % fee and **-2.66 %** at a 0.2 % fee. Profit factor was 1.00 and 0.93, and the worst drawdown was about 18 %. Over the same period buy-and-hold of the 3 coins lost 23 % and cash made 0 %. So the strategy beat buy-and-hold only because it stayed in cash most of the time. It showed no edge over cash. In development (2022-08 → 2024-12) it made +5.8 % while buy-and-hold made +251 %.

Everything here is a backtest on OKX spot data, used as a proxy for Bybit. It is not investment advice and does not promise any return.

## Files

| file | purpose |
|---|---|
| `config/config.freqai.json` | FreqAI config. It extends `config.backtest.json` through `add_config_files` |
| `strategies/FreqAIStrategy.py` | IStrategy v3 on 1h spot, long only |
| `scripts/freqai_run.sh` | runs everything again: dev sweep, holdout, fee stress, lookahead-analysis and the summary. `--fresh` wipes cached models |
| `scripts/freqai_summarize.py` | builds the results table from freqtrade's result zips |
| `user_data/backtest_results/freqai/<run>/` | freqtrade results for each run (`--export trades`) |
| `user_data/logs/freqai/<run>.log` | full freqtrade output for each run |
| `reports/freqai_lookahead.csv` | lookahead-analysis output |

## Config summary

- **Model:** `LightGBMRegressor` with 300 trees, learning rate 0.03, 15 leaves, min_child_samples 50, subsample 0.8, colsample 0.5, L2 1.0, `random_state` 42 and 4 threads. A regressor was chosen because the target is continuous. Its size is the entry signal, so a threshold sweep is possible without retraining.
- **Walk-forward:** `train_period_days` 180 and `backtest_period_days` 30. Every 30 days the model is retrained on the previous 180 days and then predicts the next 30 days. The dev period needs 30 trainings per pair and the holdout needs 22. `live_retrain_hours` is 24 (used for dry-run only).
- **Split:** `data_split_parameters` uses `test_size` 0.1 and `shuffle` false, so the most recent 10 % of each training window is used only for the eval metric. `weight_factor` 0.9 weights recent rows more.
- **Features:**
  - `include_timeframes` ["1h","4h"], `include_corr_pairlist` [BTC/USDT, ETH/USDT], `indicator_periods_candles` [8,16,32] and `include_shifted_candles` 1.
  - Each period gets RSI, MFI, ADX, ROC, realised volatility, relative volume, distance to the EMA, and the close's position inside the high/low channel.
  - Basic features: 1-candle return, high-low range, candle body and log-volume change.
  - Calendar: sine/cosine of day of week and of hour.
  - Raw price and raw volume are left out on purpose because they are non-stationary.
  - This gives 228 features for BTC and ETH and 340 for SOL.
- **Outliers:** `use_SVM_to_remove_outliers` is on with nu 0.05. The SVM drops training outliers and sets `do_predict` to 0 on unusual candles, which happens on about 5 % of candles. `DI_threshold` is 0 (off) to save compute.
- **Label:** `&-fwd_ret` = mean(close[t+1..t+12]) / close[t] − 1, so `label_period_candles` is 12. FreqAI builds the targets of each training window only from candles before that window ends, and it drops the last 12 rows because their label is NaN. The label therefore never uses prices from the prediction window. This comes from `freqai_interface.py`, where the training frame is sliced to `date < train_stop` before `set_freqai_targets` runs.
- **Trading rules:**
  - Enter when `do_predict == 1` and the prediction is above `entry_threshold`.
  - Exit when the prediction is below 0.
  - Stoploss is -8 %. ROI is off.
  - Wallet is 100 USDT, `max_open_trades` is 3 and the stake is unlimited (about 33 USDT per trade).

## Protocol and time split

| period | range | notes |
|---|---|---|
| development | 2022-08-01 → 2025-01-01 | Starts in August, not January. Local data begins on 2022-01-01, and the first model needs 180 days of training plus indicator startup. FreqAI asks for 4520 × 1h startup candles, so data loads from 2022-01-24. The first model is trained on 2022-02-02 → 2022-08-01. |
| holdout | 2025-01-01 → 2026-09-25 | Run once with the chosen setting, at fee 0.001 and again at fee 0.002 as a stress test. It has its own FreqAI identifier. Its first model is trained on 2024-07-05 → 2025-01-01, which is earlier data, as walk-forward requires. |

**What was tuned on dev:** only `entry_threshold`, with 3 values. The grid {0.006, 0.012, 0.020} was set from the dev prediction distribution. The 80th, 90th and 95th percentiles of the dev predictions are 0.0054, 0.0091 and 0.0128. Nothing else was tuned: the model parameters, features, label length, exit rule and stoploss were fixed before the sweep. The selection rule was also set before the sweep: pick the highest dev total profit at fee 0.001 among settings with at least 50 trades. **Chosen: `entry_threshold` = 0.020.** The holdout was then run once with it. The dev and holdout runs were later repeated with `--fresh` only to check reproducibility, and the numbers were identical.

## Results

All numbers come from freqtrade's backtest result JSON (`scripts/freqai_summarize.py`). "Market change" is freqtrade's average buy-and-hold change of the 3 pairs over the period. Holding cash returns 0 %.

| run | period | fee | trades | total profit % | max DD % | win rate % | profit factor | buy & hold % |
|---|---|---|---|---|---|---|---|---|
| dev, thr 0.006 | 2022-08-01 → 2025-01-01 | 0.001 | 1007 | -21.96 | 39.02 | 55.3 | 0.93 | +250.85 |
| dev, thr 0.012 | 2022-08-01 → 2025-01-01 | 0.001 | 365 | +2.35 | 21.72 | 55.1 | 1.01 | +250.85 |
| **dev, thr 0.020 (chosen)** | 2022-08-01 → 2025-01-01 | 0.001 | 115 | **+5.77** | 11.99 | 53.9 | 1.08 | +250.85 |
| dev, thr 0.020 | 2022-08-01 → 2025-01-01 | 0.002 | 115 | -1.97 | 13.30 | 52.2 | 0.97 | +250.85 |
| **holdout, thr 0.020** | 2025-01-01 → 2026-09-25 | 0.001 | 43 | **+0.14** | 17.53 | 58.1 | 1.00 | -23.14 |
| **holdout, thr 0.020** | 2025-01-01 → 2026-09-25 | 0.002 | 43 | **-2.66** | 18.19 | 58.1 | 0.93 | -23.14 |

Other details:
- **Holdout at fee 0.001:**
  - CAGR is 0.08 % and daily Sharpe is 0.05.
  - Exits on a negative prediction: 32 trades, +32.3 USDT. Stoploss exits: 11 trades, -32.1 USDT.
  - By pair: SOL +4.6 USDT, BTC +0.7 USDT, ETH -5.1 USDT.
- **Dev at threshold 0.020:** SOL made 99 of the 115 trades.
- **Signal quality:** win rates are about 55 %, but the -8 % stoploss losses cancel the wins. Lower thresholds trade more and lose to fees.

## Look-ahead check

`freqtrade lookahead-analysis` ran on 2024-01-01 → 2024-02-15. It used a fresh identifier so no cached predictions were involved, and threshold 0.012 only to get enough signals. It took about 48 s.
- Result: 10 signals checked, **0 biased entry signals and 0 biased exit signals**.
- The tool still prints `has_bias = Yes`, flagging the prediction and target columns (`&-fwd_ret*` and `do_predict`) and the derived signal columns.
- The log shows why: in the shortened re-runs, the last candle has no FreqAI prediction yet (`0.0106 != 0.0`, `do_predict 1.0 != 0.0`). The difference is "a value against an empty 0", not "a different value". freqtrade's own note also says to ignore columns used in `set_freqai_targets()`.
- So the tool does not fit FreqAI predictions well. The stronger evidence against look-ahead is how FreqAI builds its windows:
  - Each model is trained only on candles before its prediction window. The logs show a training stop equal to the backtest window start, for example "Training ... from 2024-07-05 to 2025-01-01" for the January 2025 window.
  - Labels are computed on the truncated training frame.
  - All features are backward-looking rolling or TA-Lib values.

## Runtime (4 CPUs)

| step | time |
|---|---|
| dev backtest with training (90 model fits) | about 1.7 min (4 min on a first run while another agent was using the CPUs) |
| holdout backtest with training (66 fits) | about 75 s |
| each re-run with cached predictions (other threshold or fee) | 7-9 s |
| lookahead-analysis | about 48 s |
| full `scripts/freqai_run.sh --fresh` | 4 min 15 s |

## Caveats

- **No edge after costs.** The holdout result at fee 0.001 is break-even (profit factor 1.00) and turns negative at fee 0.002. The +5.8 % on dev was the best of 3 thresholds, so it is optimistic in-sample, and it did not carry over to the holdout.
- **It does not beat buy-and-hold in bull markets.** In dev it made +5.8 % while buy-and-hold made +251 %. The better holdout comparison (-23 % for buy-and-hold) comes from being in cash most of the time, not from skill. Cash (0 %) did just as well at lower risk.
- **Small sample.** The holdout has 43 trades, so the confidence interval on the profit easily includes clearly negative outcomes. The result depends heavily on a single pair (SOL), and each stoploss costs about 8 %.
- **Fills are optimistic.** Slippage is not modelled beyond the fee. This is spot only, so there is no funding cost. OKX data stands in for Bybit.
- **Environment fix.** The venv had joblib 1.6.0, which no longer ships `joblib.externals.cloudpickle`, and FreqAI imports it. joblib was downgraded to 1.5.3 in `.venv` (`pip install "joblib<1.6"`). Without this, FreqAI crashes on import.
- **Cached predictions.** They are keyed by identifier in `user_data/models/<identifier>/`. If you change features or model parameters, bump the identifier or use `--fresh`, otherwise old predictions are reused.
- **Possible next steps, none of them tested here.** A wider stop or a volatility-scaled stop, a classifier on "12h return > fees", DI_threshold, or more pairs to get a larger sample. Any of these would need a new, untouched holdout, because this one has now been seen.
