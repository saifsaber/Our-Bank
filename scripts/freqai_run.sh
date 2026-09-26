#!/usr/bin/env bash
# Reproduce the FreqAI experiment (see reports/freqai.md).
#
#   scripts/freqai_run.sh            # dev sweep + holdout (+ fee stress), then summary
#   scripts/freqai_run.sh --fresh    # also wipe cached FreqAI models/predictions first
#   STAGE=dev scripts/freqai_run.sh  # only the dev sweep   (STAGE=holdout: only holdout)
#
# Protocol
#   * Development period 2022-08-01 -> 2025-01-01. It starts in August 2022, not January,
#     because each walk-forward model is trained on the previous 180 days, plus
#     indicator startup candles, and the local data begins on 2022-01-01. FreqAI asks for
#     4520 x 1h startup candles, so loading starts around 2022-01-24.
#   * Dev sweep: entry_threshold in {0.006, 0.012, 0.020} (predicted 12h mean forward return),
#     fee 0.001. Selection rule (fixed before the sweep): highest total profit at fee 0.001
#     with at least 50 trades.
#   * Holdout 2025-01-01 -> 2026-09-25: CHOSEN_THR only, run once at fee 0.001 and once at
#     fee 0.002 as a stress test. The holdout uses its own FreqAI identifier, so it never reuses
#     dev models. Its first model is trained on 2024-07 -> 2024-12, which is earlier data, as
#     walk-forward training requires.
#   * FreqAI caches predictions per identifier (user_data/models/<identifier>). Re-runs with
#     only a different threshold or fee reuse the same walk-forward predictions, so every
#     setting sees the same model outputs.
set -euo pipefail
cd "$(dirname "$0")/.."

FT=.venv/bin/freqtrade
BASE_CFG=config/config.freqai.json
OUT=user_data/backtest_results/freqai
LOGDIR=user_data/logs/freqai
DEV_RANGE=20220801-20250101
HOLDOUT_RANGE=20250101-20260925
DEV_ID=lgbm-reg-v1-dev
HOLDOUT_ID=lgbm-reg-v1-holdout
DEV_THRESHOLDS=(0.006 0.012 0.020)
# Chosen on dev by the rule above (see reports/freqai.md). Do not change it after seeing
# holdout results.
CHOSEN_THR=${CHOSEN_THR:-0.020}
STAGE=${STAGE:-all}

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$OUT" "$LOGDIR"

if [[ "${1:-}" == "--fresh" ]]; then
  rm -rf "user_data/models/$DEV_ID" "user_data/models/$HOLDOUT_ID"
fi

tag() { echo "$1" | tr '.' 'p'; }   # 0.006 -> 0p006 (a dot would be read as a file suffix)

run() {  # run <name> <identifier> <timerange> <threshold> <fee>
  local name=$1 ident=$2 range=$3 thr=$4 fee=$5
  local ov="$TMP/$name.json" dir="$OUT/$name"
  printf '{"freqai_strategy": {"entry_threshold": %s, "exit_threshold": 0.0}, "freqai": {"identifier": "%s"}}\n' \
    "$thr" "$ident" > "$ov"
  rm -rf "$dir"; mkdir -p "$dir"
  echo ">>> $name  (identifier=$ident timerange=$range thr=$thr fee=$fee)"
  local t0=$SECONDS
  "$FT" backtesting -c "$BASE_CFG" -c "$ov" \
    --timerange "$range" --fee "$fee" \
    --cache none --export trades --backtest-directory "$dir" \
    > "$LOGDIR/$name.log" 2>&1
  echo "    done in $((SECONDS - t0)) s  (log: $LOGDIR/$name.log)"
  grep -A6 "STRATEGY SUMMARY" "$LOGDIR/$name.log" | tail -2 | head -1 || true
}

if [[ "$STAGE" == all || "$STAGE" == dev ]]; then
  for thr in "${DEV_THRESHOLDS[@]}"; do
    run "dev_thr$(tag "$thr")_fee0p001" "$DEV_ID" "$DEV_RANGE" "$thr" 0.001
  done
  # Fee stress on dev for the chosen threshold (information only)
  run "dev_thr$(tag "$CHOSEN_THR")_fee0p002" "$DEV_ID" "$DEV_RANGE" "$CHOSEN_THR" 0.002
fi

if [[ "$STAGE" == all || "$STAGE" == holdout ]]; then
  run "holdout_thr$(tag "$CHOSEN_THR")_fee0p001" "$HOLDOUT_ID" "$HOLDOUT_RANGE" "$CHOSEN_THR" 0.001
  run "holdout_thr$(tag "$CHOSEN_THR")_fee0p002" "$HOLDOUT_ID" "$HOLDOUT_RANGE" "$CHOSEN_THR" 0.002
fi

if [[ "$STAGE" == all || "$STAGE" == lookahead ]]; then
  # Look-ahead bias check on a short dev window, with a fresh identifier so nothing is
  # served from the prediction cache. Each checked signal triggers extra FreqAI backtests,
  # so the window is kept short. The 0.012 threshold is used only to get enough signals in
  # the window. lookahead-analysis forces market orders, which needs price_side "other".
  LA_ID=lgbm-reg-v1-lookahead
  rm -rf "user_data/models/$LA_ID"
  printf '{"freqai_strategy": {"entry_threshold": 0.012, "exit_threshold": 0.0}, "freqai": {"identifier": "%s"}, "entry_pricing": {"price_side": "other"}, "exit_pricing": {"price_side": "other"}}\n' \
    "$LA_ID" > "$TMP/la.json"
  mkdir -p "$OUT/../freqai_lookahead"
  echo ">>> lookahead-analysis (20240101-20240215)"
  t0=$SECONDS
  "$FT" lookahead-analysis -c "$BASE_CFG" -c "$TMP/la.json" \
    --timerange 20240101-20240215 --minimum-trade-amount 5 --targeted-trade-amount 10 \
    --backtest-directory "$OUT/../freqai_lookahead" \
    --lookahead-analysis-exportfilename reports/freqai_lookahead.csv \
    > "$LOGDIR/lookahead.log" 2>&1
  echo "    done in $((SECONDS - t0)) s  (log: $LOGDIR/lookahead.log)"
  grep -B2 -A6 "has_bias" "$LOGDIR/lookahead.log" || tail -5 "$LOGDIR/lookahead.log"
fi

.venv/bin/python scripts/freqai_summarize.py "$OUT"
