"""Summarise FreqAI backtest results written by scripts/freqai_run.sh.

Usage: .venv/bin/python scripts/freqai_summarize.py user_data/backtest_results/freqai

Reads the newest result zip in each run sub-directory and prints a Markdown table. Every number
comes from freqtrade's own result JSON.
"""

import json
import sys
import zipfile
from pathlib import Path


def load(run_dir: Path):
    zips = sorted(run_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        return None
    with zipfile.ZipFile(zips[-1]) as zf:
        name = next(
            n for n in zf.namelist() if n.endswith(".json") and "_config" not in n
            and not n.endswith("_market_change.json")
        )
        data = json.loads(zf.read(name))
    strat = next(iter(data["strategy"].values()))
    return strat


def main(root: str) -> None:
    rows = []
    for d in sorted(Path(root).iterdir()):
        if not d.is_dir():
            continue
        s = load(d)
        if s is None:
            continue
        trades = s["total_trades"]
        wins = s.get("wins", 0)
        pf = s.get("profit_factor")
        rows.append(
            (
                d.name,
                f"{s['backtest_start'][:10]} -> {s['backtest_end'][:10]}",
                trades,
                f"{100 * s['profit_total']:.2f}",
                f"{100 * s.get('max_drawdown_account', 0):.2f}",
                f"{100 * wins / trades:.1f}" if trades else "-",
                f"{pf:.2f}" if pf is not None else "-",
                f"{100 * s.get('market_change', 0):.2f}",
            )
        )
    hdr = (
        "run", "period", "trades", "total profit %", "max DD %", "win rate %",
        "profit factor", "market change %",
    )
    print("| " + " | ".join(hdr) + " |")
    print("|" + "---|" * len(hdr))
    for r in rows:
        print("| " + " | ".join(str(x) for x in r) + " |")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "user_data/backtest_results/freqai")
