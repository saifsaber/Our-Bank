#!/usr/bin/env bash
# Look-ahead and recursive-formula bias checks for strategies.
#
#   scripts/run_lookahead.sh [STRATEGY ...]
#
# Defaults to the three rule-based baselines. Runs only on the DEVELOPMENT
# period (never the holdout). Outputs go to reports/lookahead/:
#   <Strategy>_lookahead.csv   -- freqtrade lookahead-analysis export
#   <Strategy>_recursive.txt   -- freqtrade recursive-analysis table
# scripts/summarize.py --lookahead-dir reports/lookahead picks these up.
#
# lookahead-analysis forces market orders, which requires price_side "other";
# config/config.lookahead-override.json layers that on top of the base config.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FT=".venv/bin/freqtrade"
CONFIG="config/config.backtest.json"
OVERRIDE="config/config.lookahead-override.json"
OUT="reports/lookahead"
LOOKAHEAD_TR="${LOOKAHEAD_TR:-20220101-20250101}"   # full dev period
RECURSIVE_TR="${RECURSIVE_TR:-20240101-20240701}"   # short dev window is enough
LOGS="user_data/logs/lookahead"
mkdir -p "$OUT" "$LOGS"

if [[ $# -gt 0 ]]; then
  STRATEGIES=("$@")
else
  STRATEGIES=(EmaCrossBaseline RsiMeanReversionBaseline DonchianBreakoutBaseline)
fi

for s in "${STRATEGIES[@]}"; do
  echo "=== lookahead-analysis ${s} (${LOOKAHEAD_TR})"
  rm -f "${OUT}/${s}_lookahead.csv"
  "$FT" lookahead-analysis -c "$CONFIG" -c "$OVERRIDE" -s "$s" \
    --timerange "$LOOKAHEAD_TR" \
    --minimum-trade-amount 10 --targeted-trade-amount 60 \
    --lookahead-analysis-exportfilename "${OUT}/${s}_lookahead.csv" \
    > "${LOGS}/${s}_lookahead.log" 2>&1 || { echo "lookahead failed, see ${LOGS}/${s}_lookahead.log"; }
  tail -n 6 "${LOGS}/${s}_lookahead.log"

  echo "=== recursive-analysis ${s} (${RECURSIVE_TR})"
  "$FT" recursive-analysis -c "$CONFIG" -s "$s" --no-color \
    --timerange "$RECURSIVE_TR" --startup-candle 199 499 999 \
    > "${LOGS}/${s}_recursive.log" 2>&1 || { echo "recursive failed, see ${LOGS}/${s}_recursive.log"; }
  # Keep only the result table.
  awk '/Recursive Analysis/{p=1} p' "${LOGS}/${s}_recursive.log" > "${OUT}/${s}_recursive.txt"
  cat "${OUT}/${s}_recursive.txt"
done
