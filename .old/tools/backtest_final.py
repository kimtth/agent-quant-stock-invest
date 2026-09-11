"""Multi-sleeve volatility-targeting research on actual USD ETFs.

Signals and volatility use each 1x ETF. Original exposure formulas, translated:
    target exposure e = clip(target_volatility / realized_volatility, 0, cap) * trend_ON
    portfolio target exposure = mean(e_i) * L
    2x ETF capital weight = exposure/2
Volatility and target are annualized percent; L is lev. Normalize if weights
exceed 100%; remaining capital, not the normalized-away excess exposure,
earns the defensive basket return.
"""

from __future__ import annotations

from itertools import product

import numpy as np
import pandas as pd

from backtest_etf_combos import load_all
from backtest_voltarget import panel, report_rows, stats as return_stats, trend_state
from market_config import CONFIG

COST = CONFIG.cost
WARMUP = CONFIG.warmup

NDX2, NDX = CONFIG.symbol("growth_2x"), CONFIG.symbol("growth")
GOLD2, GOLD = CONFIG.symbol("gold_2x"), CONFIG.symbol("gold")
K2, KOSPI = CONFIG.symbol("equity_2x"), CONFIG.symbol("equity")
SOX2, SOX = CONFIG.symbol("semiconductor_2x"), CONFIG.symbol("semiconductor")
# USD remains the legacy dollar-role alias; the ticker USD belongs to SOX2.
BOND, USD = CONFIG.symbol("treasury"), CONFIG.symbol("dollar")
DEF = [BOND, GOLD, USD]

SLEEVE_SETS = {
    "Growth": [(NDX, NDX2)],
    "Growth + gold": [(NDX, NDX2), (GOLD, GOLD2)],
    "Growth + gold + equity": [(NDX, NDX2), (GOLD, GOLD2), (KOSPI, K2)],
    "Growth + semiconductor + gold": [(NDX, NDX2), (SOX, SOX2), (GOLD, GOLD2)],
    "Growth + semiconductor + gold + equity": [(NDX, NDX2), (SOX, SOX2), (GOLD, GOLD2), (KOSPI, K2)],
}


def run(data, sleeves, tgt, cap, lev, trail, ma=200):
    tks = sorted({t for pair in sleeves for t in pair} | set(DEF))
    close, high = panel(data, tks)
    ret = close.pct_change().fillna(0.0).clip(-0.5, 0.5)
    d_ret = ret[DEF].mean(axis=1)

    w2 = {}
    for sig, trade in sleeves:
        on = trend_state(close[sig], high[sig], ma=ma, trail=trail)
        rv = ret[sig].rolling(20).std() * np.sqrt(252) * 100
        expo = (tgt / rv).clip(0, cap).fillna(0.0) * on * lev / len(sleeves)
        w2[trade] = (expo / 2).fillna(0.0)  # Capital weight in the 2x ETF.

    W = pd.DataFrame(w2)
    tot = W.sum(axis=1)
    over = tot > 1.0
    W.loc[over] = W.loc[over].div(tot[over], axis=0)

    H = W.shift(1).fillna(0.0)
    cash = (1 - H.sum(axis=1)).clip(0, 1)
    port = sum(H[t] * ret[t] for t in H.columns) + cash * d_ret
    port -= H.diff().abs().fillna(0.0).sum(axis=1) * COST
    return port.iloc[WARMUP:]


def stats(port):
    return return_stats(port, warmup=0)


def main():
    data, _v, _r, _rep = load_all()
    rows = []
    for name, sl in SLEEVE_SETS.items():
        for tgt, cap, lev, trail in product((15, 20, 25), (2.0, 3.0), (1.0, 1.5, 2.0), (12.0, 15.0)):
            r = stats(run(data, sl, tgt, cap, lev, trail))
            r["label"] = f"{name} target {tgt}% cap{cap:.0f} L{lev:.1f} trail {trail:.0f}"
            rows.append(r)

    print(f"Multi-sleeve parameter combinations: {len(rows)}")
    report_rows(rows, data)


if __name__ == "__main__":
    main()
