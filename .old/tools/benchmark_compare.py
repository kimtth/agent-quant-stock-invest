"""Compare configured USD ETF strategies with actual SPY/QQQ on matched dates.

Hold baselines are gross of trading costs. Strategy execution models are not
identical to buy-and-hold; date matching alone is not evidence of superiority.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtest_etf_combos import STRATEGIES, backtest, build_features, load_all
from backtest_mdd_overlay import BEST, trail_sell
from backtest_voltarget import require_symbols
from market_config import CONFIG

START, END = CONFIG.start, CONFIG.end
COST, WARMUP = CONFIG.cost, CONFIG.warmup

# Historical overlay packages (None means no regime or extra sell overlay).
MDD_PKG = {
    "S1": {"extra_sell": trail_sell(8)},
    "S2": {"extra_sell": trail_sell(12)},
    "S3": None,
    "S4": {},
    "S5": {},
}

BENCH = {
    "SPY gross hold (USD)": ("SPY", False),
    "QQQ gross hold (USD)": ("QQQ", False),
}


def stats(c: pd.Series) -> tuple[float, float]:
    c = c.dropna()
    if len(c) < 2:
        return np.nan, np.nan
    yrs = (c.index[-1] - c.index[0]).days / 365.25
    cagr = (c.iloc[-1] / c.iloc[0]) ** (1 / yrs) * 100 - 100
    mdd = (c / c.cummax() - 1).min() * 100
    return cagr, mdd


def series(ticker: str) -> pd.Series:
    """Get an actual ETF close series through the shared configured loader."""
    data, _vix, _regime, _report = load_all()
    require_symbols(data, [ticker])
    return data[ticker]["Close"].dropna()


def main():
    data, vix, regime, _rep = load_all()
    require_symbols(data, [tk for tk, _ in BENCH.values()])
    print(f"Configured USD data: {START} .. {END} (end exclusive)")
    print(f"Strategy per-side cost {COST:.2%}; warmup {WARMUP}; regime {CONFIG.benchmark} 200MA")
    print("Each strategy uses its native window; no ranking across different windows.")
    print("Hold baselines are gross; execution/cost models differ from strategies.")
    feats = {t: build_features(df) for t, df in data.items()}
    reg = regime.to_dict()
    for s in STRATEGIES:
        require_symbols(data, s.tickers)
        sub = {t: data[t] for t in s.tickers}
        subf = {t: feats[t] for t in sub}
        tgt, stp = BEST[s.sid]
        kw = MDD_PKG[s.sid]
        r = backtest(s, sub, subf, vix, tgt, stp, **({"regime": reg, **kw} if kw is not None else {}))
        if r is None:
            print(f"\n{s.sid}: insufficient history")
            continue
        dates = r["curve"].dropna().index
        print(f"\n{s.sid} {s.name}: {dates[0].date()} .. {dates[-1].date()}")
        print(f"{'Strategy / gross hold':<34}|{'CAGR':>8} |{'MDD':>9} |{'Sharpe':>7} |{'Exposure':>9}")
        print(
            f"{'Strategy with historical overlays':<34}|{r['cagr']:7.2f}% |{r['mdd']:8.2f}% "
            f"|{r['sharpe']:7.2f} |{r['exposure']:7.1f}%"
        )
        for label, (tk, _to_krw) in BENCH.items():
            close = data[tk]["Close"].reindex(dates)
            if close.isna().any():
                print(f"{label}: unavailable on exact strategy dates")
                continue
            c, m = stats(close)
            print(f"{label:<34}|{c:7.2f}% |{m:8.2f}%")
        # Fixed initial equal capital, without synthetic pre-inception prices.
        bh = pd.DataFrame({t: sub[t]["Close"] for t in sub}).reindex(dates)
        if bh.isna().any().any():
            print("Same-universe gross hold: unavailable on exact strategy dates")
            continue
        eq = (bh / bh.iloc[0]).mean(axis=1)
        c, m = stats(eq)
        print(f"{'Same-universe gross hold':<34}|{c:7.2f}% |{m:8.2f}% |{'':>7} |{100.0:7.1f}%")


if __name__ == "__main__":
    main()
