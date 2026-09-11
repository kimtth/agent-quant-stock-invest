"""Volatility-targeted trend experiments on actual USD ETFs.

Original variants, translated:
    V-continuous: exposure = clip(target_vol / realized_volatility(20_days), 0, 2)
    V-step: 2x / 1x / defense by realized-volatility range
Python uses configurable cap (default 2), multiplies continuous exposure by
the trend state, and measures volatility in annualized percent. Step exposure
selects a 2x ETF, a 1x ETF, or a defensive basket.
Historical parameters are retained for research, not US performance claims.
GLOBAL_RESEARCH_CONFIG is read by market_config before module import; this
module performs no data loading or reporting until main() is called.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtest_etf_combos import load_all
from market_config import CONFIG

COST = CONFIG.cost
WARMUP = CONFIG.warmup

NDX2, NDX = CONFIG.symbol("growth_2x"), CONFIG.symbol("growth")
GOLD2, GOLD = CONFIG.symbol("gold_2x"), CONFIG.symbol("gold")
K2, KOSPI = CONFIG.symbol("equity_2x"), CONFIG.symbol("equity")
SOX2, SOX = CONFIG.symbol("semiconductor_2x"), CONFIG.symbol("semiconductor")
BOND, DOLLAR = CONFIG.symbol("treasury"), CONFIG.symbol("dollar")
HISTORICAL_CUT = pd.Timestamp("2026-05-31")


def require_symbols(data, tks):
    """Fail explicitly rather than silently changing the requested universe."""
    missing = sorted({t for t in tks if t not in data or data[t].empty})
    if missing:
        raise ValueError(f"Missing or empty ETF data: {', '.join(missing)}")


def panel(data, tks):
    require_symbols(data, tks)
    if not tks:
        raise ValueError("At least one ETF is required")
    cal = pd.DatetimeIndex(sorted(set().union(*[set(data[t].index) for t in tks])))
    close = pd.DataFrame({t: data[t]["Close"] for t in tks}).reindex(cal).ffill()
    high = pd.DataFrame({t: data[t]["High"] for t in tks}).reindex(cal).ffill()
    first = max(data[t].index[0] for t in tks)
    last = min(data[t].index[-1] for t in tks)
    cal = cal[(cal >= first) & (cal <= last)]
    if len(cal) <= WARMUP + 1:
        raise ValueError(f"Insufficient common ETF history after {WARMUP} warmup sessions")
    return close.loc[cal], high.loc[cal]


def trend_state(close, high, ma=200, trail=12.0, entry_dd=3.0, mom=60):
    above = (close >= close.rolling(ma).mean()).to_numpy()
    hh = high.rolling(20).max()
    dd = ((hh - close) / hh * 100).to_numpy()
    mo = (close / close.shift(mom) - 1).to_numpy()
    out, on = np.zeros(len(close)), False
    for i in range(len(close)):
        if np.isnan(dd[i]) or np.isnan(mo[i]):
            continue
        if on:
            if not above[i] or dd[i] >= trail:
                on = False
        elif above[i] and dd[i] <= entry_dd and mo[i] > 0:
            on = True
        out[i] = 1.0 if on else 0.0
    return pd.Series(out, index=close.index)


def stats(port, label="", note="", warmup=WARMUP):
    port = port.dropna().iloc[warmup:]
    if len(port) < 2:
        raise ValueError("At least two evaluation sessions are required")
    e = (1 + port).cumprod()
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    ddc = e / e.cummax() - 1
    pre = e.loc[:HISTORICAL_CUT]
    pyrs = (pre.index[-1] - pre.index[0]).days / 365.25 if len(pre) > 1 else 0
    return {
        "label": label,
        "note": note,
        "start": e.index[0].date(),
        "end": e.index[-1].date(),
        "cagr": (e.iloc[-1] ** (1 / yrs) - 1) * 100,
        "mdd": ddc.min() * 100,
        "pre_cagr": (pre.iloc[-1] ** (1 / pyrs) - 1) * 100 if pyrs > 0 else np.nan,
        "pre_mdd": (pre / pre.cummax() - 1).min() * 100 if pyrs > 0 else np.nan,
        "sharpe": port.mean() / port.std() * np.sqrt(252) if port.std() > 0 else 0.0,
        "mdd_from": e.loc[: ddc.idxmin()].idxmax().date(),
        "mdd_to": ddc.idxmin().date(),
        "curve": e,
    }


def report_rows(rows, data):
    """Report native windows without ranking incomparable research runs."""
    require_symbols(data, ["SPY", "QQQ"])
    print(f"USD research; per-side cost {COST:.2%}; warmup {WARMUP} sessions; benchmark {CONFIG.benchmark}")
    print("Native windows may differ: no cross-window ranking or winner designation.")
    print("Legacy split is descriptive only, not a US crash boundary or validation set.")
    print("Execution/cost models differ; matched dates alone do not prove superiority.")
    for r in rows:
        e = r["curve"]
        print(f"\n{r.get('label', '')}: {e.index[0].date()} .. {e.index[-1].date()}")
        print(f"  CAGR {r['cagr']:.2f}% | MDD {r['mdd']:.2f}% | Sharpe {r['sharpe']:.2f}")
        pre = e.loc[:HISTORICAL_CUT]
        if len(pre) > 1:
            print(f"  Split {pre.index[0].date()} .. {pre.index[-1].date()}: "
                  f"CAGR {r['pre_cagr']:.2f}% | MDD {r['pre_mdd']:.2f}%")
        else:
            print("  Historical split: insufficient observations")
        for tk in ("SPY", "QQQ"):
            c = data[tk]["Close"].reindex(e.index)
            if c.isna().any():
                print(f"  {tk}: baseline unavailable on exact strategy dates; no comparison")
                continue
            years = (c.index[-1] - c.index[0]).days / 365.25
            bc = ((c.iloc[-1] / c.iloc[0]) ** (1 / years) - 1) * 100
            bm = (c / c.cummax() - 1).min() * 100
            print(f"  {tk} gross hold (same dates): CAGR {bc:.2f}% | MDD {bm:.2f}%")
        print(f"  Drawdown: {r['mdd_from']} .. {r['mdd_to']}")
        annual = e.resample("YE").last().pct_change() * 100
        annual.iloc[0] = (e.resample("YE").last().iloc[0] - 1) * 100
        print("  Annual returns (%): " + ", ".join(f"{d.year}: {v:.1f}" for d, v in annual.items()))
        if r.get("note"):
            print(f"  {r['note']}")


def build(data, sig_tk, lev2, lev1, defense, tgt_vol, mode, ma, trail, cap=2.0):
    tks = sorted({sig_tk, lev2, lev1, *defense})
    close, high = panel(data, tks)
    ret = close.pct_change().fillna(0.0).clip(-0.5, 0.5)
    d_ret = ret[defense].mean(axis=1)

    on = trend_state(close[sig_tk], high[sig_tk], ma=ma, trail=trail)
    rv = ret[sig_tk].rolling(20).std() * np.sqrt(252) * 100  # Annualized 1x volatility, percent.

    if mode == "cont":
        w = (tgt_vol / rv).clip(0, cap).fillna(0.0) * on
        # A 2x ETF needs capital weight w/2 for nominal exposure w.
        pos2 = (w / 2).clip(0, 1)
        pos1 = pd.Series(0.0, index=close.index)
    else:  # Step exposure.
        lo, hi = tgt_vol, tgt_vol * 1.6
        pos2 = ((rv <= lo) & (on > 0)).astype(float)
        pos1 = ((rv > lo) & (rv <= hi) & (on > 0)).astype(float)

    h2, h1 = pos2.shift(1).fillna(0.0), pos1.shift(1).fillna(0.0)
    cash_w = (1 - h2 - h1).clip(0, 1)
    r = h2 * ret[lev2] + h1 * ret[lev1] + cash_w * d_ret
    cost = (h2.diff().abs().fillna(0) + h1.diff().abs().fillna(0)) * COST
    return r - cost


def main():
    data, _v, _r, _rep = load_all()

    DEF = [BOND, GOLD, DOLLAR]
    rows = []

    for tgt in (12, 15, 18, 20, 25):
        for trail in (10.0, 12.0, 15.0):
            r = build(data, NDX, NDX2, NDX, DEF, tgt, "cont", 200, trail)
            rows.append(stats(r, f"Continuous target {tgt}% trail {trail:.0f}", "Continuous-allocation experiment"))

    for tgt in (15, 18, 20, 22, 25):
        for trail in (10.0, 12.0, 15.0):
            r = build(data, NDX, NDX2, NDX, DEF, tgt, "step", 200, trail)
            rows.append(stats(r, f"Step low-vol {tgt}% trail {trail:.0f}", "Discrete-allocation experiment"))

    # Two- and three-sleeve step-exposure families.
    for tgt in (18, 20, 22):
        rn = build(data, NDX, NDX2, NDX, DEF, tgt, "step", 200, 12.0)
        rg = build(data, GOLD, GOLD2, GOLD, DEF, tgt, "step", 200, 12.0)
        pair = pd.concat([rn, rg], axis=1).dropna()
        rows.append(stats(pair.mean(axis=1), f"Growth + gold step {tgt}%", "Two sleeves"))
        rk = build(data, KOSPI, K2, KOSPI, DEF, tgt, "step", 200, 12.0)
        trio = pd.concat([rn, rg, rk], axis=1).dropna()
        rows.append(stats(trio.mean(axis=1), f"Growth + gold + equity step {tgt}%", "Three sleeves"))

    report_rows(rows, data)


if __name__ == "__main__":
    main()
