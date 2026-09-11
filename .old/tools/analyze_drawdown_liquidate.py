"""Counterfactual liquidation scenarios, not actual sell executions.

Residuals 0.35 and zero are assumed return fractions, not observed holdings.
Zero residual freezes simulated equity and can activate the frozen escape.
No fill prices or incremental costs are modeled; lower MDD is not guaranteed.
Historical grid search is not out-of-sample evidence.
"""

from __future__ import annotations

from analyze_drawdown import drawdown_series, equity_from, load, stats
from analyze_drawdown_lockout import max_streak

HIGH = 40


def simulate(
    rows,
    thr: float,
    n: int,
    freeze_k: int | None,
    first_day_residual: float,
    hold_residual: float,
):
    """Path-dependent (A or C), using the frozen-stop rule notation:

    A : min_count('({previous_total_assets}/max_value({previous_total_assets},{H_days}))*100', {N_days}, {thr}) = 0
    C : max_count('abs(rate_of_change_period({previous_total_assets},{1_days}))*100', {K_days}, {0}) = 0

    min_count counts strictly below; max_count counts strictly above. Original
    *100 thresholds are percent (90), while Python thr is decimal (0.90).
    Start from the first supplied asset value; A uses prior simulated ratios
    with up to HIGH+1 points per high. Allow the first two rows; keep partial
    lookbacks. C starts at zero-based row K+1 and checks K changes through
    current simulated equity, using abs(decimal change) < 1e-9, not exact zero.

    first_day_residual scales the first blocked return; hold_residual scales
    subsequent blocked returns. Allowed returns are unscaled. These returns
    update simulated equity, not actual holdings or fills; zero freezes equity.
    freeze_k=None disables C.
    """
    assets = [rows[0].asset]
    sig: list[bool] = []
    rets: list[float] = []
    run = 0  # consecutive blocked days so far
    for i in range(len(rows)):
        if i < 2:
            a_ok = True
        else:
            lo = max(0, i - n)
            cnt = 0
            for idx in range(lo, i):
                hi = max(assets[max(0, idx - HIGH) : idx + 1])
                if assets[idx] / hi < thr:
                    cnt += 1
            a_ok = cnt == 0

        frozen = False
        if freeze_k is not None and i >= freeze_k + 1:
            recent = assets[i - freeze_k : i + 1]
            frozen = all(
                abs(recent[j + 1] / recent[j] - 1) < 1e-9 for j in range(len(recent) - 1)
            )

        allowed = a_ok or frozen
        sig.append(allowed)
        if allowed:
            run = 0
            r = rows[i].ret
        else:
            run += 1
            r = rows[i].ret * (first_day_residual if run == 1 else hold_residual)
        rets.append(r)
        assets.append(assets[-1] * (1 + r))
    return sig, rets


def report(name: str, rows, sig, rets) -> None:
    stats(name, rows, rets)
    n, when = max_streak(sig, rows)
    print(f"{'':34}   lockout max {n:3d}d (from {when}), off {sum(1 for s in sig if not s):3d}d")


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
    stats("BASELINE", rows, [r.ret for r in rows])

    print("\n=== HOLD-THROUGH (block buys only, residual 0.35) ===")
    for thr, n in ((0.92, 5), (0.90, 15)):
        sig, rets = simulate(rows, thr, n, 10, 0.35, 0.35)
        report(f"thr={thr:.2f} N={n} K=10", rows, sig, rets)

    print("\n=== FULL LIQUIDATION (sell all on stop) ===")
    for thr in (0.90, 0.92, 0.95):
        for n in (5, 10, 15, 20):
            sig, rets = simulate(rows, thr, n, 10, 0.35, 0.0)
            report(f"thr={thr:.2f} N={n} K=10", rows, sig, rets)
        print()

    print("\n=== FULL LIQUIDATION -- frozen escape length K ===")
    for k in (10, 15, 20, 25, None):
        for thr, n in ((0.92, 5), (0.90, 15)):
            sig, rets = simulate(rows, thr, n, k, 0.35, 0.0)
            report(f"thr={thr:.2f} N={n} K={k}", rows, sig, rets)
        print()

    print("\n=== FULL LIQUIDATION -- robustness grid around thr=0.90 (K=10) ===")
    print(f"{'':10}" + "".join(f"{n:>16d}" for n in (10, 15, 18, 20, 22, 25)))
    for thr in (0.87, 0.88, 0.89, 0.90, 0.91, 0.92):
        cells = []
        for n in (10, 15, 18, 20, 22, 25):
            sig, rets = simulate(rows, thr, n, 10, 0.35, 0.0)
            e = equity_from(rets)
            from analyze_drawdown import cagr as _cagr

            c = _cagr(e, len(rows))
            d = min(drawdown_series(e))
            cells.append(f"{c:6.1%}/{d:6.1%}")
        print(f"thr={thr:.2f}  " + "".join(f"{c:>16s}" for c in cells))

    for thr, n, k in ((0.90, 20, 10), (0.90, 22, 10), (0.92, 5, 20)):
        print(f"\n=== detail: FULL LIQ thr={thr:.2f} N={n} K={k} ===")
        sig, rets = simulate(rows, thr, n, k, 0.35, 0.0)
        report(f"thr={thr:.2f} N={n} K={k}", rows, sig, rets)
        per_year(rows, rets)
        hist: dict[int, int] = {}
        cur = 0
        for s in sig:
            if not s:
                cur += 1
            elif cur:
                hist[cur] = hist.get(cur, 0) + 1
                cur = 0
        if cur:
            hist[cur] = hist.get(cur, 0) + 1
        print("    lockout histogram:", dict(sorted(hist.items())))


if __name__ == "__main__":
    main()
