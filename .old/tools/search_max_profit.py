"""Max-profit search. Fast O(n) simulation via monotonic deque rolling max.

Rule:
    A : min_count('({previous_total_assets}/max_value({previous_total_assets},{H_days}))*100', {N_days}, {thr}) = 0
    B : min_count('({previous_total_assets}/max_value({previous_total_assets},{H_days}))*100', {M_days}, {thr}) >= M
    condition : (A or B) and <existing buy condition>
M = 0 disables B.

min_count counts values strictly BELOW the threshold; equality is not a breach.
The original *100 expressions use percent thresholds (90); Python thr uses
decimal ratios (0.90). B requires M consecutive breaches, not M blocked days.
Only the filter scales supplied returns here; no buy orders are reconstructed.
Historical grid search is counterfactual research, not out-of-sample evidence.
"""

from __future__ import annotations

from collections import deque

from analyze_drawdown import cagr, drawdown_series, equity_from, load
from portfolio_history import mar

RESID = 0.35


def simulate(rows, high: int, thr: float, n: int, m: int):
    """Apply (A or B), then update simulated equity with the filtered return.

    Allowed: use the full daily return. Blocked: use (daily return * RESID).
    Next equity = (current equity * (1 + filtered return)).

    Keep the first two sessions allowed. A uses available prior observations;
    B needs a full M-session window. Today's breach enters tomorrow's count.
    The rolling high includes the current equity and up to H earlier values
    (H+1 values in this implementation, unlike an exact H-session window).
    """
    assets = [rows[0].asset]
    dq: deque[int] = deque()  # indices, decreasing asset value
    breach: list[int] = []
    sig: list[bool] = []
    rets: list[float] = []
    cnt_n = 0
    cnt_m = 0
    for i in range(len(rows)):
        # Rolling high: current equity plus up to H earlier values.
        while dq and assets[dq[-1]] <= assets[i]:
            dq.pop()
        dq.append(i)
        while dq[0] < i - high:
            dq.popleft()
        breach.append(1 if assets[i] / assets[dq[0]] < thr else 0)

        if i >= 2:
            a_ok = cnt_n == 0
            esc = m > 0 and i >= m and cnt_m >= m
            allowed = a_ok or esc
        else:
            allowed = True
        sig.append(allowed)
        r = rows[i].ret if allowed else rows[i].ret * RESID
        rets.append(r)
        assets.append(assets[-1] * (1 + r))

        # Add today's breach and drop the oldest from each count.
        # Tomorrow's decision uses these updated N- and M-session counts.
        cnt_n += breach[i]
        if i - n >= 0:
            cnt_n -= breach[i - n]
        if m > 0:
            cnt_m += breach[i]
            if i - m >= 0:
                cnt_m -= breach[i - m]
    return sig, rets


def lock_max(rows, sig):
    cur = 0
    best = (0, "")
    start = ""
    for i, s in enumerate(sig):
        if not s:
            if cur == 0:
                start = rows[i].date
            cur += 1
        else:
            if cur > best[0]:
                best = (cur, start)
            cur = 0
    if cur > best[0]:
        best = (cur, start)
    return best


def main() -> None:
    rows = load()
    base_e = equity_from([r.ret for r in rows])
    base_c = cagr(base_e, len(rows))
    base_d = min(drawdown_series(base_e))
    print(f"BASELINE  CAGR {base_c:.2%}  MDD {base_d:.2%}  MAR {mar(base_c, base_d):.2f}")

    res = []
    for high in (20, 30, 40, 60, 90, 120):
        for thr in (0.85, 0.87, 0.88, 0.89, 0.90, 0.91, 0.92, 0.93, 0.94, 0.95):
            for n in (3, 5, 8, 10, 15, 20, 25):
                for m in (0, 5, 10, 15, 20, 25, 30, 40, 50):
                    if m and m <= n:
                        continue
                    sig, rets = simulate(rows, high, thr, n, m)
                    e = equity_from(rets)
                    c = cagr(e, len(rows))
                    d = min(drawdown_series(e))
                    res.append((c, d, high, thr, n, m, sig))
    print(f"tested {len(res)} combos")

    print("\n=== TOP 15 by raw CAGR ===")
    print(f"{'CAGR':>8} {'MDD':>8} {'MAR':>5}   H  thr    N    M  {'maxlock':>8}")
    for c, d, h, t, n, m, sig in sorted(res, key=lambda r: -r[0])[:15]:
        lk = lock_max(rows, sig)
        print(f"{c:8.2%} {d:8.2%} {mar(c, d):5.2f} {h:3d} {t:.2f} {n:4d} {m:4d} {lk[0]:6d}d {lk[1]}")

    print("\n=== Historical counterfactual CAGR by fixed MDD band ===")
    for lo, hi in ((-0.14, 0.0), (-0.16, -0.14), (-0.18, -0.16), (-0.20, -0.18)):
        pool = [r for r in res if lo <= r[1] < hi]
        if not pool:
            continue
        print(f"\n  MDD in [{lo:.0%}, {hi:.0%})")
        for c, d, h, t, n, m, sig in sorted(pool, key=lambda r: -r[0])[:5]:
            lk = lock_max(rows, sig)
            print(
                f"  {c:8.2%} {d:8.2%} {mar(c, d):5.2f} {h:3d} {t:.2f} {n:4d} {m:4d} {lk[0]:6d}d {lk[1]}"
            )


if __name__ == "__main__":
    main()
