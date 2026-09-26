#!/usr/bin/env bash
# One-time setup: virtualenv, pinned Freqtrade, user_data folders, and 1h/4h history.
# Data comes from OKX by default (Bybit blocks some regions); pass EXCHANGE=bybit to use Bybit.
set -euo pipefail
cd "$(dirname "$0")/.."

EXCHANGE="${EXCHANGE:-okx}"

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/freqtrade create-userdir --userdir user_data
.venv/bin/freqtrade download-data --exchange "$EXCHANGE" \
  --pairs BTC/USDT ETH/USDT SOL/USDT --timeframes 1h 4h \
  --timerange 20220101- --userdir user_data
