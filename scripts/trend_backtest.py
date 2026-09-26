#!/usr/bin/env python3
"""
Round 3: diversified, volatility-targeted, long-only trend following on daily
bars across a survivorship-bias-free top-35 USDT universe (Binance spot data).

The rules are pre-registered in reports/trend_following.md (written before the
first run) and are the defaults of Config below. Everything else (the grid) is
reported for robustness only.

Inputs  (from scripts/trend_download.py): user_data/trend/panel_*.parquet,
         user_data/trend/universe.csv
         OKX USDT Simple Earn history: user_data/funding/okx_savings_usdt.csv
Outputs: reports/trend_following.json (+ tables printed to stdout)

Usage:  .venv/bin/python scripts/trend_backtest.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TD = ROOT / "user_data" / "trend"
SAVINGS_CSV = ROOT / "user_data" / "funding" / "okx_savings_usdt.csv"
OUT_JSON = ROOT / "reports" / "trend_following.json"

PERIODS = {
    "dev": ("2018-01-01", "2023-12-31"),
    "holdout": ("2024-01-01", "2026-09-25"),
}


@dataclass(frozen=True)
class Config:
    lookbacks: tuple = (20, 50, 100, 200)
    target_vol: float = 0.40
    max_w: float = 0.20
    vol_window: int = 60
    vol_min_obs: int = 20
    band: float = 0.02            # skip |dw| < band * equity (exits always executed)
    fee: float = 0.001            # per side
    slippage: float = 0.0005      # per side
    top_n: int = 35               # use the top-N of the stored (top-35) universe
    exec_price: str = "open"      # "open" of t+1, or "close" of t+1
    extra_delay: int = 0          # extra days between signal and execution
    cheat: bool = False           # deliberate look-ahead (uses close of the execution day)
    pre_rate: float = 0.0         # savings APR assumed before OKX history starts
    capital: float = 1.0
    min_order: float = 0.0        # absolute min order value (USDT); 5 for Bybit spot

    @property
    def cost(self) -> float:
        return self.fee + self.slippage


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
def load_panel() -> dict:
    close = pd.read_parquet(TD / "panel_close.parquet")
    opn = pd.read_parquet(TD / "panel_open.parquet")
    idx = pd.date_range(close.index.min(), pd.Timestamp("2026-09-25", tz="UTC"), freq="D")
    close = close.reindex(idx)
    opn = opn.reindex(idx)[close.columns]
    last = close.apply(pd.Series.last_valid_index)
    li = idx.get_indexer(pd.DatetimeIndex(last.tolist()))
    assert (li >= 0).all(), "last-valid index lookup failed"
    close_ff = causal_ffill(close)
    uni = pd.read_csv(TD / "universe.csv")
    uni["month_end"] = pd.to_datetime(uni["month_end"]).dt.tz_localize("UTC")
    return dict(idx=idx, cols=list(close.columns), close=close, open=opn, close_ff=close_ff,
                last_i=pd.Series(li, index=close.columns), uni=uni)


def causal_ffill(close: pd.DataFrame) -> pd.DataFrame:
    """Carry the last close over short gaps only (<= 6 days; longer gaps are split into
    separate instruments by the downloader). Uses past rows only."""
    return close.ffill(limit=6)


def savings_daily(idx: pd.DatetimeIndex, pre_rate: float) -> pd.Series:
    s = pd.read_csv(SAVINGS_CSV, parse_dates=["time"]).set_index("time")["lending_apr"]
    g = np.log1p(s / (365 * 24)).groupby(s.index.floor("D")).sum()
    g = np.expm1(g).reindex(idx)
    start = s.index.min().floor("D")
    g[idx < start] = (1 + pre_rate) ** (1 / 365) - 1
    return g.fillna(g.ffill()).fillna(0.0)


# --------------------------------------------------------------------------- #
# Signals (causal: every value at row t uses rows <= t only)
# --------------------------------------------------------------------------- #
def compute_features(close_ff: pd.DataFrame, cfg: Config) -> dict:
    c = close_ff
    inds = []
    for n in cfg.lookbacks:
        sma = c.rolling(n, min_periods=n).mean()
        inds.append((c > sma).astype(float))
        inds.append((c > c.shift(n)).astype(float))
    s = sum(inds) / len(inds)
    r = c.pct_change(fill_method=None)
    sig = r.rolling(cfg.vol_window, min_periods=cfg.vol_min_obs).std() * np.sqrt(365)
    return dict(s=s, r=r, sig=sig)


def universe_at(uni: pd.DataFrame, t: pd.Timestamp, top_n: int) -> list[str]:
    me = uni["month_end"][uni["month_end"] <= t]
    if me.empty:
        return []
    m = me.max()
    u = uni[(uni["month_end"] == m) & (uni["rank"] <= top_n)]
    return u["symbol"].tolist()


def target_weights(feat: dict, uni: pd.DataFrame, t: pd.Timestamp, cfg: Config) -> pd.Series:
    """Weights decided with information up to the close of day t."""
    members = universe_at(uni, t, cfg.top_n)
    if not members:
        return pd.Series(dtype=float)
    sig = feat["sig"].loc[t, members]
    s = feat["s"].loc[t, members]
    ok = sig.notna() & (sig > 0)
    members = list(sig[ok].index)
    if not members:
        return pd.Series(dtype=float)
    inv = 1.0 / sig[members]
    base = inv / inv.sum()
    win = feat["r"].loc[:t, members].iloc[-cfg.vol_window:]
    cov = win.fillna(0.0).cov().values * 365
    vref = float(np.sqrt(max(base.values @ cov @ base.values, 1e-12)))
    k = min(1.0, cfg.target_vol / vref)
    w = (k * s[members] * base).clip(upper=cfg.max_w)
    w = w[w > 0]
    if w.sum() > 1:
        w = w / w.sum()
    return w


# --------------------------------------------------------------------------- #
# Simulation engine
# --------------------------------------------------------------------------- #
def simulate(P: dict, sav: pd.Series, start: str, end: str, cfg: Config, schedule: dict,
             band: float, name: str) -> dict:
    """schedule: {execution_date: target weight Series}. Executes at open (or close) of that day."""
    idx = P["idx"]
    cols = P["cols"]
    col_i = {c: i for i, c in enumerate(cols)}
    t0 = idx.get_loc(pd.Timestamp(start, tz="UTC"))
    t1 = idx.get_loc(pd.Timestamp(end, tz="UTC"))
    O = P["open"].values
    C = P["close"].values
    CF = P["close_ff"].values
    last_i = P["last_i"].values
    last_global = len(idx) - 1
    cost = cfg.cost
    sav_v = sav.values

    qty = np.zeros(len(cols))
    cash = cfg.capital
    eq, expo, npos = [], [], []
    traded = 0.0
    n_trades = n_skip_min = n_skip_band = 0
    dust_days = 0
    for d in range(t0, t1 + 1):
        date = idx[d]
        if date in schedule:
            tw = schedule[date]
            px = C[d] if cfg.exec_price == "close" else O[d]
            # value positions at the execution price (fallback previous close)
            pv = np.where(np.isnan(px), CF[d - 1], px)
            held = qty * np.nan_to_num(pv)
            equity = cash + held.sum()
            tgt = np.zeros(len(cols))
            for s_, w_ in tw.items():
                tgt[col_i[s_]] = w_ * equity
            delta = tgt - held
            orders = []
            for i in np.nonzero((np.abs(delta) > 1e-12))[0]:
                if np.isnan(px[i]):
                    continue  # not tradeable today
                full_exit = tgt[i] == 0 and held[i] > 0
                if not full_exit and abs(delta[i]) < band * equity:
                    n_skip_band += 1
                    continue
                if cfg.min_order > 0 and abs(delta[i]) < cfg.min_order:
                    n_skip_min += 1
                    continue
                orders.append(i)
            sells = [i for i in orders if delta[i] < 0]
            buys = [i for i in orders if delta[i] > 0]
            for i in sells:
                v = -delta[i]
                qty[i] -= v / px[i]
                if tgt[i] == 0:
                    qty[i] = 0.0
                cash += v * (1 - cost)
                traded += v
                n_trades += 1
            need = sum(delta[i] * (1 + cost) for i in buys)
            scale = min(1.0, cash / need) if need > 0 else 1.0
            for i in buys:
                v = delta[i] * scale
                if cfg.min_order > 0 and v < cfg.min_order:
                    n_skip_min += 1
                    continue
                qty[i] += v / px[i]
                cash -= v * (1 + cost)
                traded += v
                n_trades += 1
        # forced exit on delisting / end of a price segment
        for i in np.nonzero(qty > 0)[0]:
            if last_i[i] == d and d < last_global:
                v = qty[i] * CF[d, i]
                cash += v * (1 - cost)
                traded += v
                qty[i] = 0.0
                n_trades += 1
        cash *= 1 + sav_v[d]
        hv = qty * np.nan_to_num(CF[d])
        e = cash + hv.sum()
        eq.append(e)
        expo.append(hv.sum() / e if e > 0 else 0.0)
        pos_mask = hv > 1e-9 * cfg.capital
        npos.append(int(pos_mask.sum()))
        if cfg.min_order > 0 and ((hv > 0) & (hv < cfg.min_order)).any():
            dust_days += 1
    eqs = pd.Series(eq, index=idx[t0:t1 + 1])
    return dict(name=name, equity=eqs, exposure=pd.Series(expo, index=eqs.index),
                npos=pd.Series(npos, index=eqs.index), traded=traded, n_trades=n_trades,
                n_skip_min=n_skip_min, n_skip_band=n_skip_band, dust_days=dust_days,
                capital=cfg.capital)


def strategy_schedule(P: dict, feat: dict, start: str, end: str, cfg: Config) -> dict:
    idx = P["idx"]
    t0 = idx.get_loc(pd.Timestamp(start, tz="UTC"))
    t1 = idx.get_loc(pd.Timestamp(end, tz="UTC"))
    sched = {}
    lag = 1 + cfg.extra_delay
    for d in range(t0, t1 + 1):
        date = idx[d]
        if date.dayofweek == 0 or d == t0:  # Monday execution, plus the first day
            sig_d = d - lag
            if cfg.cheat:
                sig_d = d  # uses the close of the execution day: look-ahead on purpose
            if sig_d < 0:
                continue
            sched[date] = target_weights(feat, P["uni"], idx[sig_d], cfg)
    return sched


def ew_schedule(P: dict, start: str, end: str, cfg: Config) -> dict:
    idx = P["idx"]
    t0 = idx.get_loc(pd.Timestamp(start, tz="UTC"))
    t1 = idx.get_loc(pd.Timestamp(end, tz="UTC"))
    sched = {}
    for d in range(t0, t1 + 1):
        if idx[d].day == 1 or d == t0:
            t = idx[d - 1]
            mem = [m for m in universe_at(P["uni"], t, cfg.top_n) if not np.isnan(P["close"].at[t, m])]
            if mem:
                sched[idx[d]] = pd.Series(1.0 / len(mem), index=mem)
    return sched


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def metrics(res: dict, sav: pd.Series) -> dict:
    e = res["equity"]
    cap = res["capital"]
    full = pd.concat([pd.Series([cap], index=[e.index[0] - pd.Timedelta(days=1)]), e])
    r = full.pct_change().dropna()
    sv = sav.reindex(r.index).fillna(0.0)
    days = len(e)
    tot = e.iloc[-1] / cap - 1
    cagr = (e.iloc[-1] / cap) ** (365 / days) - 1
    vol = r.std() * np.sqrt(365)
    sh0 = r.mean() / r.std() * np.sqrt(365) if r.std() > 1e-6 else np.nan
    ex = r - sv
    shs = ex.mean() / ex.std() * np.sqrt(365) if ex.std() > 1e-6 else np.nan
    dd = (full / full.cummax() - 1).min()
    m = full.resample("ME").last()
    mr = m.pct_change().dropna()
    mr_all = pd.concat([pd.Series([full.resample("ME").last().iloc[0] / cap - 1],
                                  index=[m.index[0]]), mr])
    yrs = {}
    for y in sorted(set(e.index.year)):
        ey = full[full.index.year <= y].iloc[-1]
        prev = full[full.index.year < y]
        e0 = prev.iloc[-1] if len(prev) else cap
        yrs[str(y)] = float(ey / e0 - 1)
    avg_eq = float(e.mean())
    return dict(
        total=float(tot), cagr=float(cagr), vol=float(vol), sharpe=float(sh0), sharpe_vs_savings=float(shs),
        max_dd=float(dd), worst_month=float(mr_all.min()),
        turnover_per_year=float(res["traded"] / avg_eq / (days / 365)),
        avg_exposure=float(res["exposure"].mean()),
        pct_days_invested=float((res["exposure"] > 0.01).mean()),
        avg_positions=float(res["npos"].mean()),
        n_trades=int(res["n_trades"]), yearly=yrs,
    )


def savings_result(P: dict, sav: pd.Series, start: str, end: str, capital: float = 1.0) -> dict:
    idx = P["idx"]
    s = sav[(idx >= pd.Timestamp(start, tz="UTC")) & (idx <= pd.Timestamp(end, tz="UTC"))]
    eq = capital * (1 + s).cumprod()
    z = pd.Series(0.0, index=eq.index)
    return dict(name="savings", equity=eq, exposure=z, npos=z, traded=0.0, n_trades=0,
                n_skip_min=0, n_skip_band=0, dust_days=0, capital=capital)


# --------------------------------------------------------------------------- #
# Look-ahead checks
# --------------------------------------------------------------------------- #
def lookahead_truncation_check(P: dict, cfg: Config, n: int = 25, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    idx = P["idx"]
    feat_full = compute_features(P["close_ff"], cfg)
    cand = [d for d in idx if d >= pd.Timestamp("2018-03-01", tz="UTC") and d.dayofweek == 6]
    picks = sorted(rng.choice(len(cand), size=n, replace=False))
    max_diff = 0.0
    for p in picks:
        t = cand[p]
        trunc = P["close"].loc[:t]
        cff = causal_ffill(trunc)  # rebuilt from the truncated raw data only
        feat_t = compute_features(cff, cfg)
        uni_t = P["uni"][P["uni"]["month_end"] <= t]
        w_full = target_weights(feat_full, P["uni"], t, cfg)
        w_tr = target_weights(feat_t, uni_t, t, cfg)
        a = w_full.reindex(w_full.index.union(w_tr.index)).fillna(0)
        b = w_tr.reindex(a.index).fillna(0)
        max_diff = max(max_diff, float((a - b).abs().max()) if len(a) else 0.0)
    return dict(dates_checked=n, max_abs_weight_diff=max_diff, passed=bool(max_diff < 1e-9))


def universe_causality_check(n: int = 6) -> dict:
    """Rebuild a few month-end universes from volume data truncated at that month-end."""
    spec = importlib.util.spec_from_file_location("td", ROOT / "scripts" / "trend_download.py")
    td = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(td)
    qv = pd.read_parquet(TD / "panel_quote_volume.parquet")
    close = pd.read_parquet(TD / "panel_close.parquet")
    uni = pd.read_csv(TD / "universe.csv")
    mes = sorted(uni["month_end"].unique())
    picks = [mes[i] for i in np.linspace(3, len(mes) - 2, n).astype(int)]
    ok = True
    for m in picks:
        t = pd.Timestamp(m, tz="UTC")
        u2 = td.build_universe(qv.loc[:t], close.loc[:t], int(uni["rank"].max()))
        a = u2[u2["month_end"] == m]["symbol"].tolist()
        b = uni[uni["month_end"] == m]["symbol"].tolist()
        ok &= a == b
    return dict(month_ends_checked=[str(x) for x in picks], passed=bool(ok))


# --------------------------------------------------------------------------- #
def pct(x, nd=1):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x * 100:+.{nd}f}%"


def run_strategy(P, sav, per, cfg, feat_cache):
    key = (cfg.lookbacks, cfg.vol_window)
    if key not in feat_cache:
        feat_cache[key] = compute_features(P["close_ff"], cfg)
    start, end = PERIODS[per]
    sched = strategy_schedule(P, feat_cache[key], start, end, cfg)
    return simulate(P, sav, start, end, cfg, sched, cfg.band, "trend")


def main() -> None:
    P = load_panel()
    base = Config()
    sav = savings_daily(P["idx"], base.pre_rate)
    sav5 = savings_daily(P["idx"], 0.05)
    feat_cache: dict = {}
    out: dict = {"config": {k: (list(v) if isinstance(v, tuple) else v) for k, v in asdict(base).items()},
                 "periods": PERIODS, "results": {}, "grid": {}, "feasibility": {}, "lookahead": {}}

    # universe description
    uni = P["uni"]
    out["universe"] = dict(
        month_ends=int(uni["month_end"].nunique()),
        size_min=int(uni.groupby("month_end").size().min()),
        size_max=int(uni.groupby("month_end").size().max()),
        size_first=int(uni[uni["month_end"] == uni["month_end"].min()].shape[0]),
        first_month_end=str(uni["month_end"].min().date()),
        distinct=int(uni["symbol"].nunique()),
        delisted=sorted(s for s in uni["symbol"].unique()
                        if P["last_i"][s] < len(P["idx"]) - 4),
    )
    print(f"Universe: {out['universe']['distinct']} distinct instruments, "
          f"{len(out['universe']['delisted'])} later stopped trading")

    for per, (start, end) in PERIODS.items():
        res = {}
        for tv in (0.20, 0.40, 0.60):
            for cost_name, slip in (("base", 0.0005), ("stress", 0.001)):
                cfg = replace(base, target_vol=tv, slippage=slip)
                r = run_strategy(P, sav, per, cfg, feat_cache)
                res[f"trend_tv{int(tv * 100)}_{cost_name}"] = metrics(r, sav)
        for cost_name, slip in (("base", 0.0005), ("stress", 0.001)):
            cfg = replace(base, slippage=slip)
            ew = simulate(P, sav, start, end, cfg, ew_schedule(P, start, end, cfg), 0.0, "ew")
            res[f"ew_bh_{cost_name}"] = metrics(ew, sav)
            btc = simulate(P, sav, start, end, cfg, {pd.Timestamp(start, tz="UTC"): pd.Series({"BTC": 1.0})},
                           0.0, "btc")
            res[f"btc_bh_{cost_name}"] = metrics(btc, sav)
        res["savings"] = metrics(savings_result(P, sav, start, end), sav)
        # extra (added after the first run, not pre-registered): static BTC + savings mix with the
        # same average exposure as the 40% strategy, rebalanced monthly. Answers "does the timing
        # add anything beyond simply holding less crypto?"
        wexp = res["trend_tv40_base"]["avg_exposure"]
        mix_sched = {d: pd.Series({"BTC": wexp}) for d in pd.date_range(start, end, freq="MS", tz="UTC")}
        mix_sched.setdefault(pd.Timestamp(start, tz="UTC"), pd.Series({"BTC": wexp}))
        res["btc_savings_mix_same_exposure"] = metrics(
            simulate(P, sav, start, end, base, mix_sched, 0.0, "mix"), sav)
        res["btc_savings_mix_same_exposure"]["btc_weight"] = wexp
        # sensitivity: 5% APR on cash before OKX history (only matters in dev)
        cfg5 = replace(base, pre_rate=0.05)
        r5 = run_strategy(P, sav5, per, cfg5, feat_cache)
        res["trend_tv40_base_pre5"] = metrics(r5, sav5)
        res["savings_pre5"] = metrics(savings_result(P, sav5, start, end), sav5)
        out["results"][per] = res

        print(f"\n=== {per} {start} -> {end} ===")
        print("| name | CAGR | total | vol | Sharpe | Sharpe-sav | MaxDD | worst mo | turnover/yr | avg expo |")
        for k, m in res.items():
            print(f"| {k} | {pct(m['cagr'])} | {pct(m['total'])} | {m['vol']*100:.1f}% | {m['sharpe']:.2f} | "
                  f"{m['sharpe_vs_savings']:.2f} | {pct(m['max_dd'])} | {pct(m['worst_month'])} | "
                  f"{m['turnover_per_year']:.1f}x | {m['avg_exposure']*100:.0f}% |")

    # robustness grid (base costs, 40% target unless varied)
    grid = {
        "lb20": replace(base, lookbacks=(20,)),
        "lb50": replace(base, lookbacks=(50,)),
        "lb100": replace(base, lookbacks=(100,)),
        "lb200": replace(base, lookbacks=(200,)),
        "no_band": replace(base, band=0.0),
        "exec_close_t1": replace(base, exec_price="close"),
        "delay_+1d": replace(base, extra_delay=1),
        "top20": replace(base, top_n=20),
        "CHEAT_lookahead": replace(base, cheat=True),
    }
    for g, cfg in grid.items():
        out["grid"][g] = {}
        for per in PERIODS:
            r = run_strategy(P, sav, per, cfg, feat_cache)
            out["grid"][g][per] = metrics(r, sav)
    print("\n=== robustness grid (40% target, base costs) ===")
    print("| variant | dev CAGR | dev Sharpe | dev MaxDD | holdout CAGR | holdout Sharpe | holdout MaxDD |")
    for g, v in out["grid"].items():
        d, h = v["dev"], v["holdout"]
        print(f"| {g} | {pct(d['cagr'])} | {d['sharpe']:.2f} | {pct(d['max_dd'])} | {pct(h['cagr'])} | "
              f"{h['sharpe']:.2f} | {pct(h['max_dd'])} |")

    # small-account feasibility (Bybit spot 5 USDT minimum order)
    for per in PERIODS:
        out["feasibility"][per] = {}
        for cap in (100.0, 1000.0):
            for mo in (0.0, 5.0):
                cfg = replace(base, capital=cap, min_order=mo)
                r = run_strategy(P, sav, per, cfg, feat_cache)
                m = metrics(r, sav)
                held = r["npos"][r["exposure"] > 0.01]
                m.update(n_skip_min=r["n_skip_min"], n_skip_band=r["n_skip_band"], dust_days=r["dust_days"],
                         avg_positions_when_invested=float(held.mean()) if len(held) else 0.0,
                         max_positions=int(r["npos"].max()), final_equity=float(r["equity"].iloc[-1]))
                out["feasibility"][per][f"cap{int(cap)}_min{int(mo)}"] = m
    print("\n=== small accounts (40% target, base costs) ===")
    for per, v in out["feasibility"].items():
        for k, m in v.items():
            print(f"{per} {k}: CAGR {pct(m['cagr'])} final {m['final_equity']:.2f} trades {m['n_trades']} "
                  f"skipped(min) {m['n_skip_min']} skipped(band) {m['n_skip_band']} "
                  f"avg pos {m['avg_positions_when_invested']:.1f} max pos {m['max_positions']}")

    # look-ahead checks
    out["lookahead"]["truncation"] = lookahead_truncation_check(P, base)
    out["lookahead"]["universe"] = universe_causality_check()
    print("\nLook-ahead:", out["lookahead"])
    assert out["lookahead"]["truncation"]["passed"], "signals use future data!"
    assert out["lookahead"]["universe"]["passed"], "universe uses future data!"

    OUT_JSON.write_text(json.dumps(out, indent=1, default=float))
    print(f"\nWrote {OUT_JSON}")


if __name__ == "__main__":
    sys.exit(main())
