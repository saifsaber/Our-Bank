#!/usr/bin/env python3
"""
Download the data used by the funding-rate carry study (round 2).

Everything is public, no API key needed. Output goes to user_data/funding/
(gitignored), one CSV per series:

  funding_binance_<SYM>.csv   Binance USDT-M perpetual funding history, from
                              data.binance.vision monthly files (2022-01 ->
                              last published month). Long-history proxy for
                              Bybit (Bybit is geo-blocked from this machine).
                              columns: time (UTC), rate, interval_h
  funding_okx_<SYM>.csv       OKX <SYM>-USDT-SWAP funding history from the
                              public REST API. OKX only serves ~3 months back,
                              so this is used to (1) fill the current month
                              that Binance has not published yet and (2) check
                              that OKX and Binance funding agree.
                              columns: time (UTC), rate, interval_h
  klines_spot_<SYM>.csv       Binance spot daily candles  (time, open, high, low, close)
  klines_perp_<SYM>.csv       Binance USDT-M perp daily candles (time, open, high, low, close)
                              Used for the basis mark-to-market of the hedge.
  okx_savings_usdt.csv        OKX Simple Earn USDT lending-rate history
                              (hourly, annualised) as the "do nothing clever"
                              benchmark for idle stablecoins.

Usage
-----
  REQUESTS_CA_BUNDLE=/root/.ccr/ca-bundle.crt \
      .venv/bin/python scripts/funding_download.py [--start 2022-01] [--symbols BTC ETH SOL]

Re-running is safe: every file is rebuilt from scratch.
"""

from __future__ import annotations

import argparse
import io
import os
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "user_data" / "funding"
BINANCE = "https://data.binance.vision/data"
OKX = "https://www.okx.com"

SESSION = requests.Session()
# The agent proxy re-signs TLS; honour REQUESTS_CA_BUNDLE if set (requests
# does that by itself), otherwise fall back to the proxy CA when it exists.
if "REQUESTS_CA_BUNDLE" not in os.environ and Path("/root/.ccr/ca-bundle.crt").exists():
    SESSION.verify = "/root/.ccr/ca-bundle.crt"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _get(url: str, params: dict | None = None, retries: int = 4) -> requests.Response | None:
    """GET with a small retry loop. Returns None on 404 (file not published)."""
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, timeout=30)
        except requests.RequestException:
            time.sleep(1 + attempt)
            continue
        if r.status_code == 404:
            return None
        if r.status_code == 429:
            time.sleep(2 + attempt)
            continue
        r.raise_for_status()
        return r
    raise RuntimeError(f"GET failed after {retries} tries: {url} {params}")


def _read_zip_csv(content: bytes, names: list[str]) -> pd.DataFrame:
    """Read the single CSV inside a data.binance.vision zip.

    Some files carry a header row and some do not, so we always read without a
    header and drop the first row if it is not numeric.
    """
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        with z.open(z.namelist()[0]) as f:
            df = pd.read_csv(f, header=None)
    if not str(df.iloc[0, 0]).strip().lstrip("-").isdigit():
        df = df.iloc[1:]
    df = df.iloc[:, : len(names)]
    df.columns = names
    return df


def _ms_to_utc(series: pd.Series) -> pd.Series:
    """Binance switched spot timestamps to microseconds in 2025; normalise."""
    v = pd.to_numeric(series).astype("int64")
    v = v.where(v < 10**14, v // 1000)
    return pd.to_datetime(v, unit="ms", utc=True)


def _months(start: str, end: date) -> list[str]:
    y, m = map(int, start.split("-"))
    out = []
    while (y, m) <= (end.year, end.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


# --------------------------------------------------------------------------- #
# Binance (data.binance.vision)
# --------------------------------------------------------------------------- #
def binance_funding(sym: str, start: str) -> pd.DataFrame:
    frames = []
    for mon in _months(start, datetime.now(timezone.utc).date()):
        url = f"{BINANCE}/futures/um/monthly/fundingRate/{sym}USDT/{sym}USDT-fundingRate-{mon}.zip"
        r = _get(url)
        if r is None:  # current month is only published after it ends
            continue
        df = _read_zip_csv(r.content, ["calc_time", "interval_h", "rate"])
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    out = pd.DataFrame(
        {
            # calc_time is a few ms after the funding stamp; floor to the minute
            "time": _ms_to_utc(df["calc_time"]).dt.floor("min"),
            "rate": pd.to_numeric(df["rate"]),
            "interval_h": pd.to_numeric(df["interval_h"]),
        }
    )
    return out.drop_duplicates("time").sort_values("time").reset_index(drop=True)


def binance_klines(sym: str, market: str, start: str) -> pd.DataFrame:
    """Daily candles. market = 'spot' or 'perp'. Monthly files, then daily
    files for the current (not yet published) month."""
    base = f"{BINANCE}/spot" if market == "spot" else f"{BINANCE}/futures/um"
    names = ["open_time", "open", "high", "low", "close"]
    frames, have_until = [], None
    for mon in _months(start, datetime.now(timezone.utc).date()):
        r = _get(f"{base}/monthly/klines/{sym}USDT/1d/{sym}USDT-1d-{mon}.zip")
        if r is None:
            continue
        frames.append(_read_zip_csv(r.content, names))
        have_until = mon
    # daily files after the last published month
    y, m = map(int, have_until.split("-"))
    d = date(y + (m == 12), 1 if m == 12 else m + 1, 1)
    today = datetime.now(timezone.utc).date()
    while d < today:
        r = _get(f"{base}/daily/klines/{sym}USDT/1d/{sym}USDT-1d-{d.isoformat()}.zip")
        if r is not None:
            frames.append(_read_zip_csv(r.content, names))
        d += timedelta(days=1)
    df = pd.concat(frames, ignore_index=True)
    out = pd.DataFrame(
        {
            "time": _ms_to_utc(df["open_time"]),
            "open": pd.to_numeric(df["open"]),
            "high": pd.to_numeric(df["high"]),
            "low": pd.to_numeric(df["low"]),
            "close": pd.to_numeric(df["close"]),
        }
    )
    return out.drop_duplicates("time").sort_values("time").reset_index(drop=True)


# --------------------------------------------------------------------------- #
# OKX public REST
# --------------------------------------------------------------------------- #
def _okx_paginate(path: str, params: dict, ts_key: str, max_pages: int = 2000) -> list[dict]:
    """OKX history endpoints return newest first; page back with `after`."""
    rows, after = [], None
    for _ in range(max_pages):
        p = dict(params)
        if after:
            p["after"] = after
        data = _get(OKX + path, p).json()
        if data.get("code") != "0":
            raise RuntimeError(f"OKX error {data}")
        page = data["data"]
        if not page:
            break
        rows.extend(page)
        after = page[-1][ts_key]
        time.sleep(0.12)  # stay well under the public rate limit
    return rows


def okx_funding(sym: str) -> pd.DataFrame:
    rows = _okx_paginate(
        "/api/v5/public/funding-rate-history",
        {"instId": f"{sym}-USDT-SWAP", "limit": 400},
        "fundingTime",
    )
    df = pd.DataFrame(rows)
    out = pd.DataFrame(
        {
            "time": pd.to_datetime(pd.to_numeric(df["fundingTime"]), unit="ms", utc=True),
            # realizedRate is what was actually settled
            "rate": pd.to_numeric(df["realizedRate"].replace("", None).fillna(df["fundingRate"])),
        }
    ).drop_duplicates("time").sort_values("time").reset_index(drop=True)
    out["interval_h"] = out["time"].diff().dt.total_seconds().div(3600).bfill().round().astype(int)
    return out


def okx_savings() -> pd.DataFrame:
    rows = _okx_paginate(
        "/api/v5/finance/savings/lending-rate-history",
        {"ccy": "USDT", "limit": 100},
        "ts",
        max_pages=1000,
    )
    df = pd.DataFrame(rows)
    return (
        pd.DataFrame(
            {
                "time": pd.to_datetime(pd.to_numeric(df["ts"]), unit="ms", utc=True),
                # `rate` = market lending rate, `lendingRate` = what lenders actually get
                "rate_apr": pd.to_numeric(df["rate"]),
                "lending_apr": pd.to_numeric(df["lendingRate"]),
            }
        )
        .drop_duplicates("time")
        .sort_values("time")
        .reset_index(drop=True)
    )


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2022-01", help="first month (YYYY-MM) for Binance files")
    ap.add_argument("--symbols", nargs="+", default=["BTC", "ETH", "SOL"])
    ap.add_argument("--no-savings", action="store_true", help="skip OKX savings-rate history")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    def save(df: pd.DataFrame, name: str) -> None:
        df.to_csv(OUT / name, index=False)
        print(f"  {name:28s} {len(df):6d} rows  {df['time'].min()} -> {df['time'].max()}")

    for sym in args.symbols:
        print(f"{sym}:")
        save(binance_funding(sym, args.start), f"funding_binance_{sym}.csv")
        save(okx_funding(sym), f"funding_okx_{sym}.csv")
        save(binance_klines(sym, "spot", args.start), f"klines_spot_{sym}.csv")
        save(binance_klines(sym, "perp", args.start), f"klines_perp_{sym}.csv")
    if not args.no_savings:
        print("OKX USDT savings:")
        save(okx_savings(), "okx_savings_usdt.csv")


if __name__ == "__main__":
    main()
