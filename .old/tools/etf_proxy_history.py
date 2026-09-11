"""Actual-history coverage audit (historical filename retained for compatibility).

No pre-inception NAV, artificial volume, FX conversion, or retrospectively fitted
expense drag is generated. US-listed ETFs are not exact Korean ETF equivalents.
"""

from __future__ import annotations

import pandas as pd


def build_proxies(actual, start, end, calendar):
    """Compatibility API returning only observed bars and their coverage report."""
    observed, rows = {}, []
    for ticker, frame in actual.items():
        frame = frame.loc[(frame.index >= start) & (frame.index < end)]
        frame = frame.loc[frame.index.intersection(calendar)].copy()
        if frame.empty:
            raise ValueError(f"{ticker}: no actual history in the requested window")
        observed[ticker] = frame
        rows.append({"ticker": ticker, "source": "actual adjusted OHLCV",
                     "start": frame.index[0].date(), "end": frame.index[-1].date(),
                     "sessions": len(frame), "synthetic_sessions": 0})
    return observed, pd.DataFrame(rows)


def main():
    from backtest_etf_combos import load_all

    _, _, _, report = load_all()
    print("Actual ETF history coverage; synthetic extension is disabled.")
    print(report.to_string(index=False))


if __name__ == "__main__":
    main()