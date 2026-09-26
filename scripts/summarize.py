#!/usr/bin/env python3
"""
Summarise freqtrade backtest results into a Markdown report, with a
buy-and-hold benchmark and a cash benchmark, per period.

Generic: works for any strategy (rule-based baselines, FreqAI, ...).

Examples
--------
  # Baselines (what scripts/run_baselines.sh does):
  .venv/bin/python scripts/summarize.py --out reports/baselines.md \
      --results dev:user_data/backtest_results/baselines/dev_fee0.001 \
                eval:user_data/backtest_results/baselines/eval_fee0.001

  # Any result files / directories, only some strategies, only runs whose
  # --notes contain a tag:
  .venv/bin/python scripts/summarize.py --out reports/x.md \
      --results user_data/backtest_results/backtest-result-2026-09-26_21-36-34.zip \
      --strategy FreqAIFoo --notes-contains "v2"

--results items
  Each item is ``[LABEL:]PATH``. PATH is a freqtrade result file
  (``backtest-result-*.zip`` or legacy ``.json``) or a directory holding them
  (use --recursive to descend). LABEL groups rows into one table (e.g. "dev",
  "eval"); without a label, rows are grouped by the backtest timerange.
  If the same (label, strategy, fee) appears several times, the most recent run
  wins.

Metric definitions (all from freqtrade's own stats)
  Total profit %  profit_total: closed-trade profit / starting balance (open
                  trades are force-closed at the end of a backtest, so this is
                  the whole account return).
  CAGR %          freqtrade's cagr over the actual backtested window.
  Max DD % (MtM)  wallet_stats.max_relative_drawdown: peak-to-trough of the
                  mark-to-market wallet balance (incl. open positions).
  Max DD % (closed) max_relative_drawdown over closed-trade equity.
  Win rate        wins / trades.  PF = gross profit / gross loss.
Buy-and-hold: equal-weight portfolio of the strategy's pairs, bought at the
open of the first backtested candle, sold at the close of the last candle,
paying `fee` on entry and on exit. Its max DD is computed on hourly closes.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# Loading freqtrade results
# --------------------------------------------------------------------------- #
@dataclass
class Row:
    label: str
    strategy: str
    fee: float | None
    stats: dict
    source: Path
    run_time: int = 0
    notes: str = ""
    extra: dict = field(default_factory=dict)


def _result_files(path: Path, recursive: bool) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise SystemExit(f"Result path not found: {path}")
    pattern = "**/backtest-result-*" if recursive else "backtest-result-*"
    files = [
        p
        for p in path.glob(pattern)
        if p.suffix in (".zip", ".json") and not p.name.endswith(".meta.json")
    ]
    return sorted(files)


def _split_label(item: str) -> tuple[str | None, Path]:
    # "dev:some/path" -> ("dev", path). A bare path (even containing ':' on
    # odd filesystems) is kept if it exists as-is.
    if Path(item).exists():
        return None, Path(item)
    m = re.match(r"^([^/\\:]+):(.+)$", item)
    if m:
        return m.group(1), Path(m.group(2))
    return None, Path(item)


def _detect_fee(stats: dict, notes: str) -> float | None:
    for t in stats.get("trades", []) or []:
        if t.get("fee_open") is not None:
            return float(t["fee_open"])
    m = re.search(r"fee=([0-9.]+)", notes or "")
    return float(m.group(1)) if m else None


def load_rows(
    items: list[str], strategies: list[str] | None, notes_contains: str | None, recursive: bool
) -> list[Row]:
    from freqtrade.data.btanalysis import load_backtest_stats

    rows: dict[tuple, Row] = {}
    for item in items:
        label, path = _split_label(item)
        if not path.is_absolute():
            path = (Path.cwd() / path) if (Path.cwd() / path).exists() else ROOT / path
        for f in _result_files(path, recursive):
            try:
                data = load_backtest_stats(f)
            except Exception as e:  # noqa: BLE001
                print(f"WARNING: cannot load {f}: {e}", file=sys.stderr)
                continue
            meta = data.get("metadata", {}) or {}
            for name, st in (data.get("strategy") or {}).items():
                if strategies and name not in strategies:
                    continue
                m = meta.get(name, {}) or {}
                notes = m.get("notes", "") or ""
                if notes_contains and notes_contains not in notes:
                    continue
                fee = _detect_fee(st, notes)
                lab = label or f"{st.get('backtest_start', '?')[:10]} -> {st.get('backtest_end', '?')[:10]}"
                row = Row(lab, name, fee, st, f, int(m.get("backtest_start_time", 0) or 0), notes)
                key = (lab, name, fee)
                if key not in rows or row.run_time >= rows[key].run_time:
                    rows[key] = row
    return list(rows.values())


# --------------------------------------------------------------------------- #
# Benchmarks
# --------------------------------------------------------------------------- #
class PriceStore:
    def __init__(self, datadir: Path, data_format: str):
        self.datadir = datadir
        self.data_format = data_format
        self._cache: dict[tuple, pd.DataFrame] = {}

    def get(self, pair: str, timeframe: str) -> pd.DataFrame:
        key = (pair, timeframe)
        if key not in self._cache:
            from freqtrade.data.history import load_pair_history

            df = load_pair_history(
                pair=pair,
                timeframe=timeframe,
                datadir=self.datadir,
                data_format=self.data_format,
                fill_up_missing=False,
            )
            if df.empty:
                raise SystemExit(f"No data for {pair} {timeframe} in {self.datadir}")
            self._cache[key] = df.set_index("date").sort_index()
        return self._cache[key]


def _ts(s) -> pd.Timestamp:
    t = pd.Timestamp(s)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def buy_and_hold(
    prices: PriceStore, pairs: list[str], timeframe: str, start, end, fee: float
) -> dict:
    """Equal-weight buy-and-hold, no rebalancing, fee paid on entry and exit.

    Buys at the open of the first candle >= start, sells at the close of the
    last candle < end (end is exclusive, like freqtrade's backtest_end).
    """
    start, end = _ts(start), _ts(end)
    w = 1.0 / len(pairs)
    curves, per_asset = [], {}
    for p in pairs:
        df = prices.get(p, timeframe)
        win = df[(df.index >= start) & (df.index < end)]
        if win.empty:
            raise SystemExit(f"No {p} data in {start} -> {end}")
        units = w * (1 - fee) / win["open"].iloc[0]
        curves.append(units * win["close"])
        per_asset[p] = win["close"].iloc[-1] / win["open"].iloc[0] - 1  # gross, no fee
    eq = pd.concat(curves, axis=1).ffill().dropna().sum(axis=1)  # MtM, excl. exit fee
    final = eq.iloc[-1] * (1 - fee)
    days = (eq.index[-1] - eq.index[0]).total_seconds() / 86400 + 1 / 24
    dd = (eq / eq.cummax() - 1).min()
    return {
        "total": final - 1.0,
        "cagr": final ** (365.25 / days) - 1 if days > 0 and final > 0 else float("nan"),
        "max_dd": -dd,
        "per_asset": per_asset,
        "start": eq.index[0],
        "end": eq.index[-1],
    }


def regime_word(ret: float) -> str:
    if ret > 0.20:
        return "bull"
    if ret < -0.20:
        return "bear"
    return "sideways"


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #
def pct(x, digits=1) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "n/a"
    return f"{x * 100:+.{digits}f}%" if x < 0 or x > 0 else f"{0:.{digits}f}%"


def pct_abs(x, digits=1) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return f"{x * 100:.{digits}f}%"


def num(x, digits=2) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "n/a"
    return f"{x:.{digits}f}"


def fee_str(f) -> str:
    return "?" if f is None else f"{f * 100:.2f}%"


def strategy_metrics(st: dict) -> dict:
    wallet = st.get("wallet_stats") or {}
    return {
        "trades": st.get("total_trades", 0),
        "total": st.get("profit_total"),
        "cagr": st.get("cagr"),
        "dd_mtm": wallet.get("max_relative_drawdown"),
        "dd_closed": st.get("max_relative_drawdown"),
        "winrate": st.get("winrate"),
        "pf": st.get("profit_factor"),
        "avg_trade": st.get("profit_mean"),
        "final": st.get("final_balance"),
        "start": st.get("backtest_start"),
        "end": st.get("backtest_end"),
        "days": st.get("backtest_days"),
    }


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def load_lookahead(dirpath: Path, strategies: set[str]) -> list[str]:
    out: list[str] = []
    if not dirpath or not dirpath.is_dir():
        return out
    la_rows = []
    for f in sorted(dirpath.glob("*_lookahead.csv")):
        with f.open() as fh:
            for r in csv.DictReader(fh):
                if strategies and r.get("strategy") not in strategies:
                    continue
                la_rows.append(r)
    if la_rows:
        out += [
            "### Look-ahead analysis (`freqtrade lookahead-analysis`)",
            "",
            "| strategy | has bias | signals checked | biased entries | biased exits | biased indicators |",
            "|---|---|---:|---:|---:|---|",
        ]
        for r in la_rows:
            verdict = "**YES**" if str(r["has_bias"]).lower() == "true" else "no"
            out.append(
                f"| {r['strategy']} | {verdict} | {r['total_signals']} | "
                f"{r['biased_entry_signals']} | {r['biased_exit_signals']} | "
                f"{r.get('biased_indicators') or '-'} |"
            )
        out.append("")
    rec = [
        f
        for f in sorted(dirpath.glob("*_recursive.txt"))
        if not strategies or f.name[: -len("_recursive.txt")] in strategies
    ]
    if rec:
        out += [
            "### Recursive-formula analysis (`freqtrade recursive-analysis`)",
            "",
            "Relative difference of the last indicator values between runs with different "
            "startup-candle counts (`-` = no difference). Values near 0% at the strategy's "
            "own `startup_candle_count` mean indicators have converged (no warm-up bias).",
            "",
        ]
        for f in rec:
            txt = f.read_text().strip()
            name = f.name[: -len("_recursive.txt")]
            out += [f"**{name}**", "", "```", txt or "(no output - see logs)", "```", ""]
    return out


def build_report(args, rows: list[Row]) -> tuple[str, dict]:
    cfg = {}
    if args.config and Path(args.config).exists():
        cfg = json.loads(Path(args.config).read_text())
    exchange = (cfg.get("exchange") or {}).get("name", "okx")
    datadir = Path(args.datadir) if args.datadir else ROOT / "user_data" / "data" / exchange
    prices = PriceStore(datadir, args.data_format or cfg.get("dataformat_ohlcv", "feather"))

    # Preserve label order as given on the command line.
    labels: list[str] = []
    for r in rows:
        if r.label not in labels:
            labels.append(r.label)
    order = {lab: i for i, lab in enumerate(labels)}
    rows.sort(key=lambda r: (order[r.label], r.fee or 0, r.strategy))

    md: list[str] = [f"# {args.title}", ""]
    md.append(
        f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `scripts/summarize.py`. "
        f"Price data: `{datadir.relative_to(ROOT) if datadir.is_relative_to(ROOT) else datadir}`._"
    )
    md.append("")
    if args.preamble:
        md += [Path(args.preamble).read_text().rstrip(), ""]

    machine: dict = {"groups": {}}
    regime_lines: list[str] = []

    for lab in labels:
        grp = [r for r in rows if r.label == lab]
        ms = {id(r): strategy_metrics(r.stats) for r in grp}
        starts = [_ts(ms[id(r)]["start"]) for r in grp]
        ends = [_ts(ms[id(r)]["end"]) for r in grp]
        start, end = min(starts), max(ends)
        pairs = sorted({p for r in grp for p in (r.stats.get("pairlist") or [])})
        timeframe = grp[0].stats.get("timeframe", "1h")
        tr = grp[0].stats.get("timerange", "")
        fees = sorted({r.fee for r in grp if r.fee is not None}) or [args.benchmark_fee]
        bh = {}
        if not args.no_benchmark and pairs:
            for f in fees:
                bh[f] = buy_and_hold(prices, pairs, timeframe, start, end, f)

        md += [
            f"## Period: {lab}",
            "",
            f"Backtested window: **{start:%Y-%m-%d %H:%M} -> {end:%Y-%m-%d %H:%M} UTC** "
            f"(timerange `{tr}`; start may be later than requested because of the "
            f"strategies' indicator warm-up), timeframe {timeframe}, pairs: {', '.join(pairs)}, "
            f"starting balance {grp[0].stats.get('starting_balance')} "
            f"{grp[0].stats.get('stake_currency', '')}, max_open_trades "
            f"{grp[0].stats.get('max_open_trades')}.",
            "",
            "| Strategy | Fee/side | Trades | Total profit % | CAGR % | Max DD % (MtM) "
            "| Max DD % (closed) | Win rate | Profit factor | Avg trade % | vs B&H (pp) |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        machine["groups"][lab] = {"start": str(start), "end": str(end), "rows": [], "buy_and_hold": {}}
        for r in grp:
            m = ms[id(r)]
            b = bh.get(r.fee)
            vs = f"{(m['total'] - b['total']) * 100:+.1f}" if b and m["total"] is not None else "n/a"
            md.append(
                f"| {r.strategy} | {fee_str(r.fee)} | {m['trades']} | {pct(m['total'])} | "
                f"{pct(m['cagr'])} | {pct_abs(m['dd_mtm'])} | {pct_abs(m['dd_closed'])} | "
                f"{pct_abs(m['winrate'])} | {num(m['pf'])} | {pct(m['avg_trade'], 2)} | {vs} |"
            )
            machine["groups"][lab]["rows"].append(
                {"strategy": r.strategy, "fee": r.fee, "source": str(r.source), **{
                    k: (str(v) if k in ("start", "end") else v) for k, v in m.items()}}
            )
        for f, b in bh.items():
            md.append(
                f"| _Buy & hold, equal-weight_ | {fee_str(f)} | {len(pairs)} | {pct(b['total'])} | "
                f"{pct(b['cagr'])} | {pct_abs(b['max_dd'])} | n/a | n/a | n/a | n/a | 0.0 |"
            )
            machine["groups"][lab]["buy_and_hold"][str(f)] = {
                k: v for k, v in b.items() if k not in ("start", "end")
            }
        md.append("| _Cash_ | - | 0 | 0.0% | 0.0% | 0.0% | 0.0% | n/a | n/a | n/a | "
                  + (f"{-next(iter(bh.values()))['total'] * 100:+.1f}" if bh else "n/a") + " |")
        md.append("")
        if bh:
            b0 = next(iter(bh.values()))
            per = ", ".join(f"{p} {pct(v)}" for p, v in b0["per_asset"].items())
            regime_lines.append(
                f"| {lab} | {start:%Y-%m-%d} -> {end:%Y-%m-%d} | {per} | "
                f"{pct(b0['total'])} | {pct_abs(b0['max_dd'])} | {regime_word(b0['total'])} |"
            )
            # Calendar-year breakdown inside the period (fee-free, gross).
            years = range(start.year, end.year + 1)
            yl = []
            for y in years:
                ys = max(start, _ts(f"{y}-01-01"))
                ye = min(end, _ts(f"{y + 1}-01-01"))
                if ye <= ys:
                    continue
                yb = buy_and_hold(prices, pairs, timeframe, ys, ye, 0.0)
                yl.append(f"{y}: {pct(yb['total'], 0)} ({regime_word(yb['total'])})")
            regime_lines.append(f"|  | by calendar year (gross) | {'; '.join(yl)} | | | |")

    if regime_lines:
        md += [
            "## Market regime of each period (buy-and-hold)",
            "",
            "Per-asset returns are gross (open of first candle -> close of last). Portfolio "
            "return is equal-weight and net of the first fee level. Regime label: "
            "> +20% bull, < -20% bear, otherwise sideways.",
            "",
            "| Period | Window | Per-asset return | Portfolio (net) | Portfolio max DD | Regime |",
            "|---|---|---|---:|---:|---|",
            *regime_lines,
            "",
        ]

    la = load_lookahead(Path(args.lookahead_dir) if args.lookahead_dir else None,
                        {r.strategy for r in rows})
    if la:
        md += ["## Bias checks", "", *la]

    if args.epilogue:
        md += [Path(args.epilogue).read_text().rstrip(), ""]

    md += [
        "## Notes on metrics",
        "",
        "- *Total profit %*: whole-account return on the starting balance (open trades are "
        "force-closed at the end of the backtest).",
        "- *Max DD % (MtM)*: largest peak-to-trough fall of the mark-to-market wallet; "
        "*closed*: same on closed-trade equity only. Buy-and-hold DD uses hourly closes.",
        "- *vs B&H (pp)*: strategy total profit minus buy-and-hold total profit at the same fee, "
        "in percentage points.",
        "- Fees are applied on entry and exit. The higher fee level is a crude fee + slippage "
        "stress test; spot trading has no funding costs.",
        "",
        "Sources:",
        "",
        *sorted({f"- `{r.source.relative_to(ROOT) if r.source.is_relative_to(ROOT) else r.source}`"
                 for r in rows}),
        "",
    ]
    return "\n".join(md), machine


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="Markdown file to write")
    ap.add_argument("--results", nargs="+", required=True, help="[LABEL:]PATH items (files or dirs)")
    ap.add_argument("--strategy", nargs="*", help="Only include these strategy names")
    ap.add_argument("--notes-contains", help="Only include runs whose --notes contain this text")
    ap.add_argument("--recursive", action="store_true", help="Search result dirs recursively")
    ap.add_argument("--title", default="Backtest summary")
    ap.add_argument("--config", default=str(ROOT / "config" / "config.backtest.json"),
                    help="Freqtrade config (used for exchange name / data format)")
    ap.add_argument("--datadir", help="OHLCV data dir (default user_data/data/<exchange>)")
    ap.add_argument("--data-format", help="OHLCV data format (default from config)")
    ap.add_argument("--benchmark-fee", type=float, default=0.001,
                    help="Fee for buy-and-hold when a run's fee cannot be detected")
    ap.add_argument("--no-benchmark", action="store_true")
    ap.add_argument("--lookahead-dir", help="Dir with *_lookahead.csv / *_recursive.txt")
    ap.add_argument("--preamble", help="Markdown file inserted after the title")
    ap.add_argument("--epilogue", help="Markdown file appended before the metric notes")
    ap.add_argument("--json-out", help="Also write machine-readable numbers here")
    args = ap.parse_args()

    rows = load_rows(args.results, args.strategy, args.notes_contains, args.recursive)
    if not rows:
        raise SystemExit("No matching backtest results found.")
    text, machine = build_report(args, rows)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(machine, indent=2, default=str))
    print(f"Wrote {out} ({len(rows)} strategy rows)")


if __name__ == "__main__":
    main()
