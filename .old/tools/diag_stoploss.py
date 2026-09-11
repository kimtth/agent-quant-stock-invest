"""Trace stop-loss fills, gap slippage and repeated losses in USD strategies.

The returned trade-log column names and reason codes retain their legacy API;
console labels are English. Trade returns are gross price returns, not
portfolio-weighted contributions or net-of-cost returns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtest_etf_combos import (
    MAX_POS,
    STRATEGIES,
    build_features,
    load_all,
    price_score,
)
from backtest_voltarget import require_symbols
from market_config import CONFIG

COST = CONFIG.cost
WARMUP = CONFIG.warmup


def run_logged(strat, data, feats, vix, target, stop, max_pos=MAX_POS, regime=None):
    """Historical next-open/intraday execution logic with fill-level logs."""
    require_symbols(data, strat.tickers)
    names = list(data.keys())
    if not names or any(len(data[n]) <= WARMUP for n in names):
        raise ValueError(f"Each ETF needs more than {WARMUP} sessions for stop diagnostics")
    cal = sorted(set().union(*[set(d.index) for d in data.values()]))
    ready = {n: data[n].index[WARMUP] for n in names}
    cal = [d for d in cal if d >= min(ready.values())]
    if len(cal) < 2:
        raise ValueError("At least two evaluation sessions are required")

    cash, pos = 1.0, {}
    pend_buy, pend_sell = [], []
    curve, log = [], []
    mark = pd.DataFrame({n: data[n]["Close"] for n in names}).reindex(cal).ffill()

    for day in cal:
        px = {n: data[n].loc[day] for n in names if day in data[n].index}
        mk = mark.loc[day]

        for n in pend_sell:
            if n in pos and n in px:
                o = px[n]["Open"]
                cash += pos[n]["shares"] * o * (1 - COST)
                log.append((pos[n]["date"], day, n, o / pos[n]["entry"] - 1, "신호"))
                del pos[n]
        if pend_buy:
            slots = max_pos - len(pos)
            equity = cash + sum(pos[n]["shares"] * mk[n] for n in pos)
            for n in pend_buy[:slots]:
                if n in pos or n not in px:
                    continue
                budget = min(cash, equity / max_pos)
                if budget <= 0:
                    break
                o = px[n]["Open"]
                sh = budget / (o * (1 + COST))
                cash -= sh * o * (1 + COST)
                pos[n] = {"shares": sh, "entry": o, "date": day}
        pend_buy, pend_sell = [], []

        for n in list(pos):
            if n not in px:
                continue
            e = pos[n]["entry"]
            lo, hi_ = px[n]["Low"], px[n]["High"]
            exit_px, why = None, ""
            if stop is not None and lo <= e * (1 + stop / 100):
                exit_px, why = min(e * (1 + stop / 100), px[n]["Open"]), "손절"
            elif target is not None and hi_ >= e * (1 + target / 100):
                exit_px, why = max(e * (1 + target / 100), px[n]["Open"]), "목표"
            if exit_px is not None:
                cash += pos[n]["shares"] * exit_px * (1 - COST)
                log.append((pos[n]["date"], day, n, exit_px / e - 1, why))
                del pos[n]

        equity = cash + sum(pos[n]["shares"] * mk[n] for n in pos)
        curve.append((day, equity))

        vrow = vix.reindex([day], method="ffill").iloc[0]
        v = {"vix": float(vrow["vix"]), "vixchg5": float(vrow["vixchg5"])}
        if np.isnan(v["vix"]):
            continue

        for n in list(pos):
            f = feats[n]
            if day not in f.index:
                continue
            row = f.loc[day].to_dict()
            if any(pd.isna(row[k]) for k in ("disp10", "disp20", "disp60", "ret10", "ret20", "ret60")):
                continue
            if strat.sell(row, v):
                pend_sell.append(n)

        cands = []
        risk_on = True if regime is None else bool(regime.get(day, 0.0))
        for n in names:
            if not risk_on:
                break
            if n in pos or n in pend_sell or day not in feats[n].index or day < ready[n]:
                continue
            row = feats[n].loc[day].to_dict()
            if any(pd.isna(x) for x in row.values()):
                continue
            try:
                if strat.buy(row, v):
                    cands.append(n)
            except (TypeError, ValueError):
                continue
        if cands:
            sc = price_score(feats, day, cands)
            pend_buy = sorted(cands, key=lambda n: -sc.get(n, 0))

    eq = pd.Series(dict(curve)).sort_index().dropna()
    eq = eq[eq > 0]
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    dd = (eq / eq.cummax()) - 1
    trough = dd.idxmin()
    peak = eq.loc[:trough].idxmax()
    return {
        "cagr": (eq.iloc[-1] ** (1 / yrs) - 1) * 100,
        "mdd": dd.min() * 100,
        "peak": peak,
        "trough": trough,
        "eq": eq,
        "log": pd.DataFrame(log, columns=["진입", "청산", "종목", "수익률", "사유"]),
    }


def show(tag, r, stop):
    lg = r["log"]
    print(f"\n{'=' * 78}\n{tag}   CAGR {r['cagr']:6.2f}%   MDD {r['mdd']:7.2f}%")
    print(f"{'=' * 78}")
    if lg.empty:
        print("No closed trades")
        return
    print(f"Closed trades {len(lg)}   Gross price win rate {(lg['수익률'] > 0).mean() * 100:.1f}%")
    print("\nBy exit reason (unweighted gross price returns):")
    reason_labels = {"신호": "Signal", "손절": "Stop", "목표": "Target"}
    for why, g in lg.groupby("사유"):
        label = reason_labels.get(why, str(why))
        print(f"  {label:6s} {len(g):5d} trades  mean {g['수익률'].mean() * 100:7.2f}%  "
              f"worst {g['수익률'].min() * 100:7.2f}%  sum {g['수익률'].sum() * 100:8.1f} pp")

    if stop is not None:
        st = lg[lg["사유"] == "손절"]["수익률"] * 100
        if len(st):
            print(f"\nStop-fill return distribution (threshold {stop}%):")
            for q in (0, 5, 25, 50, 75, 100):
                print(f"  Percentile {q:3d}: {np.percentile(st, q):7.2f}%")
            worse = (st < stop - 0.01).mean() * 100
            print(f"  Filled below threshold: {worse:.1f}% (gap-down slippage)")

    lose = (lg["수익률"] < 0).astype(int).values
    best = cur = 0
    for x in lose:
        cur = cur + 1 if x else 0
        best = max(best, cur)
    print(f"\nLongest consecutive loss sequence: {best} trades")

    win = lg[(lg["청산"] >= r["peak"]) & (lg["청산"] <= r["trough"])]
    print(f"\nMDD window {r['peak'].date()} → {r['trough'].date()}  ({(r['trough'] - r['peak']).days} days)")
    print(f"  Closed trades {len(win)}, losses {(win['수익률'] < 0).sum()}, "
          f"unweighted gross return sum {win['수익률'].sum() * 100:.1f} pp")


def main():
    data, vix, regime, _ = load_all()
    s1 = STRATEGIES[0]
    require_symbols(data, s1.tickers)
    sub = {t: data[t] for t in s1.tickers}
    feats = {t: build_features(df) for t, df in sub.items()}
    print(f"USD stop diagnostics; per-side cost {COST:.2%}; warmup {WARMUP} sessions")

    for tag, tgt, stp in [
        ("S1 no target or stop", None, None),
        ("S1 target35 / stop-1.5", 35.0, -1.5),
        ("S1 target35 / stop-8", 35.0, -8.0),
    ]:
        show(tag, run_logged(s1, sub, feats, vix, tgt, stp), stp)

    print(f"\n{'=' * 78}\nIllustration: repeated -1.5% stops (approximate round-trip cost {COST * 2 * 100:.1f}%)\n{'=' * 78}")
    per = 0.985 * (1 - COST) ** 2
    for n in (10, 20, 30, 50, 70, 100):
        print(f"  {n:3d} consecutive stops → cumulative {(per ** n - 1) * 100:6.1f}%")
    need = np.log(0.35) / np.log(per)
    print(f"\n  Consecutive stops to reach -65%: {need:.0f}")


if __name__ == "__main__":
    main()
