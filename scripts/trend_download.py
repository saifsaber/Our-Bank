#!/usr/bin/env python3
"""
Download the data for the round-3 study (diversified trend following on daily
bars) and build a survivorship-bias-free monthly universe.

Source: data.binance.vision (Binance public bulk data, no API key). This bucket
keeps the files of *delisted* symbols too (LUNA, FTT, SRM, ...), which is what
lets us avoid survivorship bias.

How the symbol list is obtained
-------------------------------
1. The S3 bucket behind data.binance.vision is listable:
       https://s3-ap-northeast-1.amazonaws.com/data.binance.vision
           ?delimiter=/&prefix=data/spot/monthly/klines/
   The listing is paginated (1000 prefixes per page, follow <NextMarker>).
   Every "directory" is one spot symbol that has ever had monthly klines,
   including delisted ones. We keep the ones quoted in USDT.
2. Exclusions (never tradeable as "crypto risk"):
   - stablecoins / fiat:      USDC BUSD TUSD FDUSD DAI USDP PAX UST USTC ...
   - gold tokens:             PAXG XAUT
   - wrapped / liquid-staked duplicates of BTC/ETH/SOL: WBTC WBETH BETH BNSOL
   - Binance leveraged tokens: <COIN>UP / <COIN>DOWN / <COIN>BULL / <COIN>BEAR
     and BULL / BEAR (the prefix must itself be a listed coin, so JUP stays)
   - tokenised stocks / ETFs (2025+ listings such as AAPLB, NVDAB, SPYB, ...)
   The full decision per symbol is written to user_data/trend/symbols.csv.
3. For every kept symbol we list data/spot/monthly/klines/<SYM>/1d/ and fetch
   every monthly zip, plus the daily zips of the current (unpublished) month.

Universe (built here, used by trend_backtest.py)
------------------------------------------------
At each month-end M we rank all kept symbols that (a) traded on the last day of
M and (b) have at least 30 daily candles up to M, by the sum of their USDT
quote volume over the trailing 30 days ending on M. The top N (default 35) form
the universe for the whole following month. Only data up to and including day
M is used. Output: user_data/trend/universe.csv (month_end, rank, symbol,
qv30).

Price series that have a gap of >= 7 days are split into separate instruments
(SYM, SYM#2, ...). This matters for LUNAUSDT: the old Terra LUNA was delisted
in May 2022 and the *new* LUNA was later listed under the same symbol, which
would otherwise show up as a fake +5,000,000% jump.

Usage
-----
  REQUESTS_CA_BUNDLE=/root/.ccr/ca-bundle.crt \
      .venv/bin/python scripts/trend_download.py [--top 35] [--workers 16]

Re-running reuses the per-symbol files already downloaded (use --refresh to
rebuild them).
"""

from __future__ import annotations

import argparse
import io
import os
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "user_data" / "trend"
KL = OUT / "klines"
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
DATA = "https://data.binance.vision"

SESSION = requests.Session()
if "REQUESTS_CA_BUNDLE" not in os.environ and Path("/root/.ccr/ca-bundle.crt").exists():
    SESSION.verify = "/root/.ccr/ca-bundle.crt"
adapter = requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32)
SESSION.mount("https://", adapter)

STABLE = {
    "USDC", "BUSD", "TUSD", "FDUSD", "DAI", "USDP", "PAX", "UST", "USTC", "USDS", "USDSB",
    "USDSOLD", "SUSD", "USDE", "USD1", "RLUSD", "XUSD", "BFUSD", "AEUR", "EUR", "EURI", "GBP",
    "AUD", "BKRW", "FRAX", "U", "KGST", "PYUSD", "TRY", "BRL",
}
GOLD = {"PAXG", "XAUT"}
WRAPPED = {"WBTC", "WBETH", "BETH", "BNSOL"}
# Tokenised stocks / ETFs listed on Binance spot in 2025-2026 (ticker + "B").
STOCKS = set("""AAOIB AAPLB ALABB AMATB AMDB AMZNB ARMB ASMLB ASTSB AVGOB AXTIB BABAB BMNRB
CBRSB COHRB COINB CRCLB CRDOB CRWVB DELLB DJTB DRAMB EWYB FLNCB GLWB GMEB GOOGLB HOODB IBMB
INTCB INTWB IRENB KORUB LITEB METAB MRVLB MSFTB MSTRB MUB MUUB MVLLB NBISB NFLXB NOKB NVDAB
ORCLB PLTRB PYPLB QCOMB QQQB RKLBB SKHYB SMCIB SMHB SNDKB SNXXB SOXLB SOXSB SPCXB SPYB TQQQB
TSLAB TSMB USARB WDCB""".split())


def get(url: str, params: dict | None = None, retries: int = 6) -> requests.Response | None:
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, timeout=60)
        except requests.RequestException:
            time.sleep(1 + attempt)
            continue
        if r.status_code == 404:
            return None
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 + 2 * attempt)
            continue
        r.raise_for_status()
        return r
    raise RuntimeError(f"GET failed: {url} {params}")


def s3_list(prefix: str, delimiter: str | None = None) -> tuple[list[str], list[str]]:
    """Return (common prefixes, keys) under prefix, following pagination."""
    prefixes, keys, marker = [], [], ""
    while True:
        params = {"prefix": prefix, "marker": marker}
        if delimiter:
            params["delimiter"] = delimiter
        r = get(S3, params)
        txt = r.text
        prefixes += re.findall(r"<Prefix>([^<]+/)</Prefix>", txt)
        page_keys = re.findall(r"<Key>([^<]+)</Key>", txt)
        keys += page_keys
        if "<IsTruncated>true</IsTruncated>" not in txt:
            break
        m = re.search(r"<NextMarker>([^<]+)</NextMarker>", txt)
        marker = m.group(1) if m else page_keys[-1]
    prefixes = [p for p in prefixes if p != prefix]
    return prefixes, keys


def classify(base: str, all_bases: set[str]) -> str:
    if base in STABLE:
        return "stablecoin/fiat"
    if base in GOLD:
        return "gold token"
    if base in WRAPPED:
        return "wrapped/staked duplicate"
    if base in STOCKS:
        return "tokenised stock/ETF"
    if base in ("BULL", "BEAR"):
        return "leveraged token"
    for suf in ("UP", "DOWN", "BULL", "BEAR"):
        if base.endswith(suf) and base[: -len(suf)] in all_bases:
            return "leveraged token"
    return ""


def read_kline_zip(content: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        raw = z.read(z.namelist()[0])
    df = pd.read_csv(io.BytesIO(raw), header=None)
    if not str(df.iloc[0, 0]).lstrip("-").isdigit():  # a header row (some newer files)
        df = df.iloc[1:].reset_index(drop=True)
    df = df.iloc[:, :8].astype(float)
    df.columns = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume"]
    ot = df["open_time"]
    # Binance switched spot files to microseconds from 2025-01-01.
    unit = pd.Series("ms", index=df.index).where(ot < 1e14, "us")
    t = [pd.Timestamp(int(v), unit=u, tz="UTC") for v, u in zip(ot, unit)]
    df["time"] = pd.DatetimeIndex(t).normalize()
    return df[["time", "open", "high", "low", "close", "volume", "quote_volume"]]


def fetch_symbol(sym: str, refresh: bool) -> tuple[str, int]:
    path = KL / f"{sym}.parquet"
    if path.exists() and not refresh:
        return sym, len(pd.read_parquet(path))
    enc = quote(sym)
    _, keys = s3_list(f"data/spot/monthly/klines/{sym}/1d/")
    zips = [k for k in keys if k.endswith(".zip")]
    frames = []
    last_month = None
    for k in zips:
        r = get(f"{DATA}/{quote(k)}")
        if r is None:
            continue
        frames.append(read_kline_zip(r.content))
        last_month = k[-11:-4]
    # current month: daily files (only if the symbol was alive last month)
    if last_month is not None and last_month >= "2026-08":
        _, dkeys = s3_list(f"data/spot/daily/klines/{sym}/1d/{sym}-1d-2026-09")
        for k in dkeys:
            if k.endswith(".zip"):
                r = get(f"{DATA}/{quote(k)}")
                if r is not None:
                    frames.append(read_kline_zip(r.content))
    if not frames:
        return sym, 0
    df = pd.concat(frames).drop_duplicates("time").sort_values("time").reset_index(drop=True)
    df.to_parquet(path, index=False)
    _ = enc
    return sym, len(df)


def split_segments(df: pd.DataFrame, sym: str, gap_days: int = 7) -> dict[str, pd.DataFrame]:
    gaps = df["time"].diff().dt.days.fillna(1)
    seg_id = (gaps >= gap_days).cumsum()
    out = {}
    for i, g in df.groupby(seg_id):
        name = sym if i == 0 else f"{sym}#{i + 1}"
        out[name] = g.reset_index(drop=True)
    return out


def build_panel(syms: list[str]) -> dict[str, pd.DataFrame]:
    """Return wide DataFrames (date x instrument) for open/high/low/close/quote_volume."""
    cols = {c: {} for c in ["open", "high", "low", "close", "quote_volume"]}
    for s in syms:
        p = KL / f"{s}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        if df.empty:
            continue
        df = df[df["close"] > 0]
        for name, g in split_segments(df, s[:-4]).items():
            g = g.set_index("time")
            for c in cols:
                cols[c][name] = g[c]
    return {c: pd.DataFrame(v).sort_index() for c, v in cols.items()}


def build_universe(qv: pd.DataFrame, close: pd.DataFrame, top: int) -> pd.DataFrame:
    idx = pd.date_range(close.index.min(), close.index.max(), freq="D", tz="UTC")
    qv = qv.reindex(idx)
    close = close.reindex(idx)
    qv30 = qv.rolling(30, min_periods=1).sum()
    nobs = close.notna().cumsum()
    month_ends = [d for d in idx if (d + pd.Timedelta(days=1)).month != d.month]
    rows = []
    for m in month_ends:
        alive = close.loc[m].notna() & (nobs.loc[m] >= 30)
        v = qv30.loc[m][alive].dropna().sort_values(ascending=False).head(top)
        for r, (s, val) in enumerate(v.items(), 1):
            rows.append({"month_end": m.date().isoformat(), "rank": r, "symbol": s, "qv30": float(val)})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top", type=int, default=35)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    KL.mkdir(parents=True, exist_ok=True)

    print("Listing spot symbols in the data.binance.vision bucket ...")
    prefixes, _ = s3_list("data/spot/monthly/klines/", delimiter="/")
    all_syms = sorted(p.rstrip("/").split("/")[-1] for p in prefixes)
    usdt = [s for s in all_syms if s.endswith("USDT") and len(s) > 4]
    bases = {s[:-4] for s in usdt}
    rows = [{"symbol": s, "base": s[:-4], "excluded": classify(s[:-4], bases)} for s in usdt]
    sym_df = pd.DataFrame(rows)
    keep = sym_df[sym_df["excluded"] == ""]["symbol"].tolist()
    print(f"{len(all_syms)} spot symbols, {len(usdt)} quoted in USDT, {len(keep)} kept after exclusions")

    n_rows = {}
    t0 = time.time()
    with ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(fetch_symbol, s, args.refresh): s for s in keep}
        for i, f in enumerate(as_completed(futs), 1):
            s, n = f.result()
            n_rows[s] = n
            if i % 50 == 0:
                print(f"  {i}/{len(keep)} symbols ({time.time() - t0:.0f}s)")
    sym_df["n_days"] = sym_df["symbol"].map(n_rows).fillna(0).astype(int)
    sym_df.to_csv(OUT / "symbols.csv", index=False)

    panel = build_panel(keep)
    for c, df in panel.items():
        df.to_parquet(OUT / f"panel_{c}.parquet")
    close = panel["close"]
    print(f"Panel: {close.shape[1]} instruments, {close.index.min().date()} -> {close.index.max().date()}")

    uni = build_universe(panel["quote_volume"], close, args.top)
    uni.to_csv(OUT / "universe.csv", index=False)
    per_m = uni.groupby("month_end").size()
    print(f"Universe: {uni['month_end'].nunique()} month-ends, size min {per_m.min()} max {per_m.max()}, "
          f"{uni['symbol'].nunique()} distinct instruments ever included")
    last = close.index.max()
    dead = [s for s in uni["symbol"].unique() if close[s].last_valid_index() < last - pd.Timedelta(days=3)]
    print(f"  of which later delisted / stopped trading: {len(dead)}")


if __name__ == "__main__":
    main()
