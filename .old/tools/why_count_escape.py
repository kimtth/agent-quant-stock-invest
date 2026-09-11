"""Why introduce min_count in a counterfactual equity-stop experiment?

The original plain level condition is:
    {previous_total_assets}/max_value({previous_total_assets},{40_days}) >= 0.90
Zero residual can freeze equity below the old peak; RESID=0.35 generally does
not. The n-session breach window can delay release beyond the high window.

Count-based alternatives, retaining the original ratio units (no *100):
    A : min_count('{previous_total_assets}/max_value({previous_total_assets},{H_days})', {N_days}, {thr}) = 0
    B : min_count('{previous_total_assets}/max_value({previous_total_assets},{H_days})', {M_days}, {thr}) >= M
min_count counts strictly BELOW a decimal threshold such as 0.90. B counts
breach states, not blocked days: all M prior ratios must breach. A alone is
equivalent to not(any(breach, N)); (A or B) adds the count-based escape.

Compare no escape, frozen equity, breach-count timer and rebound. These are
counterfactual return multipliers, not reconstructed overnight holdings.
"""

from __future__ import annotations

from analyze_drawdown import cagr, drawdown_series, equity_from, load, stats
from portfolio_history import mar

HIGH = 40
RESID = 0.35


def run(rows, thr: float, n: int, escape: str, param: int):
    """Allow (A or escape), with P_days = param:

    none    : False
    frozen  : max_count('abs(rate_of_change_period({previous_total_assets},{1_days}))*100', {P_days}, {0}) = 0
    timer   : min_count({equity_ratio},{P_days},{thr}) >= param
    rebound : ({previous_total_assets}/previous_value({previous_total_assets},{P_days}) - 1) >= 0.03

    max_count counts strictly ABOVE zero; Python approximates exact flatness
    with abs(decimal change) < 1e-9 over P changes through current simulated
    equity. Frozen/rebound checks start at zero-based row P+1. The rebound
    threshold 0.03 is decimal (+3%); its expression has no *100.

    Start equity at the first supplied asset value; allow the first two rows.
    Counts use prior simulated ratios with partial lookbacks and up to HIGH+1
    points per high. Blocked returns scale by RESID and feed back into equity.
    fired counts escape days on which A alone would not allow risk.
    """
    assets = [rows[0].asset]
    sig: list[bool] = []
    rets: list[float] = []
    fired = 0
    for i in range(len(rows)):
        if i < 2:
            allowed, esc = True, False
        else:
            cnt = 0
            for idx in range(max(0, i - n), i):
                hi = max(assets[max(0, idx - HIGH) : idx + 1])
                if assets[idx] / hi < thr:
                    cnt += 1
            a_ok = cnt == 0

            esc = False
            if escape == "frozen" and i >= param + 1:
                rec = assets[i - param : i + 1]
                esc = all(abs(rec[j + 1] / rec[j] - 1) < 1e-9 for j in range(len(rec) - 1))
            elif escape == "timer":
                # min_count({equity_ratio},{P_days},{thr}) >= param.
                # All param prior ratios must breach; this is not a blocked-day timer.
                c2 = 0
                for idx in range(max(0, i - param), i):
                    hi = max(assets[max(0, idx - HIGH) : idx + 1])
                    if assets[idx] / hi < thr:
                        c2 += 1
                esc = c2 >= param
            elif escape == "rebound" and i >= param + 1:
                esc = assets[i] / assets[i - param] - 1 >= 0.03
            allowed = a_ok or esc
            if esc and not a_ok:
                fired += 1
        sig.append(allowed)
        r = rows[i].ret if allowed else rows[i].ret * RESID
        rets.append(r)
        assets.append(assets[-1] * (1 + r))
    return sig, rets, fired


def lock_stats(rows, sig):
    hist: dict[int, int] = {}
    cur = 0
    start = ""
    worst = (0, "")
    for i, s in enumerate(sig):
        if not s:
            if cur == 0:
                start = rows[i].date
            cur += 1
        elif cur:
            hist[cur] = hist.get(cur, 0) + 1
            if cur > worst[0]:
                worst = (cur, start)
            cur = 0
    if cur:
        hist[cur] = hist.get(cur, 0) + 1
        if cur > worst[0]:
            worst = (cur, start)
    return hist, worst


def show(rows, label, thr, n, escape, param):
    sig, rets, fired = run(rows, thr, n, escape, param)
    e = equity_from(rets)
    hist, worst = lock_stats(rows, sig)
    print(
        f"{label:<28} CAGR {cagr(e, len(rows)):6.2%}  MDD {min(drawdown_series(e)):7.2%}  "
        f"MAR {mar(cagr(e, len(rows)), min(drawdown_series(e))):5.2f}  "
        f"off {sum(1 for s in sig if not s):4d}d  maxlock {worst[0]:3d}d ({worst[1]})  "
        f"escape fired {fired}d"
    )
    return hist


def main() -> None:
    rows = load()
    stats("BASELINE", rows, [r.ret for r in rows])

    print("\n=== 1. user's rule: not(any(A,5)), thr 0.90, NO escape ===")
    h = show(rows, "no escape", 0.90, 5, "none", 0)
    print("   lockout histogram:", dict(sorted(h.items())))

    print("\n=== 2. does the FROZEN escape ever fire while still holding? ===")
    for k in (5, 10, 15):
        show(rows, f"frozen K={k}", 0.90, 5, "frozen", k)

    print("\n=== 3. escapes that CAN fire while still holding ===")
    print("  -- timer: release after M consecutive breach days --")
    for m in (5, 10, 15, 20, 25, 30):
        show(rows, f"timer M={m}", 0.90, 5, "timer", m)
    print("  -- rebound: account +3% over the last M days --")
    for m in (3, 5, 10, 15):
        show(rows, f"rebound M={m}", 0.90, 5, "rebound", m)

    print("\n=== 4. shorter high window shortens the deadlock by itself ===")
    global HIGH
    for hw in (20, 30, 40, 60):
        HIGH = hw
        show(rows, f"H={hw}, no escape", 0.90, 5, "none", 0)
    HIGH = 40


if __name__ == "__main__":
    main()
