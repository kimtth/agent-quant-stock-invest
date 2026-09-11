"""Historical drawdown-overlay experiments on configured USD ETF strategies.

Original overlay notation, translated:
    baseline  current conditions + target/stop settings (not formula fields)
    trail     sell: decline_from_high_ratio({20_days}) >= X
    ulcer     buy: {downside_volatility} <= X (Ulcer Index)
    ma200     buy: disparity({200_days}) >= 100
    regime    buy: {DOW_index_close} >= moving_average({DOW_index_close},{200_days})
    pos2      setting: maximum holdings 3 -> 2 (more cash)

The current grid runs baseline, trail, regime and pos2, not ulcer/ma200 variants.
The regime now uses configured SPY/QQQ, not the original DOW label/KOSPI proxy.
Parameters are retained research settings, not US recommendations or verified
deployment equivalents.
"""

from __future__ import annotations

import pandas as pd

from backtest_etf_combos import STRATEGIES, build_features, backtest, load_all
from backtest_voltarget import require_symbols
from market_config import CONFIG

COST = CONFIG.cost
WARMUP = CONFIG.warmup

# Historical target/stop settings, not recommendations for the new market.
BEST = {
    "S1": (35.0, -1.5),
    "S2": (50.0, -15.0),
    "S3": (50.0, -15.0),
    "S4": (25.0, -10.0),
    "S5": (25.0, -10.0),
}


def trail_sell(x):
    return lambda row, v: row["dd20"] >= x


def main():
    data, vix, regime, _ = load_all()
    feats = {t: build_features(df) for t, df in data.items()}
    reg = regime.to_dict()

    variants = [
        ("baseline", {}),
        ("trail 20 sessions -8%", {"extra_sell": trail_sell(8)}),
        ("trail 20 sessions -12%", {"extra_sell": trail_sell(12)}),
        ("trail 20 sessions -15%", {"extra_sell": trail_sell(15)}),
        (f"regime {CONFIG.benchmark} 200MA", {"regime": reg}),
        ("regime + trail-8%", {"regime": reg, "extra_sell": trail_sell(8)}),
        ("regime + trail-12%", {"regime": reg, "extra_sell": trail_sell(12)}),
        ("max positions 2", {"max_pos": 2}),
        ("regime + positions 2", {"regime": reg, "max_pos": 2}),
        ("regime+trail12+positions2", {"regime": reg, "extra_sell": trail_sell(12), "max_pos": 2}),
    ]

    for s in STRATEGIES:
        require_symbols(data, s.tickers)
        sub = {t: data[t] for t in s.tickers}
        subf = {t: feats[t] for t in sub}
        tgt, stp = BEST[s.sid]
        print("=" * 86)
        print(f"{s.sid}  {s.name}   target/stop {tgt:+.0f}% / {stp:.1f}%")
        print(f"Per-side cost {COST:.2%}; warmup {WARMUP}; native strategy windows (no cross-window ranking)")
        print(f"{'Variant':<24}|{'CAGR':>8} |{'MDD':>9} |{'Sharpe':>7} |{'Trades':>6} |{'Win rate':>8}")
        print("-" * 86)
        base = None
        for label, kw in variants:
            r = backtest(s, sub, subf, vix, tgt, stp, **kw)
            if r is None:
                print(f"{label}: insufficient history")
                continue
            print(f"  Window: {r['start']} .. {r['end']}")
            if base is None:
                base = r
            dm = r["mdd"] - base["mdd"]
            dc = r["cagr"] - base["cagr"]
            print(
                f"{label:<24}|{r['cagr']:7.2f}% |{r['mdd']:8.2f}% |{r['sharpe']:7.2f} "
                f"|{r['trades']:6d} |{r['winrate']:6.1f}%"
                + ("" if label == "baseline" else f"   (MDD {dm:+.1f}%p, CAGR {dc:+.2f}%p)")
            )
        print()


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    main()
