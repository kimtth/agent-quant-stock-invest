"""Counterfactual buy-block-only scenario. Wide parameter search.

Blocked days assume residual return fraction 0.35; holdings are not reconstructed.
Counterfactual overlays only; historical grid search is not out-of-sample evidence.
Grid over: high window H, threshold thr, re-arm window N, frozen escape K.
"""

from __future__ import annotations

from analyze_drawdown import cagr, drawdown_series, equity_from, load, stats
from analyze_drawdown_lockout import max_streak
from portfolio_history import mar as mar_ratio


def simulate(rows, high: int, thr: float, n: int, freeze_k: int | None, residual: float):
    """Buy-block filter (A or C), using the original frozen-stop notation:

    A : min_count('({previous_total_assets}/max_value({previous_total_assets},{H_days}))*100', {N_days}, {thr}) = 0
    C : max_count('abs(rate_of_change_period({previous_total_assets},{1_days}))*100', {K_days}, {0}) = 0

    min_count counts strictly below; max_count counts strictly above. The
    original *100 threshold is percent (90); Python thr is decimal (0.90).
    Start from the first supplied asset value. A uses prior simulated ratios,
    with up to high+1 points per high. Allow the first two rows and keep partial
    lookbacks. C starts at zero-based row K+1, checking K changes through current
    simulated equity with abs(decimal change) < 1e-9, rather than exact zero.
    freeze_k=None disables C. Blocked returns are multiplied by residual and
    feed back into simulated equity; allowed returns are unscaled.
    """
    assets = [rows[0].asset]
    sig: list[bool] = []
    rets: list[float] = []
    for i in range(len(rows)):
        if i < 2:
            a_ok = True
        else:
            cnt = 0
            for idx in range(max(0, i - n), i):
                hi = max(assets[max(0, idx - high) : idx + 1])
                if assets[idx] / hi < thr:
                    cnt += 1
            a_ok = cnt == 0
        frozen = False
        if freeze_k is not None and i >= freeze_k + 1:
            rec = assets[i - freeze_k : i + 1]
            frozen = all(abs(rec[j + 1] / rec[j] - 1) < 1e-9 for j in range(len(rec) - 1))
        allowed = a_ok or frozen
        sig.append(allowed)
        r = rows[i].ret if allowed else rows[i].ret * residual
        rets.append(r)
        assets.append(assets[-1] * (1 + r))
    return sig, rets


def metrics(rows, rets):
    e = equity_from(rets)
    return cagr(e, len(rows)), min(drawdown_series(e))


def per_year(rows, rets) -> None:
    for y in sorted({r.date[:4] for r in rows}):
        idx = [i for i, r in enumerate(rows) if r.date[:4] == y]
        b = equity_from([rows[i].ret for i in idx])
        f = equity_from([rets[i] for i in idx])
        print(
            f"    {y}: {b[-1] - 1:8.2%} -> {f[-1] - 1:8.2%} | "
            f"DD {min(drawdown_series(b)):7.2%} -> {min(drawdown_series(f)):7.2%}"
        )


def main() -> None:
    rows = load()
    residual = 0.35
    stats("BASELINE", rows, [r.ret for r in rows])

    results = []
    for high in (20, 30, 40, 60, 90):
        for thr in (0.88, 0.90, 0.91, 0.92, 0.93, 0.94):
            for n in (3, 5, 8, 10, 15, 20, 25):
                sig, rets = simulate(rows, high, thr, n, 10, residual)
                c, d = metrics(rows, rets)
                lk, _ = max_streak(sig, rows)
                results.append((mar_ratio(c, d), c, d, high, thr, n, lk, sum(1 for s in sig if not s)))

    results.sort(key=lambda r: r[0] if r[0] == r[0] else float("-inf"), reverse=True)
    print("\n=== top 20 by MAR (CAGR / MDD) ===")
    print(f"{'MAR':>5} {'CAGR':>8} {'MDD':>8}  H  thr    N  {'lock':>5} {'off':>5}")
    for mar, c, d, high, thr, n, lk, off in results[:20]:
        print(f"{mar:5.2f} {c:8.2%} {d:8.2%} {high:2d} {thr:.2f} {n:4d} {lk:5d} {off:5d}")

    print("\n=== best MDD with CAGR >= 75% ===")
    ok = [r for r in results if r[1] >= 0.75]
    ok.sort(key=lambda r: r[2], reverse=True)
    for mar, c, d, high, thr, n, lk, off in ok[:12]:
        print(f"{mar:5.2f} {c:8.2%} {d:8.2%} {high:2d} {thr:.2f} {n:4d} {lk:5d} {off:5d}")

    print("\n=== H=40 stability map (CAGR/MDD) ===")
    print(f"{'':10}" + "".join(f"{n:>16d}" for n in (3, 5, 8, 10, 15, 20, 25)))
    for thr in (0.88, 0.90, 0.91, 0.92, 0.93, 0.94):
        cells = []
        for n in (3, 5, 8, 10, 15, 20, 25):
            _, rets = simulate(rows, 40, thr, n, 10, residual)
            c, d = metrics(rows, rets)
            cells.append(f"{c:6.1%}/{d:6.1%}")
        print(f"thr={thr:.2f}  " + "".join(f"{c:>16s}" for c in cells))

    print("\n=== H=20 stability map (CAGR/MDD) ===")
    print(f"{'':10}" + "".join(f"{n:>16d}" for n in (3, 5, 8, 10, 15, 20, 25)))
    for thr in (0.88, 0.90, 0.91, 0.92, 0.93, 0.94):
        cells = []
        for n in (3, 5, 8, 10, 15, 20, 25):
            _, rets = simulate(rows, 20, thr, n, 10, residual)
            c, d = metrics(rows, rets)
            cells.append(f"{c:6.1%}/{d:6.1%}")
        print(f"thr={thr:.2f}  " + "".join(f"{c:>16s}" for c in cells))

    print("\n=== neighbourhood-averaged MAR (robustness, H fixed) ===")
    print("  each cell = mean MAR of itself and its 4 thr/N neighbours")
    thrs = (0.88, 0.90, 0.91, 0.92, 0.93, 0.94)
    ns = (3, 5, 8, 10, 15, 20, 25)
    for high in (20, 30, 40):
        grid = {}
        for ti, thr in enumerate(thrs):
            for ni, n in enumerate(ns):
                _, rets = simulate(rows, high, thr, n, 10, residual)
                c, d = metrics(rows, rets)
                grid[(ti, ni)] = mar_ratio(c, d)
        best_r = None
        for ti, thr in enumerate(thrs):
            for ni, n in enumerate(ns):
                # Mean MAR of the cell and existing axial index-neighbours;
                # edge cells have fewer than 4 neighbours; spacing is not weighted.
                cells = [grid[(ti, ni)]]
                for dt, dn in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    k = (ti + dt, ni + dn)
                    if k in grid:
                        cells.append(grid[k])
                avg = sum(cells) / len(cells)
                if best_r is None or avg > best_r[0]:
                    best_r = (avg, thr, n)
        print(f"  H={high}: best robust cell thr={best_r[1]:.2f} N={best_r[2]} avgMAR={best_r[0]:.2f}")

    for high, thr, n in ((20, 0.91, 25), (40, 0.91, 5), (30, 0.90, 15), (40, 0.92, 5)):
        print(f"\n=== detail: H={high} thr={thr:.2f} N={n} K=10 ===")
        sig, rets = simulate(rows, high, thr, n, 10, residual)
        stats(f"H={high} thr={thr:.2f} N={n}", rows, rets)
        lk, when = max_streak(sig, rows)
        print(f"{'':34}   lockout max {lk}d (from {when}), off {sum(1 for s in sig if not s)}d")
        per_year(rows, rets)


if __name__ == "__main__":
    main()
