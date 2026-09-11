"""Third pass: fix the self-referential lockout of the level-based equity stop.

Problem: {previous_total_assets}/max_value({previous_total_assets},{40_days}) <= 0.90
is a STATE condition. If the filter makes equity flat, the ratio can stay below
0.90 until the old peak leaves the window. The post-breach hold can delay release
further; 40 is not a total lockout cap. These helpers use supplied prior equity,
not feedback from filtered returns. Ratios and thresholds here are decimals.

Fixes tested:
    1. EDGE trigger : (ratio <= 0.90) and (previous_value(ratio,{1_days}) > 0.90).
      Block K sessions including the crossing (a new crossing restarts the timer).
    2. SELF-HEALING : {previous_total_assets}/moving_average({previous_total_assets},{n_days}).
      Flat equity makes this ratio approach 1 as old observations leave the window.
    3. LEVEL + CAP : block only when (timer > 0) and (blocked_streak < cap).
      Force one allowed session once cap consecutive blocks have accumulated.
"""

from __future__ import annotations

from analyze_drawdown import Row, apply_filter, load, sig_ma, stats


def ratio_high(rows: list[Row], n: int) -> list[float]:
    """{previous_total_assets} / max_value({previous_total_assets},{n_days})

    Use n supplied equity values ending with yesterday. Return the neutral
    decimal ratio 1.0 during the first n rows.
    """
    a = [r.asset for r in rows]
    out = []
    for i in range(len(a)):
        if i < n:
            out.append(1.0)
        else:
            out.append(a[i - 1] / max(a[i - n : i]))
    return out


def ratio_ma(rows: list[Row], n: int) -> list[float]:
    """{previous_total_assets} / moving_average({previous_total_assets},{n_days})

    Use n supplied equity values ending with yesterday. Return the neutral
    decimal ratio 1.0 during the first n rows.
    """
    a = [r.asset for r in rows]
    out = []
    for i in range(len(a)):
        if i < n:
            out.append(1.0)
        else:
            out.append(a[i - 1] / (sum(a[i - n : i]) / n))
    return out


def sig_level(ratio: list[float], thr: float, hold: int) -> list[bool]:
    """Original shorthand: not(any(A, hold)) where A = ratio <= thr.

    Python blocks the breach session PLUS hold following sessions, not a
    hold-observation window. Repeated breaches reset the timer; hold=0 still
    blocks every breach session. True means risk is allowed.
    """
    out = []
    left = 0
    for v in ratio:
        if v <= thr:
            left = hold
            out.append(False)
        elif left > 0:
            left -= 1
            out.append(False)
        else:
            out.append(True)
    return out


def sig_edge(ratio: list[float], thr: float, hold: int) -> list[bool]:
    """A = (ratio <= thr) and (previous_value(ratio,{1_days}) > thr) -> not(any(A, hold)).

    Block hold sessions including the crossing; no crossing on the first row.
    hold=0 never blocks. A new crossing resets the timer, so consecutive lockout
    can exceed hold even though each isolated crossing blocks hold sessions.
    """
    out = []
    left = 0
    for i, v in enumerate(ratio):
        crossed = v <= thr and (i > 0 and ratio[i - 1] > thr)
        if crossed:
            left = hold
        if left > 0:
            left -= 1
            out.append(False)
        else:
            out.append(True)
    return out


def sig_level_capped(ratio: list[float], thr: float, hold: int, cap: int) -> list[bool]:
    """Level condition ratio <= thr, with forced re-entry after cap straight blocks.

    A breach resets the hold timer. Block while (timer > 0) and (streak < cap);
    otherwise allow one session and clear both counters. Positive hold/cap
    bound consecutive blocks at cap; hold=0 never blocks here.
    Unlike sig_level(), this timer includes the breach session in hold.
    """
    out = []
    left = 0
    streak = 0
    for v in ratio:
        blocked = v <= thr
        if blocked:
            left = hold
        if left > 0 and streak < cap:
            left -= 1
            streak += 1
            out.append(False)
        else:
            left = 0
            streak = 0
            out.append(True)
    return out


def max_streak(sig: list[bool], rows: list[Row]) -> tuple[int, str]:
    best, cur, start, best_start = 0, 0, "", ""
    for i, s in enumerate(sig):
        if not s:
            if cur == 0:
                start = rows[i].date
            cur += 1
            if cur > best:
                best, best_start = cur, start
        else:
            cur = 0
    return best, best_start


def show(name: str, rows: list[Row], sig: list[bool], residual: float) -> dict:
    n, when = max_streak(sig, rows)
    off = sum(1 for s in sig if not s)
    res = stats(name, rows, apply_filter(rows, sig, residual))
    print(f"{'':34}   -> longest lockout {n:3d}d (from {when}), total off {off}d")
    return res


def main() -> None:
    rows = load()
    r40 = ratio_high(rows, 40)
    r20 = ratio_high(rows, 20)

    for residual in (0.35, 0.0):
        print(f"\n########## residual exposure when blocked = {residual:.0%} ##########")

        print("\n-- CURRENT RULE (state/level based) --")
        show("LEVEL 40d/10% hold5", rows, sig_level(r40, 0.90, 5), residual)
        show("LEVEL 20d/5% hold3", rows, sig_level(r20, 0.95, 3), residual)

        print("\n-- FIX 1: EDGE trigger (bounded lockout) --")
        for hold in (5, 8, 10, 15, 20):
            show(f"EDGE 40d/10% block{hold}d", rows, sig_edge(r40, 0.90, hold), residual)
        for hold in (5, 10, 15):
            show(f"EDGE 20d/5% block{hold}d", rows, sig_edge(r20, 0.95, hold), residual)

        print("\n-- FIX 2: self-healing MA denominator --")
        for n in (20, 40, 60):
            show(f"MA{n} level", rows, sig_ma(rows, n), residual)
        for n, thr in ((40, 0.97), (40, 0.95), (60, 0.95)):
            show(f"MA{n} < {thr}", rows, sig_level(ratio_ma(rows, n), thr, 0), residual)

        print("\n-- FIX 3: level + hard re-entry cap --")
        for cap in (5, 10, 15, 20):
            show(f"LEVEL 40d/10% cap{cap}d", rows, sig_level_capped(r40, 0.90, 5, cap), residual)


if __name__ == "__main__":
    main()
