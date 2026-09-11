"""Analyze supplied history using counterfactual overlays, not actual executions.

Equity-curve rules use {previous_total_assets} from supplied closing equity.
Filters use prior sessions only; a True signal leaves the return unscaled.
"""

from __future__ import annotations

import statistics
from pathlib import Path

from portfolio_history import RESEARCH_NOTICE, Row, benchmark_history, read_history


def load(path: str | Path | None = None) -> list[Row]:
    """Read explicit/configured CSV or a labeled gross benchmark buy-and-hold history."""
    from market_config import CONFIG

    source = path if path is not None else CONFIG.history_csv
    if source is not None:
        rows = read_history(source, start=CONFIG.start, end=CONFIG.end)
        print(f"Supplied portfolio history: {source}; returns/costs as recorded, no currency conversion.")
    else:
        rows = benchmark_history()
        print(f"{CONFIG.benchmark} buy-and-hold reference: adjusted Close, gross of costs; "
              "first row is a zero-return anchor; no transaction counts are inferred.")
    print(RESEARCH_NOTICE)
    print("No additional warmup is dropped from portfolio history; each filter retains its original lookback.")
    return rows


def drawdown_series(equity: list[float]) -> list[float]:
    """drawdown = ({total_assets} / {highest_assets_so_far}) - 1.

    The peak includes the current value; no pre-history equity anchor is inserted.
    """
    if not equity:
        raise ValueError("Drawdown requires a non-empty equity history.")
    peak = equity[0]
    out = []
    for v in equity:
        peak = max(peak, v)
        out.append(v / peak - 1.0)
    return out


def equity_from(returns: list[float]) -> list[float]:
    """Compound from 1: {total_assets} = {previous_total_assets} * (1 + {daily_return}).

    Return the compounded values without the initial capital anchor.
    """
    eq = [1.0]
    for r in returns:
        eq.append(eq[-1] * (1.0 + r))
    return eq[1:]


def cagr(equity: list[float], n_days: int) -> float:
    """CAGR = ({final_equity} ** (252 / {n_days})) - 1; initial capital is 1."""
    if not equity or n_days <= 0:
        raise ValueError("CAGR requires a non-empty equity history and positive session count.")
    return equity[-1] ** (252.0 / n_days) - 1.0


def stats(name: str, rows: list[Row], returns: list[float]) -> dict:
    """MDD = min(DD); vol = pstdev(returns) * sqrt(252); MAR = CAGR / (-MDD).

    MAR is NaN when MDD = 0. The nonzero-return share counts nonzero daily
    returns, not observed holdings/exposure. All rows enter these metrics.
    """
    if not rows or len(rows) != len(returns):
        raise ValueError("Statistics require non-empty, equally sized rows and returns.")
    eq = equity_from(returns)
    dd = drawdown_series(eq)
    mdd = min(dd)
    i_trough = dd.index(mdd)
    vol = statistics.pstdev(returns) * (252**0.5)
    c = cagr(eq, len(returns))
    exposure = sum(1 for r in returns if r != 0.0) / len(returns)
    print(
        f"{name:<34} CAGR {c:7.2%}  MDD {mdd:7.2%} @{rows[i_trough].date}"
        f"  vol {vol:6.2%}  MAR {c / -mdd if mdd else float('nan'):5.2f}  nonzero-return {exposure:5.1%}"
    )
    return {"mdd": mdd, "cagr": c, "dd": dd}


def worst_windows(rows: list[Row], win: int, top: int = 8) -> None:
    """Rank ({total_assets} / previous_value({total_assets},{win_days})) - 1.

    Rank ascending, using only complete windows of win return intervals.
    """
    eq = [r.asset for r in rows]
    res = []
    for i in range(win, len(eq)):
        res.append((eq[i] / eq[i - win] - 1.0, rows[i - win].date, rows[i].date))
    res.sort()
    print(f"\n-- worst {win}-day windows --")
    for r, d0, d1 in res[:top]:
        print(f"   {d0} -> {d1} : {r:7.2%}")


def drawdown_episodes(rows: list[Row], threshold: float = -0.08) -> None:
    """Report drawdown runs whose deepest drawdown is <= threshold.

    A run ends at recovery to the peak, or at the end of the history.
    """
    eq = [r.asset for r in rows]
    dd = drawdown_series(eq)
    print(f"\n-- drawdown episodes deeper than {threshold:.0%} --")
    peak_i = 0
    i = 0
    while i < len(dd):
        if dd[i] == 0.0:
            peak_i = i
            i += 1
            continue
        j = i
        while j < len(dd) and dd[j] < 0.0:
            j += 1
        seg = dd[i:j]
        trough = min(seg)
        if trough <= threshold:
            t_i = i + seg.index(trough)
            print(
                f"   peak {rows[peak_i].date} -> trough {rows[t_i].date} "
                f"({t_i - peak_i:3d}d, {trough:7.2%}) -> recover "
                f"{rows[j].date if j < len(dd) else 'n/a':>8} ({j - t_i:3d}d)"
            )
        i = j


# ---------------------------------------------------------------- filters
def apply_filter(rows: list[Row], signal: list[bool], residual: float = 0.0) -> list[float]:
    """Counterfactual: {overlay_return} = {daily_return} * {return_multiplier}.

    The multiplier is 1 when signal is True, otherwise residual (not holdings).
    Supplied-equity signals do not feed back from these scaled returns.
    """
    if len(rows) != len(signal):
        raise ValueError("Signal length must match portfolio history length.")
    return [r.ret if s else r.ret * residual for r, s in zip(rows, signal)]


def sig_ma(rows: list[Row], n: int) -> list[bool]:
    """{previous_total_assets} > moving_average({previous_total_assets},{n_days})

    Evaluate on prior-session equity; allow and retain the first n warmup rows.
    """
    a = [r.asset for r in rows]
    out = []
    for i in range(len(a)):
        if i < n:
            out.append(True)
            continue
        prev = a[i - 1]
        ma = sum(a[i - n : i]) / n
        out.append(prev > ma)
    return out


def sig_dd(rows: list[Row], n: int, tol: float) -> list[bool]:
    """{previous_total_assets} / max_value({previous_total_assets},{n_days}) >= 1-tol

    The ratio and tol are decimals. Equality allows risk; allow and retain
    the first n rows, then use the n equity values ending with yesterday.
    """
    a = [r.asset for r in rows]
    out = []
    for i in range(len(a)):
        if i < n:
            out.append(True)
            continue
        prev = a[i - 1]
        hi = max(a[i - n : i])
        out.append(prev / hi >= 1.0 - tol)
    return out


def sig_lossstreak(rows: list[Row], n: int, k: int) -> list[bool]:
    """min_count({portfolio_daily_return},{n_days},{0}) < k

    min_count counts strictly BELOW zero in the prior n sessions. Losses need
    not be consecutive; zero is not a loss. Allow and retain the first n rows.
    """
    out = []
    for i in range(len(rows)):
        if i < n:
            out.append(True)
            continue
        window = [rows[j].ret for j in range(i - n, i)]
        out.append(sum(1 for r in window if r < 0) < k)
    return out


def sig_vol(rows: list[Row], n: int, cap: float) -> list[bool]:
    """stddev({portfolio_daily_return},{n_days}) < cap

    Python uses population SD of prior decimal returns, not annualized.
    Equality blocks risk; allow and retain the first n warmup rows.
    """
    out = []
    for i in range(len(rows)):
        if i < n:
            out.append(True)
            continue
        window = [rows[j].ret for j in range(i - n, i)]
        out.append(statistics.pstdev(window) < cap)
    return out


def combine(*sigs: list[bool]) -> list[bool]:
    """Allow risk only when every signal is True; zip uses the shortest length."""
    return [all(v) for v in zip(*sigs)]


def main() -> None:
    rows = load()
    print(f"rows={len(rows)}  {rows[0].date} .. {rows[-1].date}")
    base = [r.ret for r in rows]
    stats("BASELINE", rows, base)
    drawdown_episodes(rows)
    worst_windows(rows, 5)
    worst_windows(rows, 10)

    # exposure diagnostics
    inv = [1 - r.cash / r.asset for r in rows]
    print(f"\navg overnight invested ratio = {sum(inv) / len(inv):.1%}")
    print(f"days fully in cash overnight = {sum(1 for r in rows if r.held == 0)}/{len(rows)}")

    for residual in (0.0, 0.35):
        print(f"\n================ residual exposure when risk-off = {residual:.0%}")
        for n in (5, 10, 20, 40, 60):
            stats(f"MA{n} equity filter", rows, apply_filter(rows, sig_ma(rows, n), residual))
        for n, tol in ((10, 0.03), (20, 0.05), (20, 0.08), (40, 0.10), (60, 0.12)):
            stats(
                f"DD stop {n}d/{tol:.0%}",
                rows,
                apply_filter(rows, sig_dd(rows, n, tol), residual),
            )
        for n, k in ((5, 3), (5, 4), (10, 6), (10, 7)):
            stats(
                f"loss-streak {k}/{n}d",
                rows,
                apply_filter(rows, sig_lossstreak(rows, n, k), residual),
            )
        for n, cap in ((10, 0.020), (20, 0.020), (20, 0.025)):
            stats(
                f"vol cap {n}d<{cap:.1%}",
                rows,
                apply_filter(rows, sig_vol(rows, n, cap), residual),
            )
        combos = {
            "MA20 AND DD20/5%": combine(sig_ma(rows, 20), sig_dd(rows, 20, 0.05)),
            "MA10 AND vol20<2.0%": combine(sig_ma(rows, 10), sig_vol(rows, 20, 0.020)),
            "DD20/5% AND vol20<2.0%": combine(sig_dd(rows, 20, 0.05), sig_vol(rows, 20, 0.020)),
            "DD20/5% AND loss4/5d": combine(sig_dd(rows, 20, 0.05), sig_lossstreak(rows, 5, 4)),
        }
        for name, sig in combos.items():
            stats(name, rows, apply_filter(rows, sig, residual))


if __name__ == "__main__":
    main()
