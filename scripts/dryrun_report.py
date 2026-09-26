#!/usr/bin/env python3
"""Weekly comparison report for the live dry-run bots.

Reads the Freqtrade sqlite databases written by the dry-run bots (default:
user_data/dryrun-*.sqlite) and prints a markdown report, also written to
user_data/dryrun_report.md. For every bot:

  * closed trades, win rate, fees paid
  * net realised profit after fees (USDT and % of the starting wallet)
  * open positions and their unrealised result at the current price (if a price is available)
  * max drawdown of the closed-trade equity curve

and, over the same window (the earliest bot start -> now), the benchmarks:

  * BTC buy-and-hold, and an equal-weight BTC/ETH/SOL buy-and-hold (0.1% fee in and out)
  * USDT in a savings product (--savings-apy, default 3.2%/year)
  * holding cash (0%)

Usage (from the repo root):
  python3 scripts/dryrun_report.py
  python3 scripts/dryrun_report.py --db rsi=user_data/dryrun-rsi.sqlite --no-fetch
  docker compose run --rm report          # same thing inside the Freqtrade image

Prices for the benchmarks and open positions come from the exchange's public API through
ccxt (no API key). If that fails (no internet, blocked region) the script falls back to
candles saved under user_data/data/<exchange>/, and otherwise prints "n/a".
Only the Python standard library is required; ccxt and pandas are used when installed.
"""

from __future__ import annotations

import argparse
import glob
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


FEE = 0.001  # Bybit spot taker fee, used for the buy-and-hold benchmarks
BENCH_PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
MIN_TRADES_FOR_CONFIDENCE = 30


# --------------------------------------------------------------------------- helpers
def parse_dt(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).replace("T", " ")
        dt = None
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(s[:26], fmt)
                break
            except ValueError:
                continue
        if dt is None:
            try:
                dt = datetime.fromisoformat(str(value))
            except ValueError:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)  # Freqtrade stores naive UTC
    return dt.astimezone(UTC)


def pct(x: float | None, digits: int = 2) -> str:
    return "n/a" if x is None else f"{x * 100:+.{digits}f}%"


def usdt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:+.2f}"


# --------------------------------------------------------------------------- prices
class Prices:
    """Current price and price-at-time lookups, via ccxt (public API) or local candles."""

    def __init__(self, exchange: str, fetch: bool, datadir: str):
        self.exchange_name = exchange
        self.datadir = datadir
        self.ex = None
        self.source = "none"
        self.errors: list[str] = []
        if fetch:
            try:
                import ccxt  # type: ignore

                self.ex = getattr(ccxt, exchange)({"enableRateLimit": True, "timeout": 20000})
            except Exception as e:  # noqa: BLE001
                self.errors.append(f"ccxt unavailable: {e}")
        self._cache: dict[str, list] = {}

    def _local_candles(self, pair: str) -> list:
        path = os.path.join(self.datadir, self.exchange_name, pair.replace("/", "_") + "-1h.feather")
        if not os.path.exists(path):
            return []
        try:
            import pandas as pd  # type: ignore

            df = pd.read_feather(path)
            return [
                [int(d.timestamp() * 1000), o, h, lo, c, v]
                for d, o, h, lo, c, v in df[["date", "open", "high", "low", "close", "volume"]]
                .itertuples(index=False, name=None)
            ]
        except Exception as e:  # noqa: BLE001
            self.errors.append(f"reading {path}: {e}")
            return []

    def candles(self, pair: str, since: datetime) -> list:
        """1h candles [ms, o, h, l, c, v] from `since` to now."""
        key = f"{pair}|{since.isoformat()}"
        if key in self._cache:
            return self._cache[key]
        rows: list = []
        if self.ex is not None:
            try:
                start = int((since - timedelta(hours=1)).timestamp() * 1000)
                while True:
                    batch = self.ex.fetch_ohlcv(pair, "1h", since=start, limit=1000)
                    if not batch:
                        break
                    rows.extend(b for b in batch if not rows or b[0] > rows[-1][0])
                    if len(batch) < 2 or batch[-1][0] <= start:
                        break
                    start = batch[-1][0] + 1
                    if batch[-1][0] >= int(datetime.now(UTC).timestamp() * 1000) - 3_600_000:
                        break
                if rows:
                    self.source = f"{self.exchange_name} public API"
            except Exception as e:  # noqa: BLE001
                msg = " ".join(str(e).split())
                self.errors.append(f"fetch {pair} from {self.exchange_name}: {type(e).__name__}: {msg}"[:160])
                rows = []
        if not rows:
            local = self._local_candles(pair)
            cut = int((since - timedelta(hours=1)).timestamp() * 1000)
            rows = [r for r in local if r[0] >= cut]
            if rows:
                self.source = f"local candles user_data/data/{self.exchange_name}"
        self._cache[key] = rows
        return rows

    def window_prices(self, pair: str, start: datetime) -> tuple[float, float, datetime] | None:
        """(price at start, latest price, time of latest price)."""
        rows = self.candles(pair, start)
        if not rows:
            return None
        start_ms = start.timestamp() * 1000
        # candle that contains `start`: last one whose open time <= start
        first = rows[0]
        for r in rows:
            if r[0] <= start_ms:
                first = r
            else:
                break
        # use the open of the containing candle if start is at its open, otherwise its close
        p0 = first[1] if first[0] >= start_ms else first[4]
        last = rows[-1]
        return p0, last[4], datetime.fromtimestamp(last[0] / 1000 + 3600, UTC)

    def last_price(self, pair: str, since: datetime) -> float | None:
        if self.ex is not None:
            try:
                t = self.ex.fetch_ticker(pair)
                if t.get("last"):
                    return float(t["last"])
            except Exception as e:  # noqa: BLE001
                self.errors.append(f"ticker {pair}: {type(e).__name__}"[:200])
        rows = self.candles(pair, since)
        return float(rows[-1][4]) if rows else None


# --------------------------------------------------------------------------- bot stats
@dataclass
class BotStats:
    name: str
    path: str
    ok: bool = True
    error: str = ""
    strategy: str = ""
    exchange: str = ""
    start: datetime | None = None
    closed: int = 0
    wins: int = 0
    realised: float = 0.0
    fees: float = 0.0
    max_dd: float = 0.0
    open_trades: list = field(default_factory=list)
    unrealised: float | None = 0.0
    exit_reasons: dict = field(default_factory=dict)
    last_close: datetime | None = None


def read_bot(name: str, path: str, wallet: float) -> BotStats:
    st = BotStats(name=name, path=path)
    if not os.path.exists(path):
        st.ok, st.error = False, "database file not found (bot not started yet?)"
        return st
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        if "trades" not in tables:
            st.ok, st.error = False, "no trades table (bot never initialised this DB)"
            return st
        if "KeyValueStore" in tables:
            row = con.execute(
                "select datetime_value from KeyValueStore where key='bot_start_time'"
            ).fetchone()
            if row:
                st.start = parse_dt(row[0])
        trades = [dict(r) for r in con.execute("select * from trades order by id")]
        con.close()
    except sqlite3.Error as e:
        st.ok, st.error = False, f"sqlite error: {e}"
        return st

    if trades:
        st.strategy = trades[0].get("strategy") or ""
        st.exchange = trades[0].get("exchange") or ""
        first_open = min(parse_dt(t["open_date"]) for t in trades)
        st.start = min(st.start, first_open) if st.start else first_open

    closed = [t for t in trades if not t["is_open"]]
    closed.sort(key=lambda t: parse_dt(t["close_date"]) or datetime.min.replace(tzinfo=UTC))
    equity = peak = wallet
    for t in closed:
        p = float(t.get("close_profit_abs") or 0.0)
        st.realised += p
        st.wins += p > 0
        equity += p
        peak = max(peak, equity)
        st.max_dd = max(st.max_dd, (peak - equity) / peak if peak > 0 else 0.0)
        reason = t.get("exit_reason") or "?"
        st.exit_reasons[reason] = st.exit_reasons.get(reason, 0) + 1
        st.last_close = parse_dt(t["close_date"])
    st.closed = len(closed)
    for t in trades:
        fo = t.get("fee_open_cost")
        if fo is None:
            fo = float(t.get("fee_open") or 0) * float(t.get("amount") or 0) * float(t.get("open_rate") or 0)
        st.fees += float(fo or 0)
        if not t["is_open"]:
            fc = t.get("fee_close_cost")
            if fc is None:
                fc = float(t.get("fee_close") or 0) * float(t.get("amount") or 0) * float(t.get("close_rate") or 0)
            st.fees += float(fc or 0)
    st.open_trades = [t for t in trades if t["is_open"]]
    return st


def mark_open(st: BotStats, prices: Prices | None) -> None:
    if not st.open_trades:
        st.unrealised = 0.0
        return
    total = 0.0
    for t in st.open_trades:
        price = prices.last_price(t["pair"], st.start or datetime.now(UTC)) if prices else None
        if price is None:
            st.unrealised = None
            return
        amount = float(t["amount"] or 0)
        cost = amount * float(t["open_rate"]) * (1 + float(t.get("fee_open") or 0))
        value = amount * price * (1 - float(t.get("fee_close") or FEE))
        t["_price"] = price
        t["_pnl"] = value - cost
        total += value - cost
    st.unrealised = total


# --------------------------------------------------------------------------- report
def build_report(bots: list[BotStats], args, prices: Prices | None) -> str:
    now = datetime.now(UTC)
    starts = [b.start for b in bots if b.start]
    start = min(starts) if starts else None
    days = (now - start).total_seconds() / 86400 if start else 0.0

    out: list[str] = []
    out.append("# Dry-run report")
    out.append("")
    out.append(f"Generated {now:%Y-%m-%d %H:%M} UTC.")
    if start:
        out.append(f"Window: {start:%Y-%m-%d %H:%M} UTC -> now ({days:.1f} days). "
                   f"Starting wallet per bot: {args.wallet:g} USDT (paper money).")
    else:
        out.append("No bot has started yet (no start time in any database).")
    out.append("")

    # ---- per bot table
    out.append("## Bots")
    out.append("")
    out.append("| Bot | Strategy | Closed trades | Win rate | Fees paid (USDT) | Realised net (USDT) | Realised net % | Open positions | Unrealised (USDT) | Total incl. open % | Max DD (closed) |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for b in bots:
        if not b.ok:
            out.append(f"| {b.name} | – | – | – | – | – | – | – | – | – | {b.error} |")
            continue
        wr = f"{b.wins / b.closed * 100:.0f}%" if b.closed else "n/a"
        tot = None if b.unrealised is None else (b.realised + b.unrealised) / args.wallet
        out.append(
            f"| {b.name} | {b.strategy or '–'} | {b.closed} | {wr} | {b.fees:.2f} | {usdt(b.realised)} | "
            f"{pct(b.realised / args.wallet)} | {len(b.open_trades)} | {usdt(b.unrealised)} | {pct(tot)} | "
            f"{b.max_dd * 100:.1f}% |"
        )
    out.append("")
    out.append("Realised net = sum of closed trades after entry and exit fees. "
               "Unrealised = open positions valued at the latest price minus the exit fee.")
    out.append("")

    # ---- open positions detail
    opens = [(b, t) for b in bots if b.ok for t in b.open_trades]
    if opens:
        out.append("### Open positions")
        out.append("")
        out.append("| Bot | Pair | Opened (UTC) | Entry | Now | Stake (USDT) | Unrealised (USDT) |")
        out.append("|---|---|---|---|---|---|---|")
        for b, t in opens:
            od = parse_dt(t["open_date"])
            now_p = t.get("_price")
            out.append(
                f"| {b.name} | {t['pair']} | {od:%Y-%m-%d %H:%M} | {float(t['open_rate']):.6g} | "
                f"{'n/a' if now_p is None else f'{now_p:.6g}'} | {float(t['stake_amount']):.2f} | "
                f"{usdt(t.get('_pnl'))} |"
            )
        out.append("")

    # ---- benchmarks
    out.append("## Benchmarks over the same window")
    out.append("")
    bench: dict[str, float | None] = {}
    if start and prices is not None:
        rets = {}
        for pair in BENCH_PAIRS:
            wp = prices.window_prices(pair, start)
            if wp:
                p0, p1, _ = wp
                rets[pair] = (p1 / p0) * (1 - FEE) ** 2 - 1
        bench["BTC buy-and-hold"] = rets.get("BTC/USDT")
        bench["Equal-weight BTC/ETH/SOL buy-and-hold"] = (
            sum(rets.values()) / len(rets) if len(rets) == len(BENCH_PAIRS) else None
        )
    else:
        bench["BTC buy-and-hold"] = None
        bench["Equal-weight BTC/ETH/SOL buy-and-hold"] = None
    savings = (1 + args.savings_apy / 100) ** (days / 365) - 1 if start else None
    bench[f"USDT savings ({args.savings_apy:g}%/year)"] = savings
    bench["Cash (do nothing)"] = 0.0

    out.append("| Benchmark | Return |")
    out.append("|---|---|")
    for k, v in bench.items():
        out.append(f"| {k} | {pct(v)} |")
    out.append("")
    if prices is not None:
        out.append(f"Price source: {prices.source}. Buy-and-hold includes a {FEE * 100:.1f}% fee on entry and on exit.")
        if prices.errors and prices.source == "none":
            out.append("")
            out.append("Price lookup problems (is the exchange reachable from this machine?):")
            out.extend(f"- {e}" for e in sorted(set(prices.errors))[:3])
    else:
        out.append("Price lookups disabled (--no-fetch and no local candles).")
    out.append("")

    # ---- verdict
    out.append("## Verdict per bot (total incl. open positions)")
    out.append("")
    out.append("| Bot | Beats cash | Beats USDT savings | Beats BTC buy-and-hold | Beats equal-weight buy-and-hold | Sample |")
    out.append("|---|---|---|---|---|---|")
    bh_btc = bench["BTC buy-and-hold"]
    bh_eq = bench["Equal-weight BTC/ETH/SOL buy-and-hold"]

    def beats(x, y):
        return "n/a" if x is None or y is None else ("yes" if x > y else "no")

    for b in bots:
        if not b.ok:
            continue
        tot = None if b.unrealised is None else (b.realised + b.unrealised) / args.wallet
        sample = ("too small to judge" if b.closed < MIN_TRADES_FOR_CONFIDENCE
                  else "ok-ish")
        out.append(f"| {b.name} | {beats(tot, 0.0)} | {beats(tot, savings)} | {beats(tot, bh_btc)} | "
                   f"{beats(tot, bh_eq)} | {b.closed} closed trades, {sample} |")
    out.append("")
    out.append(f"A bot only counts as a success if it beats USDT savings AND buy-and-hold after fees, "
               f"over several weeks, with a reasonable number of trades (fewer than "
               f"{MIN_TRADES_FOR_CONFIDENCE} closed trades is mostly luck). Dry-run fills are "
               f"optimistic: real orders can fill worse (slippage) or not at all.")
    out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", action="append", default=[],
                    help="NAME=PATH of a dry-run sqlite DB (repeatable). Default: user_data/dryrun-*.sqlite")
    ap.add_argument("--wallet", type=float, default=100.0, help="starting dry_run_wallet per bot (default 100)")
    ap.add_argument("--savings-apy", type=float, default=3.2, help="USDT savings APY in %% (default 3.2)")
    ap.add_argument("--exchange", default=None, help="exchange for prices (default: from the DBs, else bybit)")
    ap.add_argument("--no-fetch", action="store_true", help="do not call the exchange API; local candles only")
    ap.add_argument("--datadir", default="user_data/data", help="local candle folder (default user_data/data)")
    ap.add_argument("--out", default="user_data/dryrun_report.md", help="markdown output file ('' to skip)")
    args = ap.parse_args(argv)

    dbs: list[tuple[str, str]] = []
    for item in args.db:
        name, _, path = item.partition("=")
        if not path:
            path, name = name, os.path.splitext(os.path.basename(name))[0]
        dbs.append((name, path))
    if not dbs:
        for path in sorted(glob.glob("user_data/dryrun-*.sqlite")):
            dbs.append((os.path.splitext(os.path.basename(path))[0].removeprefix("dryrun-"), path))
    if not dbs:
        print("No dry-run databases found (user_data/dryrun-*.sqlite). Start the bots first, "
              "or pass --db NAME=PATH.", file=sys.stderr)
        return 1

    bots = [read_bot(n, p, args.wallet) for n, p in dbs]
    exchange = args.exchange or next((b.exchange for b in bots if b.ok and b.exchange), None) or "bybit"
    prices = Prices(exchange, fetch=not args.no_fetch, datadir=args.datadir)
    for b in bots:
        if b.ok:
            mark_open(b, prices)

    report = build_report(bots, args, prices)
    print(report)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report + "\n")
        print(f"(written to {args.out})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
