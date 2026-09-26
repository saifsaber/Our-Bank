#!/usr/bin/env python3
"""
Backtest of the funding-rate "cash-and-carry" trade: long spot + short USDT
perpetual of the same quantity (delta neutral), collecting funding.

Inputs come from scripts/funding_download.py (user_data/funding/). Funding is
Binance USDT-M history (long-history proxy for Bybit), with the last partial
month (not yet published by Binance) filled from OKX. Prices are Binance spot
and USDT-M perp daily candles, so the basis mark-to-market is included.

Model (daily steps, all decisions on information known at that time)
--------------------------------------------------------------------
* Capital C per coin is split into a spot side (fraction s) and a perp margin
  side (1 - s). The spot side buys q coins; the perp side shorts the same q.
  s = 0.5 -> perp leverage 1x;  s = L/(L+1) -> perp leverage L (L = 2, 3).
* Funding: every settlement event pays the short  q * price * rate  (negative
  rate -> the short pays). Price = mid of the day's perp open/close. Events are
  attributed to the day that *ends* at them (the 00:00 UTC event belongs to the
  previous day), so a position opened at a day's open earns that day's 08:00
  and 16:00 events and the next 00:00 one.
* Basis mark-to-market: spot leg valued at spot close, perp leg settled daily
  at perp close. Net P&L of the hedge = -q * change of (perp - spot).
* Liquidation of the short leg: checked with the day's perp HIGH. If the perp
  account equity at the high falls below maintenance margin (--mmr, 1% of
  notional, conservative vs Bybit's 0.5% tier 1 for BTC/ETH), the short is
  liquidated: its margin is lost, the now-unhedged spot is sold at the close
  and (if the rule still says "in") the trade is re-opened at the close.
* Rebalance: at each close, if perp leverage q*F/M left the band
  [L/2, L+1] the position is resized to the target split of current equity,
  paying fees on the quantity traded on both legs.
* Fees (Bybit base tier, taker everywhere): spot 0.10%, perp 0.055%, per leg
  per side; optional extra --slippage per leg per side.
* Trades execute at the daily close (== next day's open on Binance 1d bars).
* Optional lot rounding (--lots bybit) to test small accounts: quantities are
  floored to Bybit's min order qty (BTC 0.001, ETH 0.01, SOL 0.1); if that is
  0 the coin stays in cash.

Variants
--------
  always   : in the trade the whole period.
  filtered : enter when the trailing 7-day mean funding, annualised, exceeds
             the entry threshold; exit when it drops below 0. The threshold is
             fixed a priori as the 4-leg round-trip cost amortised over an
             expected 30-day hold: 2*(0.10%+0.055%) / 30 days * 365 = 3.77%/yr.
             (A 10%/yr entry threshold is also reported as a sensitivity.)

Periods (same as round 1): dev 2022-01-01 -> 2024-12-31,
holdout 2025-01-01 -> 2026-09-25 (inclusive).

Usage
-----
  .venv/bin/python scripts/funding_backtest.py            # prints tables, writes reports/funding_carry.json
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "user_data" / "funding"
COINS = ["BTC", "ETH", "SOL"]
PERIODS = {"dev": ("2022-01-01", "2024-12-31"), "holdout": ("2025-01-01", "2026-09-25")}
SPOT_FEE, PERP_FEE = 0.0010, 0.00055
# Bybit linear perp minOrderQty / qtyStep (spot min is 5 USDT, never binding here)
BYBIT_LOT = {"BTC": 0.001, "ETH": 0.01, "SOL": 0.1}
ROUND_TRIP = 2 * (SPOT_FEE + PERP_FEE)
THRESH_A_PRIORI = ROUND_TRIP / 30 * 365  # 3.77 %/yr


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
def load_coin(coin: str) -> pd.DataFrame:
    """One row per UTC day: spot/perp OHLC, daily funding sum, event counts."""
    b = pd.read_csv(DATA / f"funding_binance_{coin}.csv", parse_dates=["time"])
    o = pd.read_csv(DATA / f"funding_okx_{coin}.csv", parse_dates=["time"])
    o = o[o["time"] > b["time"].max()].assign(src="okx")
    f = pd.concat([b.assign(src="binance"), o], ignore_index=True)
    # attribute each event to the day it closes (00:00 event -> previous day)
    f["day"] = (f["time"] - pd.Timedelta(minutes=1)).dt.floor("D")
    fd = f.groupby("day").agg(
        funding=("rate", "sum"), n_events=("rate", "size"), n_neg=("rate", lambda r: (r < 0).sum())
    )

    def kl(kind: str) -> pd.DataFrame:
        k = pd.read_csv(DATA / f"klines_{kind}_{coin}.csv", parse_dates=["time"]).set_index("time")
        return k.add_prefix(f"{kind}_")

    d = kl("spot").join(kl("perp"), how="left").join(fd, how="left")
    # 5 perp days missing for SOL in 2022 on data.binance.vision: carry prices forward
    d[[c for c in d.columns if c.startswith("perp_")]] = d.filter(like="perp_").ffill()
    d[["funding", "n_events", "n_neg"]] = d[["funding", "n_events", "n_neg"]].fillna(0)
    # trailing 7-day mean daily funding, annualised; known at that day's close
    d["sig_ann"] = d["funding"].rolling(7).sum() / 7 * 365
    return d


# --------------------------------------------------------------------------- #
# Simulation of one coin
# --------------------------------------------------------------------------- #
@dataclass
class Params:
    split: float = 0.5  # fraction of capital on the spot side
    variant: str = "always"  # "always" | "filtered"
    enter_ann: float = THRESH_A_PRIORI
    exit_ann: float = 0.0
    mmr: float = 0.01
    slippage: float = 0.0
    lot: float = 0.0  # 0 = fractional quantities allowed

    @property
    def lev(self) -> float:
        return self.split / (1 - self.split)


def simulate(full: pd.DataFrame, start: str, end: str, capital: float, p: Params) -> pd.DataFrame:
    """Return a daily frame with equity and bookkeeping for one coin.

    `full` is the whole history (so the entry signal on the first day can use
    funding from before `start`); trading happens only in [start, end]."""
    d = full.loc[start:end]
    before = full.loc[: pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=1), "sig_ann"]
    sig_before = before.iloc[-1] if len(before) else np.nan
    sfee, pfee = SPOT_FEE + p.slippage, PERP_FEE + p.slippage

    cash = capital  # USDT on the spot side not in coins (+ everything when flat)
    q = 0.0  # coins long spot == coins short perp
    M = 0.0  # perp account equity (margin + realised perp P&L + funding)
    cum_funding = cum_fees = 0.0
    rows = []

    def target_qty(equity: float, price: float) -> float:
        qt = p.split * equity / price
        if p.lot:
            qt = math.floor(qt / p.lot + 1e-9) * p.lot
        return qt

    def resize(new_q: float, S: float, F: float) -> float:
        """Trade both legs to new_q at prices S/F, re-split capital. Returns fee."""
        nonlocal cash, q, M
        dq = abs(new_q - q)
        fee = dq * S * sfee + dq * F * pfee
        equity = cash + q * S + M - fee
        q = new_q
        if q == 0:
            cash, M = equity, 0.0
        else:
            M = (1 - p.split) * equity
            cash = equity - M - q * S  # leftover from lot rounding stays in cash
        return fee

    def want_in(sig: float, currently_in: bool) -> bool:
        if p.variant == "always":
            return True
        if np.isnan(sig):
            return False
        return sig > p.exit_ann if currently_in else sig > p.enter_ann

    first = d.iloc[0]
    prev_F = first["perp_open"]
    # entry on day 1 at its open, using the signal known at the previous close
    if want_in(sig_before, False):
        qt = target_qty(capital, first["spot_open"])
        if qt > 0:
            fee = resize(qt, first["spot_open"], first["perp_open"])
            cum_fees += fee

    for day, r in d.iterrows():
        S, F = r["spot_close"], r["perp_close"]
        fund = liq = rebal = 0
        if q > 0:
            # 1) funding events of this day, paid to the short
            fund = q * (r["perp_open"] + F) / 2 * r["funding"]
            # 2) liquidation check at the day's perp high
            eq_high = M - q * (r["perp_high"] - prev_F)
            if eq_high < p.mmr * q * r["perp_high"]:
                liq = 1
                # short gone, margin lost; sell the naked spot at the close
                M = 0.0
                fee = q * S * sfee
                cash += q * S - fee
                cum_fees += fee
                q = 0.0
                fund = 0.0  # conservative: assume it happened before settlement
            else:
                M += fund - q * (F - prev_F)  # daily settlement of the short
                cum_funding += fund
        in_now = q > 0
        # 3) decision at the close for the next day
        # after a liquidation the rule still counts as "in" (exit threshold applies)
        if want_in(r["sig_ann"], in_now or bool(liq)):
            equity = cash + q * S + M
            if not in_now:
                qt = target_qty(equity, S)
                if qt > 0:
                    cum_fees += resize(qt, S, F)
            else:
                lev = q * F / M if M > 0 else np.inf
                if lev > p.lev + 1 or lev < p.lev / 2:
                    qt = target_qty(equity, S)
                    if p.lot == 0 or abs(qt - q) >= p.lot - 1e-12:
                        cum_fees += resize(qt, S, F)
                        rebal = 1
        elif in_now:
            cum_fees += resize(0.0, S, F)
        prev_F = F
        rows.append(
            dict(
                day=day,
                equity=cash + q * S + M,
                in_pos=int(q > 0),
                funding_pnl=cum_funding,
                fees=cum_fees,
                liq=liq,
                rebal=rebal,
                fund_rate=r["funding"],
                n_events=r["n_events"],
                n_neg=r["n_neg"],
                notional=q * S,
            )
        )
    return pd.DataFrame(rows).set_index("day")




# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def max_dd(series: pd.Series) -> float:
    peak = series.cummax()
    return float(((series - peak) / peak).min())


def metrics(res: pd.DataFrame, capital: float) -> dict:
    eq = res["equity"]
    days = (res.index[-1] - res.index[0]).days + 1
    total = eq.iloc[-1] / capital - 1
    ann = (1 + total) ** (365 / days) - 1 if total > -1 else -1.0
    monthly = pd.concat([pd.Series([capital], index=[res.index[0] - pd.Timedelta(days=1)]), eq]).resample("ME").last()
    mret = monthly.pct_change().dropna()
    carry_curve = capital + res["funding_pnl"] - res["fees"]  # funding minus fees, no basis MTM
    held = res["in_pos"] == 1
    ev = res.loc[held, "n_events"].sum()
    return dict(
        total=total,
        ann=ann,
        worst_month=float(mret.min()),
        best_month=float(mret.max()),
        pct_months_neg=float((mret < 0).mean()),
        max_dd=max_dd(eq),
        max_dd_carry_only=max_dd(carry_curve),
        funding_pnl=float(res["funding_pnl"].iloc[-1] / capital),
        fees=float(res["fees"].iloc[-1] / capital),
        basis_pnl=float(total - (res["funding_pnl"].iloc[-1] - res["fees"].iloc[-1]) / capital),
        pct_events_neg=float(res["n_neg"].sum() / res["n_events"].sum()),
        pct_days_neg=float((res["fund_rate"] < 0).mean()),
        pct_time_in=float(held.mean()),
        pct_events_neg_held=float(res.loc[held, "n_neg"].sum() / ev) if ev else float("nan"),
        rebalances=int(res["rebal"].sum()),
        liquidations=int(res["liq"].sum()),
        avg_month_usdt=float((eq.iloc[-1] - capital) / (days / 30.4375)),
        days=days,
    )


def run_portfolio(data: dict, start: str, end: str, capital: float, p: Params) -> tuple[dict, pd.DataFrame]:
    """Each coin simulated separately on capital/len(coins); equity summed."""
    per = {}
    for c, d in data.items():
        per[c] = simulate(d, start, end, capital / len(data), p)
    idx = per[COINS[0]].index
    tot = pd.DataFrame(index=idx)
    for col in ["equity", "funding_pnl", "fees", "liq", "rebal", "n_events", "n_neg", "notional"]:
        tot[col] = sum(per[c][col] for c in per)
    tot["in_pos"] = (sum(per[c]["in_pos"] for c in per) > 0).astype(int)
    tot["fund_rate"] = sum(per[c]["fund_rate"] for c in per) / len(per)
    return per, tot


def savings_benchmark(start: str, end: str) -> dict:
    """OKX Simple Earn USDT: compounding the hourly lender APR over the period."""
    s = pd.read_csv(DATA / "okx_savings_usdt.csv", parse_dates=["time"]).set_index("time")["lending_apr"]
    t0, t1 = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    s = s[(s.index >= t0) & (s.index < t1)]
    growth = float(np.prod(1 + s / (365 * 24)))
    days = (pd.Timestamp(end) - pd.Timestamp(start)).days + 1
    return dict(total=growth - 1, ann=growth ** (365 / days) - 1, mean_apr=float(s.mean()))


# --------------------------------------------------------------------------- #
def pct(x: float, nd: int = 1) -> str:
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x * 100:+.{nd}f}%"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "reports" / "funding_carry.json"))
    args = ap.parse_args()

    data = {}
    for c in COINS:
        data[c] = load_coin(c)

    results: dict = {"params": dict(spot_fee=SPOT_FEE, perp_fee=PERP_FEE, threshold_a_priori=THRESH_A_PRIORI)}
    splits = {"50/50 (1x)": 0.5, "2x (67/33)": 2 / 3, "3x (75/25)": 0.75}
    variants = {
        "always": dict(variant="always"),
        f"filtered>{THRESH_A_PRIORI*100:.2f}%": dict(variant="filtered"),
        "filtered>10%": dict(variant="filtered", enter_ann=0.10),
    }

    for per_name, (start, end) in PERIODS.items():
        print(f"\n## {per_name}: {start} -> {end}")
        sb = savings_benchmark(start, end)
        results.setdefault(per_name, {})["okx_usdt_savings"] = sb
        print(f"OKX USDT Simple Earn benchmark: total {pct(sb['total'])}, ann {pct(sb['ann'])}")
        print("| variant | split | coin | ann | total | funding | fees | basis | worst mo | maxDD | maxDD carry | %ev neg | %time in | rebal | liq |")
        print("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for vn, vkw in variants.items():
            for sn, s in splits.items():
                p = Params(split=s, **vkw)
                per, tot = run_portfolio(data, start, end, 1000.0, p)
                for coin, res in list(per.items()) + [("EW", tot)]:
                    cap = 1000.0 / 3 if coin != "EW" else 1000.0
                    m = metrics(res, cap)
                    results[per_name].setdefault(vn, {}).setdefault(sn, {})[coin] = m
                    print(
                        f"| {vn} | {sn} | {coin} | {pct(m['ann'])} | {pct(m['total'])} | {pct(m['funding_pnl'])} | "
                        f"{pct(-m['fees'],2)} | {pct(m['basis_pnl'],2)} | {pct(m['worst_month'],2)} | {pct(m['max_dd'],2)} | "
                        f"{pct(m['max_dd_carry_only'],2)} | {m['pct_events_neg']*100:.0f}% | {m['pct_time_in']*100:.0f}% | "
                        f"{m['rebalances']} | {m['liquidations']} |"
                    )
        # stress: extra 0.05% slippage per leg per side
        for vn, vkw in list(variants.items())[:2]:
            per, tot = run_portfolio(data, start, end, 1000.0, Params(split=0.5, slippage=0.0005, **vkw))
            m = metrics(tot, 1000.0)
            results[per_name].setdefault("stress_slip0.05", {})[vn] = m
            print(f"stress slippage 0.05%/leg, {vn}, 50/50 EW: ann {pct(m['ann'])}, total {pct(m['total'])}, maxDD {pct(m['max_dd'],2)}")

        # small accounts with Bybit lot sizes
        for cap in (100.0, 1000.0):
            for vn, vkw in list(variants.items())[:2]:
                per, tot = run_portfolio(data, start, end, cap, Params(split=0.5, lot=0, **vkw))
                perl = {c: simulate(data[c], start, end, cap / 3, Params(split=0.5, lot=BYBIT_LOT[c], **vkw)) for c in COINS}
                eq_l = sum(r["equity"] for r in perl.values())
                tl = tot.copy()
                tl["equity"] = eq_l
                m_frac, m_lot = metrics(tot, cap), metrics(tl, cap)
                in_lot = {c: float(r["in_pos"].mean()) for c, r in perl.items()}
                results[per_name].setdefault("accounts", {}).setdefault(f"{int(cap)}", {})[vn] = dict(
                    fractional=m_frac, bybit_lots=m_lot, time_in_with_lots=in_lot
                )
                print(
                    f"account {cap:.0f} USDT, {vn}, 50/50 EW: {m_frac['avg_month_usdt']:+.2f} USDT/month (fractional) | "
                    f"{m_lot['avg_month_usdt']:+.2f} USDT/month with Bybit lots, time in pos per coin "
                    + ", ".join(f"{c} {v*100:.0f}%" for c, v in in_lot.items())
                )

    # minimum capital per coin at the last close, Bybit perp min qty
    last = {c: float(data[c]["perp_close"].iloc[-1]) for c in COINS}
    mins = {c: {"price": last[c], "min_perp_notional": BYBIT_LOT[c] * last[c],
                "min_capital_1x": BYBIT_LOT[c] * last[c] / 0.5,
                "min_capital_3x": BYBIT_LOT[c] * last[c] / 0.75} for c in COINS}
    results["min_capital_bybit"] = mins
    print("\nMin capital per coin (Bybit perp min qty, last close):")
    for c, v in mins.items():
        print(f"  {c}: price {v['price']:.2f}, min perp notional {v['min_perp_notional']:.2f} USDT, "
              f"min capital 1x {v['min_capital_1x']:.2f}, 3x {v['min_capital_3x']:.2f}")

    # funding stats by year (all history) for the report
    yearly = {}
    for c in COINS:
        d = data[c]
        g = d.groupby(d.index.year)
        yearly[c] = {int(y): dict(ann=float(x["funding"].sum() / len(x) * 365),
                                  pct_events_neg=float(x["n_neg"].sum() / x["n_events"].sum()))
                     for y, x in g}
    results["funding_by_year"] = yearly
    print("\nFunding by year (annualised mean, % events negative):")
    for c in COINS:
        print("  " + c + ": " + ", ".join(f"{y} {v['ann']*100:+.1f}% ({v['pct_events_neg']*100:.0f}%)" for y, v in yearly[c].items()))

    Path(args.out).write_text(json.dumps(results, indent=1, default=float))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
