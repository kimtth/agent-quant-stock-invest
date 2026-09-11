"""Second pass: counterfactual hysteresis and graded return scaling.

Signals use supplied equity and returns, not feedback from scaled returns.
"""

from __future__ import annotations


from analyze_drawdown import (
    Row,
    apply_filter,
    drawdown_series,
    equity_from,
    load,
    sig_dd,
    sig_ma,
    sig_vol,
    stats,
)


def sig_shock(rows: list[Row], pct: float) -> list[bool]:
    """rate_of_change_period({previous_total_assets},{1_days}) > -pct

    Python uses the supplied prior daily return (decimal), not recomputed
    equity changes. Allow the first row; a loss equal to pct also blocks.
    """
    out = []
    for i in range(len(rows)):
        out.append(True if i == 0 else rows[i - 1].ret > -pct)
    return out


def hysteresis(signal: list[bool], hold: int) -> list[bool]:
    """Original shorthand: not(any(risk-off, hold)).

    Python blocks the breach session PLUS hold following sessions, rather
    than a hold-observation window; each new breach resets the timer.
    """
    out = []
    off_left = 0
    for s in signal:
        if not s:
            off_left = hold
            out.append(False)
        elif off_left > 0:
            off_left -= 1
            out.append(False)
        else:
            out.append(True)
    return out


def graded(rows: list[Row], levels: list[tuple[list[bool], float]], residual: float) -> list[float]:
    """Use the smallest failing level's multiplier, starting from 1, floored at residual.

    {overlay_return} = {daily_return} * {return_multiplier}; not actual holdings.
    """
    out = []
    for i, r in enumerate(rows):
        expo = 1.0
        for sig, e in levels:
            if not sig[i]:
                expo = min(expo, e)
        expo = max(expo, residual) if expo < residual else expo
        out.append(r.ret * expo)
    return out


def report(name: str, rows: list[Row], returns: list[float]) -> None:
    stats(name, rows, returns)


def main() -> None:
    rows = load()
    residual = 0.35
    print("== hysteresis on DD20/5% (block, then stay out N more days) ==")
    base_off = sig_dd(rows, 20, 0.05)
    for hold in (0, 2, 3, 5, 10):
        report(f"DD20/5% + hold {hold}d", rows, apply_filter(rows, hysteresis(base_off, hold), residual))

    print("\n== hysteresis on DD40/10% ==")
    b = sig_dd(rows, 40, 0.10)
    for hold in (0, 3, 5, 10, 15):
        report(f"DD40/10% + hold {hold}d", rows, apply_filter(rows, hysteresis(b, hold), residual))

    print("\n== one-day shock filter ==")
    for pct in (0.03, 0.04, 0.05):
        for hold in (0, 1, 2):
            report(
                f"shock <-{pct:.0%} + hold {hold}d",
                rows,
                apply_filter(rows, hysteresis(sig_shock(rows, pct), hold), residual),
            )

    print("\n== graded exposure ladder (soft de-risk) ==")
    # {previous_total_assets} / max_value({previous_total_assets},{20_days}); allow the first 20 rows.
    l1 = sig_dd(rows, 20, 0.03)   # Ratio < 0.97 -> multiplier 0.5.
    l2 = sig_dd(rows, 20, 0.07)   # Ratio < 0.93 -> 0, floored at residual=0.35.
    report("grade: -3%->50%, -7%->off", rows, graded(rows, [(l1, 0.5), (l2, 0.0)], residual))

    l1b = sig_dd(rows, 40, 0.05)
    l2b = sig_dd(rows, 40, 0.10)
    report("grade: 40d -5%->50%, -10%->off", rows, graded(rows, [(l1b, 0.5), (l2b, 0.0)], residual))

    print("\n== best-of combos ==")
    combos = {
        "DD40/10%(hold5) AND vol20<2.0%": [
            hysteresis(sig_dd(rows, 40, 0.10), 5),
            sig_vol(rows, 20, 0.020),
        ],
        "DD20/5%(hold3) AND vol20<2.0%": [
            hysteresis(sig_dd(rows, 20, 0.05), 3),
            sig_vol(rows, 20, 0.020),
        ],
        "DD40/10%(hold5) AND MA40": [
            hysteresis(sig_dd(rows, 40, 0.10), 5),
            sig_ma(rows, 40),
        ],
        "DD60/12%(hold5) AND vol20<2.2%": [
            hysteresis(sig_dd(rows, 60, 0.12), 5),
            sig_vol(rows, 20, 0.022),
        ],
    }
    for name, sigs in combos.items():
        merged = [all(v) for v in zip(*sigs)]
        report(name, rows, apply_filter(rows, merged, residual))
        report(name + "  [full liquidation]", rows, apply_filter(rows, merged, 0.0))

    # Candidate: DD40/10% with 5 extra off sessions AND
    # stddev({portfolio_daily_return},{20_days}) < 0.020 (population SD of decimal returns).
    # Each base signal keeps its own warmup.
    rec = [all(v) for v in zip(hysteresis(sig_dd(rows, 40, 0.10), 5), sig_vol(rows, 20, 0.020))]
    print("\n== per-year: baseline vs counterfactual candidate (residual 35%) ==")
    filt = apply_filter(rows, rec, residual)
    years = sorted({r.date[:4] for r in rows})
    for y in years:
        idx = [i for i, r in enumerate(rows) if r.date[:4] == y]
        b_eq = equity_from([rows[i].ret for i in idx])
        f_eq = equity_from([filt[i] for i in idx])
        b_dd = min(drawdown_series(b_eq))
        f_dd = min(drawdown_series(f_eq))
        off = sum(1 for i in idx if not rec[i])
        print(
            f"  {y}: ret {b_eq[-1] - 1:8.2%} -> {f_eq[-1] - 1:8.2%} | "
            f"maxDD {b_dd:7.2%} -> {f_dd:7.2%} | risk-off {off:3d}/{len(idx)}d"
        )


if __name__ == "__main__":
    main()
