"""Momentum v2 research with offensive and defensive USD ETF roles.

Historical ADM, VAA and 12-1 variants retain their ranking, rebalance, trend,
trailing and re-entry rules. Defensive ETFs replace idle cash when a signal
selects defense; they are not risk-free. No US performance claim is implied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from backtest_etf_combos import load_all
from backtest_voltarget import report_rows, require_symbols
from market_config import CONFIG

M1, M3, M6, M12 = 21, 63, 126, 252
WARMUP = CONFIG.warmup
COST = CONFIG.cost


# ---------------------------------------------------------------- Scores


def score_adm(r: dict[int, pd.Series]) -> pd.Series:
    """Accelerating Dual Momentum: mean of 1/3/6-month returns."""
    return (r[M1] + r[M3] + r[M6]) / 3


def score_vaa(r: dict[int, pd.Series]) -> pd.Series:
    """VAA/Keller 13612W: larger weights on recent returns."""
    return 12 * r[M1] + 4 * r[M3] + 2 * r[M6] + r[M12]


def score_12_1(r: dict[int, pd.Series]) -> pd.Series:
    """Historical 12-1 score: subtract the most recent month's return."""
    return r[M12] - r[M1]


SCORERS: dict[str, Callable] = {"adm": score_adm, "vaa": score_vaa, "12-1": score_12_1}


# ---------------------------------------------------------------- Strategy definitions


@dataclass
class Mom:
    name: str
    offense: list[str]
    defense: list[str]
    scorer: str = "vaa"
    top: int = 1
    # VAA: any negative offensive score selects defense; otherwise evaluate selected assets.
    canary: bool = True
    trail: float | None = None  # decline_from_high_ratio(20_days) >= trail -> defense (percent).
    ma_gate: int | None = None  # Held offensive close < moving_average(close,N_days) -> daily defense.
    re_entry: float | None = None  # Daily re-entry when offensive drawdown is small enough.
    weekly: bool = False  # Weekly rather than monthly rebalance.
    note: str = ""
    tickers: list[str] = field(init=False)

    def __post_init__(self):
        self.tickers = self.offense + self.defense


NDX2, SOX2, NDX, SPX, EU, K2, Q2, SOX = (
    CONFIG.symbol("growth_2x"),
    CONFIG.symbol("semiconductor_2x"),
    CONFIG.symbol("growth"),
    CONFIG.symbol("equity"),
    CONFIG.symbol("international"),
    CONFIG.symbol("equity_2x"),
    CONFIG.symbol("small_cap_2x"),
    CONFIG.symbol("semiconductor"),
)
BOND, GOLD = CONFIG.symbol("treasury"), CONFIG.symbol("gold")
# Keep the legacy USD alias for callers; semiconductor_2x owns ticker USD.
USD, KOSPI = CONFIG.symbol("dollar"), CONFIG.symbol("equity")

STRATS = [
    Mom("M1 ADM growth/equity 2x", [NDX2, K2], [BOND, GOLD], "adm", 1, False,
        note="ADM ranking with leveraged equity roles"),
    Mom("M2 VAA global unleveraged", [NDX, SPX, EU, KOSPI], [BOND, GOLD, USD], "vaa", 1, True,
        note="VAA canary; equity roles may share a ticker"),
    Mom("M3 VAA leveraged", [NDX2, SOX2, NDX, K2], [BOND, GOLD, USD], "vaa", 1, True,
        note="Leveraged offensive assets"),
    Mom("M4 VAA leveraged top2", [NDX2, SOX2, NDX, SPX, K2, Q2], [BOND, GOLD, USD], "vaa", 2, True,
        note="Two offensive positions"),
    Mom("M5 12-1 momentum top2", [NDX2, SOX2, NDX, SPX, EU, K2, Q2], [BOND, GOLD, USD], "12-1", 2, False,
        note="12-1 ranking without canary"),
    Mom("M6 VAA leveraged + trail", [NDX2, SOX2, NDX, K2], [BOND, GOLD, USD], "vaa", 1, True,
        trail=15.0, note="M3 with 15% trail from the 20-session high"),
    Mom("M7 VAA top2 + trail", [NDX2, SOX2, NDX, SPX, K2, Q2], [BOND, GOLD, USD], "vaa", 2, True,
        trail=15.0, note="M4 with trailing exit"),
    Mom("M8 Semiconductor/growth top1", [SOX2, NDX2, SOX, NDX], [BOND, GOLD, USD], "vaa", 1, True,
        trail=20.0, note="Concentrated growth with trailing exit"),
    Mom("M9 ADM + daily 200MA", [NDX2, K2], [BOND, GOLD], "adm", 1, False,
        ma_gate=200, note="M1 with daily moving-average defense"),
    Mom("M10 VAA + daily 200MA", [NDX2, SOX2, NDX, K2], [BOND, GOLD, USD], "vaa", 1, True,
        ma_gate=200, note="M3 with daily 200MA gate"),
    Mom("M11 VAA + daily 100MA", [NDX2, SOX2, NDX, K2], [BOND, GOLD, USD], "vaa", 1, True,
        ma_gate=100, note="Faster moving-average gate"),
    Mom("M12 ADM + 200MA weekly", [NDX2, K2], [BOND, GOLD], "adm", 1, False,
        ma_gate=200, weekly=True, note="Weekly M9 rebalance"),
    Mom("M13 ADM top2 + 200MA", [NDX2, SOX2, NDX, K2, Q2], [BOND, GOLD, USD], "adm", 2, False,
        ma_gate=200, note="Two positions with a daily gate"),
    Mom("M14 Growth/equity + 200MA", [NDX, SPX, K2], [BOND, GOLD, USD], "adm", 1, False,
        ma_gate=200, note="Mixed 1x/2x universe with a daily gate"),
    Mom("M15 Growth 2x + 200MA", [NDX2], [BOND, GOLD], "adm", 1, False,
        ma_gate=200, note="Single offensive asset with defensive rotation"),
    Mom("T1 Growth top1 trail10%", [NDX2, SOX2, NDX, SPX], [BOND, GOLD, USD], "adm", 1, False,
        trail=10.0, ma_gate=200, note="10% trail from the 20-session high"),
    Mom("T2 Growth top1 trail8%", [NDX2, SOX2, NDX, SPX], [BOND, GOLD, USD], "adm", 1, False,
        trail=8.0, ma_gate=200, note="Tighter T1 trail"),
    Mom("T3 Broad top1 trail8%", [NDX2, SOX2, NDX, SPX, K2, Q2], [BOND, GOLD, USD], "adm", 1, False,
        trail=8.0, ma_gate=200, note="Includes broad and small-cap 2x equity"),
    Mom("T4 Growth top2 trail10%", [NDX2, SOX2, NDX, SPX, SOX], [BOND, GOLD, USD], "adm", 2, False,
        trail=10.0, ma_gate=200, note="Diversified T1"),
    Mom("T5 Growth 2x trail10%", [NDX2], [BOND, GOLD, USD], "adm", 1, False,
        trail=10.0, ma_gate=200, note="Single offensive asset with trailing exit"),
    Mom("T6 Growth 1x trail10%", [NDX, SPX], [BOND, GOLD, USD], "adm", 1, False,
        trail=10.0, ma_gate=200, note="Unleveraged baseline"),
    Mom("D1 Growth 2x daily trend", [NDX2], [BOND, GOLD, USD], "adm", 1, False,
        trail=10.0, ma_gate=200, re_entry=3.0, note="T5 with daily re-entry within 3% of high"),
    Mom("D2 Growth 2x entry5%", [NDX2], [BOND, GOLD, USD], "adm", 1, False,
        trail=10.0, ma_gate=200, re_entry=5.0, note="Looser D1 re-entry"),
    Mom("D3 Growth 2x trail12%", [NDX2], [BOND, GOLD, USD], "adm", 1, False,
        trail=12.0, ma_gate=200, re_entry=3.0, note="Wider D1 trail"),
    Mom("D4 Growth 2x trail15%", [NDX2], [BOND, GOLD, USD], "adm", 1, False,
        trail=15.0, ma_gate=200, re_entry=3.0, note="Widest D1 trail"),
    Mom("D5 Growth/semiconductor 2x daily", [NDX2, SOX2], [BOND, GOLD, USD], "adm", 1, False,
        trail=10.0, ma_gate=200, re_entry=3.0, note="Top momentum asset of two"),
    Mom("D6 Three offensive ETFs daily", [NDX2, SOX2, SPX], [BOND, GOLD, USD], "adm", 1, False,
        trail=10.0, ma_gate=200, re_entry=3.0, note="Growth 2x, semiconductor 2x or broad equity"),
    Mom("D7 Broad universe daily", [NDX2, SOX2, K2, Q2, NDX, SPX], [BOND, GOLD, USD], "adm", 1, False,
        trail=10.0, ma_gate=200, re_entry=3.0, note="Full offensive universe"),
    Mom("D8 Growth 2x 100MA daily", [NDX2], [BOND, GOLD, USD], "adm", 1, False,
        trail=10.0, ma_gate=100, re_entry=3.0, note="Faster 100MA gate"),
    Mom("D9 Growth 2x 60MA daily", [NDX2], [BOND, GOLD, USD], "adm", 1, False,
        trail=10.0, ma_gate=60, re_entry=3.0, note="60MA gate"),
    Mom("D10 Growth 1x daily", [NDX], [BOND, GOLD, USD], "adm", 1, False,
        trail=10.0, ma_gate=200, re_entry=3.0, note="Unleveraged daily baseline"),
]


# ---------------------------------------------------------------- Engine


def month_end_signals(cal: list[pd.Timestamp], weekly: bool = False) -> list[pd.Timestamp]:
    s = pd.Series(cal, index=pd.DatetimeIndex(cal))
    key = [s.index.year, s.index.isocalendar().week] if weekly else [s.index.year, s.index.month]
    return list(s.groupby(key).last())


def run(st: Mom, data: dict[str, pd.DataFrame]) -> dict | None:
    require_symbols(data, st.tickers)
    tk = list(dict.fromkeys(st.tickers))
    off = list(dict.fromkeys(st.offense))
    dfn = list(dict.fromkeys(st.defense))
    if not off or not dfn:
        return None

    cal = sorted(set().union(*[set(data[t].index) for t in tk]))
    close = pd.DataFrame({t: data[t]["Close"] for t in tk}).reindex(cal).ffill()
    open_ = pd.DataFrame({t: data[t]["Open"] for t in tk}).reindex(cal).ffill()
    high = pd.DataFrame({t: data[t]["High"] for t in tk}).reindex(cal).ffill()

    rets = {n: close / close.shift(n) - 1 for n in (M1, M3, M6, M12)}
    sc = SCORERS[st.scorer]({n: rets[n] for n in rets})
    dd20 = (high.rolling(20).max() - close) / high.rolling(20).max() * 100
    above = close >= close.rolling(st.ma_gate).mean() if st.ma_gate else None

    first = max(data[t].index[0] for t in tk)
    last = min(data[t].index[-1] for t in tk)
    cal = [d for d in cal if first <= d <= last]
    start_i = WARMUP
    if len(cal) <= start_i + 250:
        return None
    reb = set(month_end_signals(cal[start_i:], st.weekly))

    cash, shares = 1.0, {}
    pend: list[str] | None = None
    curve, switches, expo_off = [], 0, []
    log: list[tuple] = []

    for i, day in enumerate(cal):
        # --- Fill prior-session signals at the open ---
        if pend is not None:
            for t, s in shares.items():
                cash += s * open_.at[day, t] * (1 - COST)
            shares = {}
            if pend:
                w = 1.0 / len(pend)
                for t in pend:
                    px = open_.at[day, t]
                    if px > 0:
                        shares[t] = cash * w / px * (1 - COST)
                cash = 0.0
            pend = None

        eq = cash + sum(s * close.at[day, t] for t, s in shares.items())
        curve.append((day, eq))
        expo_off.append(1.0 if any(t in off for t in shares) else 0.0)
        log.append((day, "+".join(sorted(shares)) or "CASH"))

        if i < start_i:
            continue

        held_off = [t for t in shares if t in off]

        # --- Daily defense trigger: moving-average breach or trailing exit ---
        bail = False
        if held_off:
            if above is not None:
                bail = any(not bool(above.at[day, t]) for t in held_off)
            if st.trail is not None and max(dd20.at[day, t] for t in held_off) >= st.trail:
                bail = True
        if bail:
            d_sc = sc.loc[day, dfn].dropna()
            pend = [d_sc.idxmax()] if not d_sc.empty else []
            switches += 1
            continue

        # --- Daily re-entry: offense is above trend and near its recent high ---
        if st.re_entry is not None and not held_off:
            cand = [
                t
                for t in off
                if (above is None or bool(above.at[day, t]))
                and dd20.at[day, t] <= st.re_entry
                and sc.at[day, t] > 0
            ]
            if cand:
                pend = sorted(cand, key=lambda t: -sc.at[day, t])[: st.top]
                switches += 1
                continue

        if day not in reb:
            continue

        o_sc = sc.loc[day, off].dropna()
        d_sc = sc.loc[day, dfn].dropna()
        if o_sc.empty or d_sc.empty:
            continue

        # Exclude assets below the configured moving-average gate.
        if above is not None:
            o_sc = o_sc[[t for t in o_sc.index if bool(above.at[day, t])]]

        risk_off = o_sc.empty or ((sc.loc[day, off].dropna() < 0).any() if st.canary else False)
        if risk_off:
            target = [d_sc.idxmax()]
        else:
            picks = list(o_sc.sort_values(ascending=False).head(st.top).index)
            if not st.canary:
                picks = [p for p in picks if o_sc[p] > 0]
            if not picks:
                picks = [d_sc.idxmax()]
            elif len(picks) < st.top:
                picks.append(d_sc.idxmax())
            target = picks

        if set(target) != set(shares):
            pend = target
            switches += 1

    e = pd.Series(dict(curve)).sort_index().dropna()
    e = e[e > 0]
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    dr = e.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    ddc = e / e.cummax() - 1
    trough = ddc.idxmin()
    peak = e.loc[:trough].idxmax()
    pre = e.loc[: pd.Timestamp("2026-05-31")]
    pre_dd = (pre / pre.cummax() - 1).min() * 100 if len(pre) > 10 else float("nan")
    pre_yrs = (pre.index[-1] - pre.index[0]).days / 365.25 if len(pre) > 1 else 0
    pre_cagr = (pre.iloc[-1] ** (1 / pre_yrs) - 1) * 100 if pre_yrs > 1 else float("nan")
    return {
        "start": e.index[0].date(),
        "end": e.index[-1].date(),
        "years": yrs,
        "cagr": (e.iloc[-1] ** (1 / yrs) - 1) * 100,
        "mdd": ddc.min() * 100,
        "pre_cagr": pre_cagr,
        "pre_mdd": pre_dd,
        "mdd_from": peak.date(),
        "mdd_to": trough.date(),
        "sharpe": dr.mean() / dr.std() * np.sqrt(252) if dr.std() > 0 else 0.0,
        "switches": switches,
        "risk_on": float(np.mean(expo_off)) * 100,
        "mult": e.iloc[-1],
        "curve": e,
        "log": log,
    }


def bench(data, tk, since, until=None) -> tuple[float, float]:
    c = data[tk]["Close"].dropna()
    c = c[c.index >= since]
    if until is not None:
        c = c[c.index <= until]
    if len(c) < 2:
        return np.nan, np.nan
    yrs = (c.index[-1] - c.index[0]).days / 365.25
    return ((c.iloc[-1] / c.iloc[0]) ** (1 / yrs) - 1) * 100, (c / c.cummax() - 1).min() * 100


def main():
    data, _v, _r, _rep = load_all()

    rows = []
    for st in STRATS:
        r = run(st, data)
        if r:
            rows.append((st, r))

    if not rows:
        raise ValueError("No momentum strategy has sufficient common history")
    for st, r in rows:
        r["label"] = st.name
        r["note"] = (f"{st.note}; switches {r['switches']}; offensive holding time "
                     f"{r['risk_on']:.1f}%. Legacy metrics include the initial cash warmup.")
    report_rows([r for _, r in rows], data)

    print("\n[Holdings during each maximum drawdown]")
    for st, r in rows:
        lg = pd.Series(dict(r["log"]))
        seg = lg.loc[str(r["mdd_from"]) : str(r["mdd_to"])]
        held = ", ".join(f"{k} {v} sessions" for k, v in seg.value_counts().head(3).items())
        print(f"  {st.name:<28} {r['mdd']:7.2f}%  {r['mdd_from']} → {r['mdd_to']}   [{held}]")


if __name__ == "__main__":
    main()
