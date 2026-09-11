"""Common-date descriptive evaluation of historical USD ETF experiments.

Use configured costs, warmup, actual histories and the selected SPY/QQQ
benchmark. The legacy date split is descriptive, not a US crash boundary.
Execution, cost and exposure definitions still differ across engines: this
harness is a research comparison, not a deployment-validation certificate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtest_etf_combos import STRATEGIES, backtest, build_features, load_all
from backtest_voltarget import require_symbols
from market_config import CONFIG

COST = CONFIG.cost
WARMUP = CONFIG.warmup
EVAL_END = pd.Timestamp(CONFIG.end) - pd.Timedelta(days=1)
CRASH_CUT = pd.Timestamp("2026-05-31")

NDX2, NDX = CONFIG.symbol("growth_2x"), CONFIG.symbol("growth")
SOX2 = CONFIG.symbol("semiconductor_2x")
K200, SPX = CONFIG.symbol("equity"), CONFIG.symbol("equity")
# Preserve the legacy USD alias for dollar exposure, not semiconductor ticker USD.
BOND, GOLD, USD = CONFIG.symbol("treasury"), CONFIG.symbol("gold"), CONFIG.symbol("dollar")
DEF = [BOND, GOLD, USD]


# ---------------------------------------------------------------- Shared metric definitions
def metrics(ret: pd.Series, start, end, expo: pd.Series | None = None) -> dict:
    r = ret.loc[start:end].dropna()
    if len(r) < 250:
        return {}
    e = (1 + r).cumprod()
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    dd = e / e.cummax() - 1
    m12 = e.pct_change(252).dropna()
    return {
        "cagr": (e.iloc[-1] ** (1 / yrs) - 1) * 100,
        "mdd": dd.min() * 100,
        "sharpe": r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0.0,
        "calmar": (e.iloc[-1] ** (1 / yrs) - 1) * 100 / abs(dd.min() * 100) if dd.min() < 0 else np.nan,
        "worst12": m12.min() * 100 if len(m12) else np.nan,
        "expo": expo.loc[start:end].mean() * 100 if expo is not None else 100.0,
        "from": e.loc[: dd.idxmin()].idxmax().date(),
        "to": dd.idxmin().date(),
    }


# ---------------------------------------------------------------- Candidate generators
def frame(data, tks):
    require_symbols(data, tks)
    if not tks:
        raise ValueError("At least one ETF is required")
    cal = pd.DatetimeIndex(sorted(set().union(*[set(data[t].index) for t in tks])))
    close = pd.DataFrame({t: data[t]["Close"] for t in tks}).reindex(cal).ffill()
    high = pd.DataFrame({t: data[t]["High"] for t in tks}).reindex(cal).ffill()
    first = max(data[t].index[0] for t in tks)
    last = min(data[t].index[-1] for t in tks)
    common = (cal >= first) & (cal <= last)
    return close[common], high[common]


def hold(data, tk):
    close, _ = frame(data, [tk])
    r = close[tk].pct_change().fillna(0.0)
    return r, pd.Series(1.0, index=r.index)


def trend_state(close, high, tk, ma, trail, entry_dd):
    c, h = close[tk], high[tk]
    above = (c >= c.rolling(ma).mean()).to_numpy()
    hh = h.rolling(20).max()
    dd = ((hh - c) / hh * 100).to_numpy()
    mo = (c / c.shift(60) - 1).to_numpy()
    on = np.zeros(len(c))
    st = 0
    for i in range(len(c)):
        if st and (not above[i] or dd[i] >= trail):
            st = 0
        elif not st and above[i] and dd[i] <= entry_dd and mo[i] > 0:
            st = 1
        on[i] = st
    return pd.Series(on, index=c.index)


def vol_trend(data, lo2, hi2, trail, ma=200, entry_dd=3.0):
    """Legacy V1/V2 with a defensive basket; not the cash-only CSV rules."""
    tks = sorted({NDX2, NDX, *DEF})
    close, high = frame(data, tks)
    ret = close.pct_change().fillna(0.0).clip(-0.5, 0.5)
    sd = close.pct_change().rolling(20).std() * 100  # stddev('{daily_price_return}',{20_days}): sample SD, percent.

    on2 = trend_state(close, high, NDX2, ma, trail, entry_dd).to_numpy()
    b2 = (sd[NDX2] <= lo2).to_numpy()
    b1 = ((sd[NDX2] > lo2) & (sd[NDX2] <= hi2)).to_numpy()

    w2 = pd.Series(on2 * b2, index=close.index).shift(1).fillna(0.0)
    w1 = pd.Series(on2 * b1, index=close.index).shift(1).fillna(0.0)
    cash = (1 - w2 - w1).clip(0, 1)
    r = w2 * ret[NDX2] + w1 * ret[NDX] + cash * ret[DEF].mean(axis=1)
    r -= (w2.diff().abs().fillna(0) + w1.diff().abs().fillna(0)) * COST
    return r, (w2 + w1)


def voltarget(data, tgt, trail=15.0, cap=2.0, ma=200, entry_dd=3.0):
    """Legacy continuous targeting, including its original residual-cash formula.

    The formula uses exposure rather than ETF capital weight for defense and can
    leave capital unallocated. Retained for reproducibility, not a corrected model.
    """
    tks = sorted({NDX2, NDX, *DEF})
    close, high = frame(data, tks)
    ret = close.pct_change().fillna(0.0).clip(-0.5, 0.5)
    rv = ret[NDX].rolling(20).std() * np.sqrt(252) * 100
    on = trend_state(close, high, NDX, ma, trail, entry_dd)
    w = (tgt / rv).clip(0, cap).fillna(0.0) * on
    w2 = (w / 2).shift(1).fillna(0.0)
    cash = (1 - w.shift(1).fillna(0.0)).clip(0, 1)
    r = w2 * ret[NDX2] + cash * ret[DEF].mean(axis=1)
    r -= w2.diff().abs().fillna(0) * COST
    return r, w.shift(1).fillna(0.0).clip(0, 1)


def csv_exact(data, tk, sd_buy, sd_sell, trail=15.0, ma=200, entry_dd=3.0, cash_yield=0.0):
    """Single-position historical CSV-rule experiment, idle cash yields zero by default.

        Original CSV conditions, translated:
            Buy: disparity(ma) >= 100 AND decline_from_high_ratio(20_days) <= entry_dd
                     AND rate_of_change_period(close,60_days) >= 0 AND stddev('{daily_price_return}',{20_days}) <= sd_buy
            Sell: disparity(ma) < 100 OR decline_from_high_ratio(20_days) >= trail OR stddev > sd_sell

        Here ma is a session count; sell-side stddev abbreviates the same 20-session
        daily-return sample SD (percent). These are research rules, not proof of
        identical GenPort fills, costs or execution timing.
    """
    close, high = frame(data, [tk])
    c, h = close[tk], high[tk]
    ret = c.pct_change().fillna(0.0).clip(-0.5, 0.5)
    above = (c >= c.rolling(ma).mean()).to_numpy()
    hh = h.rolling(20).max()
    dd = ((hh - c) / hh * 100).to_numpy()
    mo = (c / c.shift(60) - 1).to_numpy()
    sd = (c.pct_change().rolling(20).std() * 100).to_numpy()

    buy = above & (dd <= entry_dd) & (mo >= 0) & (sd <= sd_buy)
    sell = (~above) | (dd >= trail) | (sd > sd_sell)

    on = np.zeros(len(c))
    st = 0
    for i in range(len(c)):
        if st and sell[i]:
            st = 0
        elif not st and buy[i]:
            st = 1
        on[i] = st
    w = pd.Series(on, index=c.index).shift(1).fillna(0.0)
    r = w * ret + (1 - w) * (cash_yield / 252)
    r -= w.diff().abs().fillna(0) * COST
    return r, w


def s1_returns(data, vix, regime, target, stop):
    """Extract legacy S1 returns; exposure remains its full-run scalar average."""
    s1 = STRATEGIES[0]
    require_symbols(data, s1.tickers)
    sub = {t: data[t] for t in s1.tickers}
    feats = {t: build_features(df) for t, df in sub.items()}
    res = backtest(s1, sub, feats, vix, target, stop, regime=regime)
    if res is None:
        raise ValueError("S1 has insufficient evaluation history")
    eq = res["curve"].dropna()
    eq = eq[eq > 0]
    r = eq.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return r, pd.Series(res["exposure"] / 100.0, index=r.index)


# ---------------------------------------------------------------- Runner
def main():
    data, vix, regime, _ = load_all()

    cands: dict[str, tuple] = {}
    cands["[BM] SPY gross hold"] = hold(data, "SPY")
    cands["[BM] QQQ gross hold"] = hold(data, "QQQ")
    cands[f"[Hold] Growth 2x ({NDX2})"] = hold(data, NDX2)
    cands[f"[Hold] Equity role ({K200})"] = hold(data, K200)
    cands[f"[Hold] Growth role ({NDX})"] = hold(data, NDX)
    cands["V1 volatility trend aggressive"] = vol_trend(data, 3.2, 4.5, 15.0)
    cands["V2 volatility trend balanced"] = vol_trend(data, 2.2, 4.0, 15.0)
    cands["V1-CSV cash-only rules"] = csv_exact(data, NDX2, 3.2, 4.5)
    cands["V2-CSV cash-only rules"] = csv_exact(data, NDX2, 2.2, 4.0)
    cands["VT target15% (legacy cash)"] = voltarget(data, 15.0)
    cands["VT target20% (legacy cash)"] = voltarget(data, 20.0)
    cands["S1 legacy stop-1.5"] = s1_returns(data, vix, regime, 35.0, -1.5)
    cands["S1 legacy no stop"] = s1_returns(data, vix, regime, None, None)

    # The S1 engine has already removed its warmup. Other generators return
    # full history; apply warmup once before finding the common date window.
    starts = {}
    ends = []
    for nm, (r, _) in cands.items():
        idx = r.dropna().index
        offset = 0 if nm.startswith("S1 ") else WARMUP
        if len(idx) <= offset:
            raise ValueError(f"{nm}: insufficient history after warmup")
        starts[nm] = idx[offset]
        ends.append(idx[-1])
    ev_start = max(pd.Timestamp(CONFIG.start), *starts.values())
    ev_end = min(EVAL_END, *ends)
    if ev_start >= ev_end:
        raise ValueError("Candidates have no common evaluation window")

    # Do not silently compare different observations within nominal dates.
    dates = cands["[BM] SPY gross hold"][0].loc[ev_start:ev_end].dropna().index
    if len(dates) < 250:
        raise ValueError("Common evaluation requires at least 250 sessions")
    for nm, (r, ex) in cands.items():
        r, ex = r.reindex(dates), ex.reindex(dates)
        if r.isna().any() or ex.isna().any():
            raise ValueError(f"{nm}: missing values on the common evaluation calendar")
        cands[nm] = (r, ex)
    ev_start, ev_end = dates[0], dates[-1]
    benchmark_label = f"[BM] {CONFIG.benchmark} gross hold"

    print("=" * 100)
    print("Common-date USD research evaluation")
    print("=" * 100)
    print(f"  Evaluation: {ev_start.date()} .. {ev_end.date()} ({len(dates)} common sessions)")
    print(f"  Per-side cost: {COST:.2%}; warmup: {WARMUP} sessions; hold baselines: gross")
    print(f"  Descriptive screen: CAGR >= {CONFIG.benchmark} and signed MDD >= {CONFIG.benchmark}")
    print("  Not validation: execution/cost models differ; no deployment equivalence is claimed.")
    print("  Exposure means offensive capital for V1/CSV, clipped leverage for VT, and a full-run average for S1.")
    print("  VT retains the legacy residual-cash formula, which can leave capital unallocated.")
    print("  The historical split is descriptive only, not a US crash boundary.")
    print("  Native post-warmup starts:")
    for nm, s in starts.items():
        print(f"    {nm:36s} {s.date()} → common {ev_start.date()}")

    rows = []
    for nm, (r, ex) in cands.items():
        a = metrics(r, ev_start, ev_end, ex)
        b = metrics(r, ev_start, min(CRASH_CUT, ev_end), ex)
        if not a:
            raise ValueError(f"{nm}: insufficient common evaluation history")
        rows.append((nm, a, b))

    bm = next(a for nm, a, _ in rows if nm == benchmark_label)

    print("\n" + "=" * 100)
    print(f"{'Strategy':36s} {'CAGR':>7s} {'MDD':>8s} {'Sharpe':>7s} {'Calmar':>7s} "
          f"{'Worst12M':>8s} {'Expo%':>6s} {'Screen':>6s}")
    print("-" * 100)
    for nm, a, _ in sorted(rows, key=lambda x: -x[1]["cagr"]):
        ok = "Yes" if (a["cagr"] >= bm["cagr"] and a["mdd"] >= bm["mdd"]) else "No"
        print(f"{nm:36s} {a['cagr']:6.2f}% {a['mdd']:7.2f}% {a['sharpe']:7.2f} "
              f"{a['calmar']:7.3f} {a['worst12']:7.1f}% {a['expo']:5.1f}% {ok:>6s}")

    print(f"\nHistorical split: {ev_start.date()} .. {min(CRASH_CUT, ev_end).date()}")
    print(f"{'Strategy':36s} {'CAGR':>7s} {'MDD':>8s} {'Sharpe':>7s} {'Drawdown window':>26s}")
    print("-" * 100)
    for nm, _, b in rows:
        if not b:
            print(f"{nm:36s} Insufficient historical-split observations")
            continue
        print(f"{nm:36s} {b['cagr']:6.2f}% {b['mdd']:7.2f}% {b['sharpe']:7.2f} "
              f"{str(b['from']):>13s}~{str(b['to']):>12s}")

    strategy_rows = [(nm, a) for nm, a, _ in rows if not nm.startswith("[")]
    n_ok = sum(a["cagr"] >= bm["cagr"] and a["mdd"] >= bm["mdd"] for _, a in strategy_rows)
    print(f"\nStrategies meeting the descriptive screen: {n_ok} / {len(strategy_rows)}")

    print("\n" + "=" * 100)
    print("Start-date sensitivity (same observed window per comparison)")
    print("=" * 100)
    print(f"{'Start':>11s} {'V1 CAGR':>9s} {'V1 MDD':>9s} {'BM CAGR':>9s} "
          f"{'BM MDD':>9s} {'CAGR gap':>8s} {'MDD gap':>8s} {'Screen':>6s}")
    print("-" * 100)
    v1r, v1e = cands["V1-CSV cash-only rules"]
    bmr, _ = cands[benchmark_label]
    verdicts = []
    sensitivity_starts = [ev_start] + [pd.Timestamp(f"{y}-01-01") for y in range(ev_start.year + 1, ev_end.year + 1)]
    for st in sensitivity_starts:
        observed = dates[dates >= st]
        if not len(observed):
            continue
        st = observed[0]
        a = metrics(v1r, st, ev_end, v1e)
        b = metrics(bmr, st, ev_end)
        if not a or not b:
            continue
        win = a["cagr"] >= b["cagr"] and a["mdd"] >= b["mdd"]
        verdicts.append(win)
        print(f"{str(st.date()):>11s} {a['cagr']:8.2f}% {a['mdd']:8.2f}% {b['cagr']:8.2f}% "
              f"{b['mdd']:8.2f}% {a['cagr'] - b['cagr']:+7.2f}p {a['mdd'] - b['mdd']:+7.2f}p "
              f"{'Yes' if win else 'No':>6s}")
    print(f"\n  V1 meets the {CONFIG.benchmark} screen: {sum(verdicts)} / {len(verdicts)} starts")

    print("\n" + "=" * 100)
    print("Four-year segment CAGR (segments clipped to common evaluation dates)")
    print("=" * 100)
    segs = [(f"{y}-01-01", f"{y + 3}-12-31") for y in range(ev_start.year, ev_end.year + 1, 4)]
    hdr = "".join(f"{s[:4]}-{e[2:4]:>2s}".rjust(12) for s, e in segs)
    print(f"{'Strategy':36s}{hdr}")
    print("-" * 100)
    for nm, _, _ in sorted(rows, key=lambda x: -x[1]["cagr"]):
        r, ex = cands[nm]
        cells = ""
        for s, e in segs:
            m = metrics(r, max(pd.Timestamp(s), ev_start), min(pd.Timestamp(e), ev_end), ex)
            cells += (f"{m['cagr']:11.1f}%" if m else f"{'-':>12s}")
        print(f"{nm:36s}{cells}")


if __name__ == "__main__":
    main()
