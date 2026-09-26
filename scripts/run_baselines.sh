#!/usr/bin/env bash
# Backtest every rule-based baseline on the fixed development and evaluation
# (holdout) periods, at the base fee (0.1%/side) and a stress fee (0.2%/side,
# used as a fee + slippage proxy). Then build reports/baselines.md.
#
# Fixed time split (never change after looking at holdout results):
#   dev  : 2022-01-01 00:00 -> 2024-12-31 23:00 UTC   (timerange 20220101-20250101)
#   eval : 2025-01-01 00:00 -> 2026-09-25 23:00 UTC   (timerange 20250101-20260926)
# Freqtrade timerange end dates are exclusive, hence the "+1 day" end values.
#
# Usage:  scripts/run_baselines.sh            # backtests + report
#         SKIP_BACKTEST=1 scripts/run_baselines.sh   # report only
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FT=".venv/bin/freqtrade"
PY=".venv/bin/python"
CONFIG="config/config.backtest.json"
STRATEGIES=(EmaCrossBaseline RsiMeanReversionBaseline DonchianBreakoutBaseline)
OUT_BASE="user_data/backtest_results/baselines"

declare -A PERIODS=(
  [dev]="20220101-20250101"
  [eval]="20250101-20260926"
)
FEES=(0.001 0.002)

if [[ "${SKIP_BACKTEST:-0}" != "1" ]]; then
  for period in dev eval; do
    tr="${PERIODS[$period]}"
    for fee in "${FEES[@]}"; do
      outdir="${OUT_BASE}/${period}_fee${fee}"
      mkdir -p "$outdir"
      # Remove stale results so the summary only sees the latest run.
      rm -f "$outdir"/backtest-result-* "$outdir"/.last_result.json
      echo "=== period=${period} timerange=${tr} fee=${fee} -> ${outdir}"
      "$FT" backtesting \
        --config "$CONFIG" \
        --strategy-list "${STRATEGIES[@]}" \
        --timerange "$tr" \
        --fee "$fee" \
        --export trades \
        --backtest-directory "$outdir" \
        --cache none \
        --notes "baselines period=${period} fee=${fee}"
    done
  done
fi

# Look-ahead / recursive checks (dev period only) are run separately:
#   scripts/run_lookahead.sh      -> reports/lookahead/*
# The summary picks up whatever is in reports/lookahead/.

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/preamble.md" <<'EOF'
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
EOF

cat > "$TMP/epilogue.md" <<'EOF'
## Caveats

- The development period starts about 2.5 weeks late (2022-01-17) because the EMA(200) warm-up (400 candles) is taken from the start of the downloaded data. The buy-and-hold benchmark uses the same window.
- Buy-and-hold is equal-weight with no rebalancing; the per-year breakdown excludes fees.
- These are small samples (46 to 467 trades per run) and one fixed split. A single good or bad period says little. The development period (2022 crash, then the 2023/24 rally, SOL up about 10x in 2023) is very different from the holdout.
- A backtest does not model partial fills, outages, or exchange differences between OKX and Bybit. The 0.20% fee run is only a rough proxy for slippage.
- Nothing here is a promise of future returns.
EOF

"$PY" scripts/summarize.py \
  --out reports/baselines.md \
  --json-out reports/baselines.json \
  --title "Rule-based baselines (spot, long only, 1h, BTC/ETH/SOL, OKX data)" \
  --config "$CONFIG" \
  --preamble "$TMP/preamble.md" \
  --epilogue "$TMP/epilogue.md" \
  --lookahead-dir reports/lookahead \
  --strategy "${STRATEGIES[@]}" \
  --results \
    "dev:${OUT_BASE}/dev_fee0.001" \
    "dev:${OUT_BASE}/dev_fee0.002" \
    "eval:${OUT_BASE}/eval_fee0.001" \
    "eval:${OUT_BASE}/eval_fee0.002"

echo "Report written to reports/baselines.md"
