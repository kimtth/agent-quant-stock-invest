"""Counterfactual count-based equity stop, not actual trade executions.

Original rule (no any/every needed):
    cnt = min_count('{previous_total_assets}/max_value({previous_total_assets},{H_days})', {N_days}, {thr})
    BUY allowed iff cnt == 0 (healthy) OR cnt >= N (all N ratios breached)

min_count counts values strictly BELOW the threshold. This original expression
has no *100: thr is a decimal ratio (0.90), as in Python. Ratios use supplied
history, not return-scaled equity; ratio_high returns 1 during its H-row warmup.
The historical grid is in-sample research, not out-of-sample evidence.
"""

from __future__ import annotations

from analyze_drawdown import Row, apply_filter, load, sig_vol, stats
from analyze_drawdown_lockout import max_streak, ratio_high


def sig_count(ratio: list[float], thr: float, n: int) -> list[bool]:
    """Allow when min_count({ratio},{n_days},{thr}) = 0 or >= n.

    Count strictly below thr, including the current ratio. The escape requires
    n consecutive breach ratios; a partial window cannot satisfy it. Arbitrary
    mixed breach/healthy windows can block longer than n-1 sessions.
    apply_filter scales blocked returns by residual without equity feedback.
    """
    out = []
    for i in range(len(ratio)):
        lo = max(0, i - n + 1)
        window = ratio[lo : i + 1]
        cnt = sum(1 for v in window if v < thr)
        out.append(cnt == 0 or cnt >= n)
    return out


def show(name: str, rows: list[Row], sig: list[bool], residual: float) -> None:
    stats(name, rows, apply_filter(rows, sig, residual))
    n, when = max_streak(sig, rows)
    off = sum(1 for s in sig if not s)
    print(f"{'':34}   -> longest lockout {n:3d}d (from {when}), total off {off}d")


def main() -> None:
    rows = load()
    for residual in (0.35, 0.0):
        print(f"\n########## residual exposure when blocked = {residual:.0%} ##########")
        for h, thr in ((40, 0.90), (40, 0.92), (60, 0.90)):
            for n in (5, 8, 10, 15):
                r = ratio_high(rows, h)
                show(f"cnt {h}d/{1 - thr:.0%} N={n}", rows, sig_count(r, thr, n), residual)
            print()

    # Candidate: min_count('{previous_total_assets}/max_value({previous_total_assets},{40_days})', {5_days}, {0.90}) = 0
    # OR min_count('{previous_total_assets}/max_value({previous_total_assets},{40_days})', {5_days}, {0.90}) >= 5.
    print("\n########## HISTORICAL CANDIDATE: 40d/-10%, N=5 (residual 35%) ##########")
    r = ratio_high(rows, 40)
    sig = sig_count(r, 0.90, 5)
    show("COUNTERFACTUAL CANDIDATE", rows, sig, 0.35)
    show("CANDIDATE [zero residual]", rows, sig, 0.0)
    sig2 = [a and b for a, b in zip(sig, sig_vol(rows, 20, 0.020))]
    show("  + vol20<2.0% (rejected)", rows, sig2, 0.35)

    # streak histogram
    hist: dict[int, int] = {}
    cur = 0
    for s in sig:
        if not s:
            cur += 1
        elif cur:
            hist[cur] = hist.get(cur, 0) + 1
            cur = 0
    print("\nlockout length histogram:", dict(sorted(hist.items())))

    # per-year
    from analyze_drawdown import drawdown_series, equity_from

    filt = apply_filter(rows, sig, 0.35)
    print("\nper-year baseline -> counterfactual candidate")
    for y in sorted({r_.date[:4] for r_ in rows}):
        idx = [i for i, r_ in enumerate(rows) if r_.date[:4] == y]
        b = equity_from([rows[i].ret for i in idx])
        f = equity_from([filt[i] for i in idx])
        off = sum(1 for i in idx if not sig[i])
        print(
            f"  {y}: ret {b[-1] - 1:8.2%} -> {f[-1] - 1:8.2%} | "
            f"maxDD {min(drawdown_series(b)):7.2%} -> {min(drawdown_series(f)):7.2%} | off {off:3d}d"
        )


if __name__ == "__main__":
    main()
