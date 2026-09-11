"""Counterfactual level stop with a frozen-equity escape instead of a count timer.

Original rules:
    A : min_count('({previous_total_assets}/max_value({previous_total_assets},{H_days}))*100', {N_days}, {thr}) = 0
    C : max_count('abs(rate_of_change_period({previous_total_assets},{1_days}))*100', {K_days}, {0}) = 0
    condition : (A or C) and <existing buy condition>

min_count counts strictly BELOW; max_count counts strictly ABOVE the threshold.
The original *100 ratio uses percent thresholds (90), while Python thr uses
decimals (0.90). C expresses exact flatness; Python uses a 1e-9 tolerance on
decimal changes. The high uses up to 41 equity points, and C checks K-1 changes,
not the K changes suggested by the original notation. This is not execution evidence.
"""

from __future__ import annotations

from analyze_drawdown import drawdown_series, equity_from, load, stats
from analyze_drawdown_lockout import max_streak


def sig_level_frozen(
    rows, ratio: list[float], thr: float, n: int, freeze_k: int, residual: float
) -> tuple[list[bool], list[float]]:
    """Evaluate (A or C) on simulated equity; the ratio argument is unused.

    Start from the first supplied asset value. A uses up to n prior ratios,
    each high including its own equity point plus up to 40 earlier points.
    Allow the first two rows; retain partial lookbacks without dropping rows.
    C starts at zero-based row K+1 and checks K prior points, excluding the
    current simulated equity. Blocked returns are multiplied by residual,
    so both conditions feed back from the resulting equity path.
    """
    assets = [rows[0].asset]
    sig: list[bool] = []
    rets: list[float] = []
    for i in range(len(rows)):
        # A: min_count({equity_ratio},{N_days},{thr}) = 0; use prior simulated ratios.
        if i < 2:
            a_ok = True
        else:
            look = assets[max(0, i - n) : i]
            hi_win = assets[max(0, i - 40) : i]
            cnt = 0
            for j, v in enumerate(look):
                idx = max(0, i - n) + j
                hi = max(assets[max(0, idx - 40) : idx + 1])
                if v / hi < thr:
                    cnt += 1
            a_ok = cnt == 0
            _ = hi_win
        # C: K prior equity points / K-1 changes, excluding current simulated equity.
        if i >= freeze_k + 1:
            recent = assets[i - freeze_k : i]
            frozen = all(abs(recent[j + 1] / recent[j] - 1) < 1e-9 for j in range(len(recent) - 1))
        else:
            frozen = False
        allowed = a_ok or frozen
        sig.append(allowed)
        r = rows[i].ret if allowed else rows[i].ret * residual
        rets.append(r)
        assets.append(assets[-1] * (1 + r))
    return sig, rets


def report(name: str, rows, sig, rets) -> None:
    stats(name, rows, rets)
    n, when = max_streak(sig, rows)
    print(
        f"{'':34}   lockout max {n:3d}d (from {when}), off {sum(1 for s in sig if not s):3d}d"
    )


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

    print("\n=== LEVEL stop + FROZEN escape (K=10) ===")
    best = None
    for thr in (0.90, 0.92, 0.95):
        for n in (5, 10, 15, 20):
            sig, rets = sig_level_frozen(rows, [], thr, n, 10, residual)
            report(f"thr={thr:.2f} N={n}", rows, sig, rets)
        print()

    print("\n=== detail: thr=0.90 N=15 ===")
    sig, rets = sig_level_frozen(rows, [], 0.90, 15, 10, residual)
    report("thr=0.90 N=15", rows, sig, rets)
    per_year(rows, rets)

    print("\n=== detail: thr=0.90 N=20 ===")
    sig, rets = sig_level_frozen(rows, [], 0.90, 20, 10, residual)
    report("thr=0.90 N=20", rows, sig, rets)
    per_year(rows, rets)

    print("\n=== detail: thr=0.92 N=5 (HISTORICAL COUNTERFACTUAL CANDIDATE) ===")
    sig, rets = sig_level_frozen(rows, [], 0.92, 5, 10, residual)
    report("thr=0.92 N=5", rows, sig, rets)
    per_year(rows, rets)
    hist: dict[int, int] = {}
    cur = 0
    for s in sig:
        if not s:
            cur += 1
        elif cur:
            hist[cur] = hist.get(cur, 0) + 1
            cur = 0
    print("    lockout histogram:", dict(sorted(hist.items())))
    _ = best


if __name__ == "__main__":
    main()
