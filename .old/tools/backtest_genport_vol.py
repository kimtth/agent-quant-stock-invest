"""Historical GenPort-inspired volatility experiments, not deployment templates.

Original proposed indicator and rules, translated (not the implemented SD measure):
    {Bollinger_band_width} = (upper-lower)/middle * 100 = 4 * 20_days_price_stddev / MA20 * 100
    [Nasdaq2x buy] disparity(200_days) >= 100 AND decline_from_high_ratio(20_days) <= 3
                                AND rate_of_change_period(close,60_days) > 0 AND Bollinger_band_width <= LO
    [Nasdaq1x buy] same trend condition AND LO < Bollinger_band_width <= HI
    [sell]        disparity(200_days) < 100 OR decline_from_high_ratio(20_days) >= trail

Python uses stddev('{daily_price_return}',{20_days}) in percent, NOT Bollinger
bandwidth. Its build() selector uses the 2x ETF's trend and volatility for BOTH
tiers; exits use the held ETF's trend. Thus the original per-ETF bandwidth
proposal is not a 1:1 description of execution. Thresholds retain historical
values without US retuning; ma and entry_dd are configurable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtest_etf_combos import load_all
from backtest_voltarget import panel, report_rows, require_symbols, stats as return_stats
from market_config import CONFIG

COST = CONFIG.cost
WARMUP = CONFIG.warmup
NDX2, NDX = CONFIG.symbol("growth_2x"), CONFIG.symbol("growth")
BOND, GOLD, DOLLAR = CONFIG.symbol("treasury"), CONFIG.symbol("gold"), CONFIG.symbol("dollar")
DEF = [BOND, GOLD, DOLLAR]


def bandwidth(close: pd.Series) -> pd.Series:
    """stddev('{daily_price_return}',{20_days}) -- daily-return SD in percent.

    Python uses sample SD (ddof=1), not annualized; despite the function name,
    this is not Bollinger bandwidth.
    """
    return close.pct_change().rolling(20).std() * 100


def build(data, lo2, hi2, trail, ma=200, entry_dd=3.0):
    tks = sorted({NDX2, NDX, *DEF})
    close, high = panel(data, tks)
    ret = close.pct_change().fillna(0.0).clip(-0.5, 0.5)
    d_ret = ret[DEF].mean(axis=1)

    # Indicators are calculated on each ETF's own history.
    def sig(tk, lo, hi):
        c, h = close[tk], high[tk]
        above = c >= c.rolling(ma).mean()
        hh = h.rolling(20).max()
        dd = (hh - c) / hh * 100
        mo = c / c.shift(60) - 1
        bw = bandwidth(c)
        trend_ok = (above & (mo > 0)).to_numpy()
        entry_ok = (dd <= entry_dd).to_numpy()
        exit_hit = ((~above) | (dd >= trail)).to_numpy()
        lo_ok = (bw <= lo).to_numpy()
        hi_ok = ((bw > lo) & (bw <= hi)).to_numpy()
        return trend_ok, entry_ok, exit_hit, lo_ok, hi_ok

    t2, e2, x2, lo2ok, hi2ok = sig(NDX2, lo2, hi2)
    t1, e1, x1, _lo1, _hi1 = sig(NDX, lo2 / 2, hi2 / 2)

    n = len(close)
    w2 = np.zeros(n)
    w1 = np.zeros(n)
    state = 0  # 0=defense, 2=2x holding, 1=1x holding
    for i in range(n):
        if state == 2 and x2[i]:
            state = 0
        elif state == 1 and x1[i]:
            state = 0
        if state != 0:
            # Switch tiers when the volatility range changes.
            if t2[i] and lo2ok[i]:
                state = 2
            elif t2[i] and hi2ok[i]:
                state = 1
            else:
                state = 0
        else:
            if t2[i] and e2[i] and lo2ok[i]:
                state = 2
            elif t2[i] and e2[i] and hi2ok[i]:
                state = 1
        w2[i] = 1.0 if state == 2 else 0.0
        w1[i] = 1.0 if state == 1 else 0.0

    W2 = pd.Series(w2, index=close.index).shift(1).fillna(0.0)
    W1 = pd.Series(w1, index=close.index).shift(1).fillna(0.0)
    cash = (1 - W2 - W1).clip(0, 1)
    port = W2 * ret[NDX2] + W1 * ret[NDX] + cash * d_ret
    port -= (W2.diff().abs().fillna(0) + W1.diff().abs().fillna(0)) * COST
    return port.iloc[WARMUP:], W2, W1


def stats(port):
    return return_stats(port, warmup=0)


def multi(data, tickers, sd_buy, sd_sell, trail, ma=200, entry_dd=3.0):
    """Apply identical rules to N independent equal-weight ETF slots."""
    tks = sorted(set(tickers) | set(DEF))
    if not tickers:
        raise ValueError("At least one traded ETF is required")
    close, high = panel(data, tks)
    ret = close.pct_change().fillna(0.0).clip(-0.5, 0.5)
    d_ret = ret[DEF].mean(axis=1)

    hold = {}
    for tk in tickers:
        c, h = close[tk], high[tk]
        above = c >= c.rolling(ma).mean()
        hh = h.rolling(20).max()
        dd = (hh - c) / hh * 100
        mo = c / c.shift(60) - 1
        sd = c.pct_change().rolling(20).std() * 100
        buy = (above & (dd <= entry_dd) & (mo >= 0) & (sd <= sd_buy)).to_numpy()
        sell = ((~above) | (dd >= trail) | (sd > sd_sell)).to_numpy()
        st, out = False, np.zeros(len(c))
        for i in range(len(c)):
            if st and sell[i]:
                st = False
            elif not st and buy[i]:
                st = True
            out[i] = 1.0 if st else 0.0
        hold[tk] = pd.Series(out, index=c.index)

    H = pd.DataFrame(hold).shift(1).fillna(0.0) / len(tickers)
    cash = (1 - H.sum(axis=1)).clip(0, 1)
    port = sum(H[t] * ret[t] for t in tickers) + cash * d_ret
    port -= H.diff().abs().fillna(0.0).sum(axis=1) * COST
    return port.iloc[WARMUP:]


def main():
    data, _v, _r, _rep = load_all()
    require_symbols(data, [NDX2])

    c2 = data[NDX2]["Close"].dropna()
    bw2 = bandwidth(c2).dropna()
    rv2 = (c2.pct_change().rolling(20).std() * np.sqrt(252) * 100).dropna()
    j = bw2.index.intersection(rv2.index)
    print(f"[Calibration] {NDX2}: 20-session daily-return standard deviation vs annualized volatility")
    for q in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        print(f"  Quantile {q:.0%}: daily SD {bw2.loc[j].quantile(q):6.2f}%   annualized {rv2.loc[j].quantile(q):6.1f}%")
    print(f"  Correlation {bw2.loc[j].corr(rv2.loc[j]):.3f}\n")

    rows = []
    for lo2 in (1.6, 1.9, 2.2, 2.5, 2.8, 3.2):
        for hi2 in (lo2 * 1.4, lo2 * 1.8):
            for trail in (10.0, 12.0, 15.0):
                p, W2, W1 = build(data, lo2, hi2, trail)
                r = stats(p)
                r["label"] = f"Daily SD 2x<={lo2:.1f}% 1x<={hi2:.1f}% trail {trail:.0f}"
                r["w2"] = W2.mean() * 100
                r["w1"] = W1.mean() * 100
                rows.append(r)

    for r in rows:
        r["note"] = f"Mean holding weights including warmup: 2x {r['w2']:.1f}%, 1x {r['w1']:.1f}%"

    SOX2 = CONFIG.symbol("semiconductor_2x")
    GOLD2 = CONFIG.symbol("gold_2x")
    K2 = CONFIG.symbol("equity_2x")
    SETS = {
        "Growth 2x + semiconductor 2x": [NDX2, SOX2],
        "Growth 2x + gold 2x": [NDX2, GOLD2],
        "Growth 2x + semiconductor 2x + gold 2x": [NDX2, SOX2, GOLD2],
        "Growth 2x + semiconductor 2x + gold 2x + equity 2x": [NDX2, SOX2, GOLD2, K2],
    }
    for nm, tks in SETS.items():
        for sb, ss in ((3.2, 4.5), (2.5, 3.5), (2.2, 4.0)):
            r = stats(multi(data, tks, sb, ss, 15.0))
            r["label"] = f"{nm} buy SD<={sb}% sell SD>{ss}%"
            r["note"] = "Independent equal-weight slots with a defensive basket"
            rows.append(r)
    report_rows(rows, data)


if __name__ == "__main__":
    main()
