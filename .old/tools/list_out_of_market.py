"""List counterfactual risk-off episodes, not actual out-of-market executions."""

from __future__ import annotations

from analyze_drawdown import equity_from, load
from analyze_drawdown_liquidate import simulate


def episodes(rows, sig):
    out = []
    i = 0
    while i < len(sig):
        if sig[i]:
            i += 1
            continue
        j = i
        while j < len(sig) and not sig[j]:
            j += 1
        out.append((i, j - 1))
        i = j
    return out


def main() -> None:
    rows = load()
    sig, rets = simulate(rows, 0.90, 20, 10, 0.35, 0.0)
    base = equity_from([r.ret for r in rows])
    filt = equity_from(rets)

    eps = episodes(rows, sig)
    print(f"total episodes {len(eps)}, total days {sum(1 for s in sig if not s)}")
    print(
        f"{'#':>3} {'start':>10} {'end':>10} {'days':>5} "
        f"{'baseline over window':>21} {'saved':>8}"
    )
    saved_total = 0.0
    for k, (a, b) in enumerate(eps, 1):
        base_move = base[b] / base[a - 1] - 1 if a > 0 else base[b] - 1
        filt_move = filt[b] / filt[a - 1] - 1 if a > 0 else filt[b] - 1
        saved = filt_move - base_move
        saved_total += saved
        print(
            f"{k:>3} {rows[a].date:>10} {rows[b].date:>10} {b - a + 1:>5} "
            f"{base_move:>20.2%} {saved:>+8.2%}"
        )
    print(f"\nsum of counterfactual window differences (not additive portfolio profit): {saved_total:+.2%}")

    print("\nby year:")
    for y in sorted({r.date[:4] for r in rows}):
        d = sum(1 for i, r in enumerate(rows) if r.date[:4] == y and not sig[i])
        tot = sum(1 for r in rows if r.date[:4] == y)
        n = sum(1 for a, b in eps if rows[a].date[:4] == y)
        print(f"  {y}: {d:3d}/{tot:3d} days out ({d / tot:5.1%}), {n} episodes")


if __name__ == "__main__":
    main()
