"""Split a portfolio into equal parts, each following an ETF's price trend.

A "sleeve" is a separately managed part of the portfolio. For example, three
sleeves each receive one third of the money. Each part holds its assigned ETF
when its trend rule is on; otherwise it holds the defensive ETF basket.

Original daily rules, translated:
    Entry: close >= N_days moving_average AND decline_from_20_days_high <= re_entry AND 60_days momentum > 0
    Exit:  close <  N_days moving_average OR  decline_from_20_days_high >= trail

In the code, ma sets the moving-average length, entry_dd sets the allowed price
drop before buying, and mom sets the momentum lookback (60 trading days by
default). Price drops from the recent high are measured in percent. Each part
splits its defensive money equally across the defensive ETFs. These are research
tests, not verified copies of strategies that can be run in GenPort.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backtest_etf_combos import load_all
from backtest_voltarget import report_rows, require_symbols
from market_config import CONFIG

COST = CONFIG.cost

NDX2, SOX2 = CONFIG.symbol("growth_2x"), CONFIG.symbol("semiconductor_2x")
NDX, SPX = CONFIG.symbol("growth"), CONFIG.symbol("equity")
EU, K2 = CONFIG.symbol("international"), CONFIG.symbol("equity_2x")
Q2, SOX = CONFIG.symbol("small_cap_2x"), CONFIG.symbol("semiconductor")
GOLD2, SILVER = CONFIG.symbol("gold_2x"), CONFIG.symbol("silver")
BOND, GOLD = CONFIG.symbol("treasury"), CONFIG.symbol("gold")
# USD is an old variable name for the dollar ETF (UUP by default).
# It does not mean ticker USD, the leveraged semiconductor ETF.
USD, KOSPI = CONFIG.symbol("dollar"), CONFIG.symbol("equity")

WARMUP = CONFIG.warmup


@dataclass
class Sleeve:
    """Settings for a group of equal portfolio parts, one per ETF in assets."""

    name: str
    assets: list[str]
    defense: list[str]
    ma: int = 200
    trail: float = 10.0
    entry_dd: float = 3.0
    mom: int = 60
    sig_of: dict[str, str] = field(default_factory=dict)  # ETF held -> ETF whose prices decide when to hold it.
    note: str = ""
    tickers: list[str] = field(init=False)

    def __post_init__(self):
        self.tickers = sorted(set(self.assets) | set(self.defense) | set(self.sig_of.values()))


STRATS = [
    Sleeve("A Growth 2x", [NDX2], [BOND, GOLD, USD], note="Single-sleeve baseline"),
    Sleeve("B Growth + semiconductor 2x", [NDX2, SOX2], [BOND, GOLD, USD], note="Two growth sleeves"),
    Sleeve("C Growth + semiconductor + gold 2x", [NDX2, SOX2, GOLD2], [BOND, GOLD, USD], note="Adds leveraged gold"),
    Sleeve("D C + equity 2x", [NDX2, SOX2, GOLD2, K2], [BOND, GOLD, USD], note="Adds broad equity"),
    Sleeve("E Five sleeves", [NDX2, SOX2, GOLD2, K2, Q2], [BOND, GOLD, USD], note="Adds small-cap equity"),
    Sleeve("F Growth + metals + international", [NDX2, SOX2, GOLD2, SILVER, EU], [BOND, GOLD, USD], note="Metals and international diversification"),
    Sleeve("G Growth + gold 2x", [NDX2, GOLD2], [BOND, GOLD, USD], note="Equity and gold"),
    Sleeve("H Four unleveraged sleeves", [NDX, SPX, GOLD, EU], [BOND, GOLD, USD], note="No leveraged ETFs"),
    Sleeve("C-trail15", [NDX2, SOX2, GOLD2], [BOND, GOLD, USD], trail=15.0, note="Wider C trail"),
    Sleeve("C-trail8", [NDX2, SOX2, GOLD2], [BOND, GOLD, USD], trail=8.0, note="Tighter C trail"),
    Sleeve("C-100MA", [NDX2, SOX2, GOLD2], [BOND, GOLD, USD], ma=100, note="Faster C gate"),
    Sleeve("C-entry5%", [NDX2, SOX2, GOLD2], [BOND, GOLD, USD], entry_dd=5.0, note="Looser C re-entry"),
    Sleeve("C-entry2%", [NDX2, SOX2, GOLD2], [BOND, GOLD, USD], entry_dd=2.0, note="Stricter C re-entry"),
    Sleeve("D-trail15", [NDX2, SOX2, GOLD2, K2], [BOND, GOLD, USD], trail=15.0, note="Wider D trail"),
    Sleeve("F-trail15", [NDX2, SOX2, GOLD2, SILVER, EU], [BOND, GOLD, USD], trail=15.0, note="Wider F trail"),
    Sleeve("P1 Signal 1x / trade 2x trail10", [NDX2], [BOND, GOLD, USD], sig_of={NDX2: NDX}, note="Unleveraged signal"),
    Sleeve("P2 Signal 1x trail8", [NDX2], [BOND, GOLD, USD], trail=8.0, sig_of={NDX2: NDX}, note="Tighter P1 trail"),
    Sleeve("P3 Signal 1x trail12", [NDX2], [BOND, GOLD, USD], trail=12.0, sig_of={NDX2: NDX}, note="Wider P1 trail"),
    Sleeve("P4 Signal 1x trail15", [NDX2], [BOND, GOLD, USD], trail=15.0, sig_of={NDX2: NDX}, note="Widest P1 trail"),
    Sleeve("P5 Signal 1x entry5%", [NDX2], [BOND, GOLD, USD], entry_dd=5.0, sig_of={NDX2: NDX}, note="Looser P1 re-entry"),
    Sleeve("P6 Signal 1x MA150", [NDX2], [BOND, GOLD, USD], ma=150, sig_of={NDX2: NDX}, note="Faster P1 gate"),
    Sleeve("P7 Signal 1x growth + gold", [NDX2, GOLD2], [BOND, GOLD, USD], sig_of={NDX2: NDX, GOLD2: GOLD}, note="Two unleveraged signals"),
    Sleeve("P8 Signal 1x three sleeves", [NDX2, GOLD2, K2], [BOND, GOLD, USD], sig_of={NDX2: NDX, GOLD2: GOLD, K2: KOSPI}, note="Adds broad equity signal"),
    Sleeve("P9 P7 trail12", [NDX2, GOLD2], [BOND, GOLD, USD], trail=12.0, sig_of={NDX2: NDX, GOLD2: GOLD}, note="Wider P7 trail"),
    Sleeve("P10 P8 trail12", [NDX2, GOLD2, K2], [BOND, GOLD, USD], trail=12.0, sig_of={NDX2: NDX, GOLD2: GOLD, K2: KOSPI}, note="Wider P8 trail"),
]


def sleeve_position(close: pd.Series, high: pd.Series, ma: int, trail: float, entry_dd: float, mom: int) -> pd.Series:
    """Return 1 when the trend rule says hold the ETF, or 0 for the defensive basket."""
    above = (close >= close.rolling(ma).mean()).to_numpy()
    hh = high.rolling(20).max()
    dd = ((hh - close) / hh * 100).to_numpy()
    mo = (close / close.shift(mom) - 1).to_numpy()

    pos = np.zeros(len(close))
    on = False
    for i in range(len(close)):
        if np.isnan(dd[i]) or np.isnan(mo[i]):
            pos[i] = 0.0
            continue
        if on:
            if not above[i] or dd[i] >= trail:
                on = False
        else:
            if above[i] and dd[i] <= entry_dd and mo[i] > 0:
                on = True
        pos[i] = 1.0 if on else 0.0
    return pd.Series(pos, index=close.index)


def run(st: Sleeve, data: dict) -> dict | None:
    """Test each portfolio part separately, then average their daily returns."""
    require_symbols(data, st.tickers)
    tk = st.tickers
    cal = sorted(set().union(*[set(data[t].index) for t in tk]))
    cal = pd.DatetimeIndex(cal)
    close = pd.DataFrame({t: data[t]["Close"] for t in tk}).reindex(cal).ffill()
    high = pd.DataFrame({t: data[t]["High"] for t in tk}).reindex(cal).ffill()

    first = max(data[t].index[0] for t in tk)
    last = min(data[t].index[-1] for t in tk)
    cal = cal[(cal >= first) & (cal <= last)]
    close, high = close.loc[cal], high.loc[cal]
    if len(cal) <= WARMUP + 250:
        return None

    ret = close.pct_change().fillna(0.0).clip(-0.5, 0.5)
    def_ret = ret[st.defense].mean(axis=1)

    sleeve_r, turn = [], []
    for a in st.assets:
        s = st.sig_of.get(a, a)
        pos = sleeve_position(close[s], high[s], st.ma, st.trail, st.entry_dd, st.mom)
        held = pos.shift(1).fillna(0.0)  # Use yesterday's decision for today's return.
        r = held * ret[a] + (1 - held) * def_ret
        c = held.diff().abs().fillna(0.0) * COST * 2  # Charge selling and buying when switching holdings.
        sleeve_r.append(r - c)
        turn.append(held.diff().abs().sum() / 2)

    port = pd.concat(sleeve_r, axis=1).mean(axis=1)
    port = port.iloc[WARMUP:]
    e = (1 + port).cumprod()
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    ddc = e / e.cummax() - 1
    trough = ddc.idxmin()
    peak = e.loc[:trough].idxmax()

    pre = e.loc[: pd.Timestamp("2026-05-31")]
    pre_yrs = (pre.index[-1] - pre.index[0]).days / 365.25 if len(pre) > 1 else 0
    exposure = float(np.mean([1.0]))  # Kept at 1 for compatibility; does not measure money in the main ETFs.
    return {
        "start": e.index[0].date(),
        "end": e.index[-1].date(),
        "years": yrs,
        "cagr": (e.iloc[-1] ** (1 / yrs) - 1) * 100,
        "mdd": ddc.min() * 100,
        "pre_cagr": (pre.iloc[-1] ** (1 / pre_yrs) - 1) * 100 if pre_yrs > 0 else np.nan,
        "pre_mdd": (pre / pre.cummax() - 1).min() * 100 if pre_yrs > 0 else np.nan,
        "mdd_from": peak.date(),
        "mdd_to": trough.date(),
        "sharpe": port.mean() / port.std() * np.sqrt(252) if port.std() > 0 else 0.0,
        "trades": sum(turn),
        "exposure": exposure,
        "curve": e,
    }


def bench(data, tk, since, until=None):
    """Calculate growth and the largest peak-to-low drop for buying and holding one ETF."""
    c = data[tk]["Close"].dropna()
    c = c[c.index >= since]
    if until is not None:
        c = c[c.index <= until]
    if len(c) < 2:
        return np.nan, np.nan
    yrs = (c.index[-1] - c.index[0]).days / 365.25
    return ((c.iloc[-1] / c.iloc[0]) ** (1 / yrs) - 1) * 100, (c / c.cummax() - 1).min() * 100


def main():
    data, _v, _r, _rep = load_all()
    rows = [(s, r) for s in STRATS if (r := run(s, data))]
    if not rows:
        raise ValueError("No sleeve has sufficient common history")
    for s, r in rows:
        r["label"] = s.name
        r["note"] = (f"{s.note}; {len(s.assets)} sleeves; MA{s.ma}; "
                     f"trail {s.trail:.0f}%; entry {s.entry_dd:.0f}%; "
                     f"round-trip equivalents including warmup {r['trades']:.1f}")
    report_rows([r for _, r in rows], data)


if __name__ == "__main__":
    main()
