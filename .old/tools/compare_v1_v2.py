"""Compare two supplied histories on identical dates, then explore return overlays."""

from __future__ import annotations

from pathlib import Path

from analyze_drawdown import Row, drawdown_series, equity_from, stats
from analyze_drawdown_lockout import max_streak, ratio_high

from portfolio_history import RESEARCH_NOTICE, read_history


def load(path: Path) -> list[Row]:
    from market_config import CONFIG
    return read_history(path, start=CONFIG.start, end=CONFIG.end)


def buys(path: Path) -> dict[str, int]:
    from market_config import CONFIG
    rows = read_history(path, require_buys=True, start=CONFIG.start, end=CONFIG.end)
    return {row.date: row.buys for row in rows if row.buys is not None}


def comparison_histories() -> tuple[list[Row], list[Row]]:
    """Require two explicit buy-count histories with identical evaluation dates."""
    from market_config import CONFIG
    if CONFIG.history_csv is None or CONFIG.compare_csv is None:
        raise ValueError("Comparison requires history_csv and compare_csv in research config, both with buys columns")
    first, second = [read_history(path, require_buys=True, start=CONFIG.start, end=CONFIG.end)
                     for path in (CONFIG.history_csv, CONFIG.compare_csv)]
    if [r.date for r in first] != [r.date for r in second]:
        raise ValueError("Comparison histories must have identical dates; supply matching daily rows or adjust start/end")
    return first, second


def deep_episodes(rows: list[Row], thr: float = -0.08) -> list[tuple[str, str, float]]:
    dd = drawdown_series([r.asset for r in rows])
    out, i = [], 0
    peak = 0
    while i < len(dd):
        if dd[i] == 0.0:
            peak, i = i, i + 1
            continue
        j = i
        while j < len(dd) and dd[j] < 0:
            j += 1
        seg = dd[i:j]
        if min(seg) <= thr:
            out.append((rows[peak].date, rows[i + seg.index(min(seg))].date, min(seg)))
        i = j
    return out


def main() -> None:
    v1, v2 = comparison_histories()
    print(RESEARCH_NOTICE)
    print("Supplied histories retain recorded costs; no currency conversion or additional warmup.")
    print(f"v1 {len(v1)} rows {v1[0].date}..{v1[-1].date}")
    print(f"v2 {len(v2)} rows {v2[0].date}..{v2[-1].date}\n")

    stats("v1 BASELINE", v1, [r.ret for r in v1])
    stats("v2 SUPPLIED COMPARISON", v2, [r.ret for r in v2])

    b1 = {r.date: r.buys for r in v1 if r.buys is not None}
    b2 = {r.date: r.buys for r in v2 if r.buys is not None}
    common = sorted(set(b1) & set(b2))
    blocked = [d for d in common if b1[d] > 0 and b2[d] == 0]
    print(f"\ncommon days {len(common)}; days v1 bought but v2 did not: {len(blocked)}")

    # how long were the actual no-buy stretches in v2?
    nb = [b2[r.date] > 0 for r in v2]
    n, when = max_streak(nb, v2)
    print(f"v2 longest zero-buy stretch: {n}d from {when}; total zero-buy {sum(1 for x in nb if not x)}d")

    print("\n-- deep drawdowns --")
    for tag, rows in (("v1", v1), ("v2", v2)):
        for p, t, d in deep_episodes(rows):
            print(f"   {tag}: peak {p} -> trough {t} : {d:7.2%}")

    print("\n-- per-year --")
    years = sorted({r.date[:4] for r in v1})
    for y in years:
        i1 = [i for i, r in enumerate(v1) if r.date[:4] == y]
        i2 = [i for i, r in enumerate(v2) if r.date[:4] == y]
        e1, e2 = equity_from([v1[i].ret for i in i1]), equity_from([v2[i].ret for i in i2])
        print(
            f"  {y}: v1 {e1[-1] - 1:8.2%} / DD {min(drawdown_series(e1)):7.2%}   "
            f"v2 {e2[-1] - 1:8.2%} / DD {min(drawdown_series(e2)):7.2%}"
        )

    # ---- re-tune N on the v2 equity curve, and on v1 as the alpha source
    print("\n-- re-tune: N sweep simulated on v1 returns (residual 35%) --")
    from analyze_drawdown import apply_filter
    from analyze_drawdown_bounded import sig_count

    for h in (40, 60, 90):
        for thr in (0.90, 0.92):
            for n in (5, 10, 15, 20, 25, 30):
                r = ratio_high(v1, h)
                s = sig_count(r, thr, n)
                stats(f"H={h} thr={thr:.2f} N={n}", v1, apply_filter(v1, s, 0.35))
                ln, lw = max_streak(s, v1)
                print(f"{'':34}   lockout max {ln:3d}d, off {sum(1 for x in s if not x):3d}d")
            print()


if __name__ == "__main__":
    main()
