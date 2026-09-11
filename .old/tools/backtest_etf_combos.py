"""Research ETF strategies using configurable USD-listed asset roles.

Signals use session closes and fill at the next session open. Intraday stops
precede targets if both are touched. Actual adjusted OHLCV only; historical
Korean results and tuned overlays are not performance evidence for this universe.

Original GenPort factor notation, translated:
    disparity({N_days})                    -> close / MA(N) * 100
    rate_of_change_period({close},{N_days}) -> (close / close.shift(N) - 1) * 100
    max_value({close},{N_days})             -> close.rolling(N).max()
    {RSI}                                  -> Wilder-style RSI(14)
    {traded_value}                         -> volume * close
    {VIX_close}                            -> ^VIX close
Traded value is now USD, not the original KRW. VIX uses the current US close
for next-open signals, not the original one-session shift for Korean trading.
These English names explain the original notation; they are not Python calls.
"""

from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from market_config import CONFIG
from market_data import download_ohlcv

START = CONFIG.start
END = CONFIG.end
MAX_POS = 3
COST = CONFIG.cost
WARMUP = CONFIG.warmup
CACHE = CONFIG.cache_dir / (hashlib.sha256(json.dumps(CONFIG.manifest(), sort_keys=True).encode()).hexdigest()[:20] + '.pkl')

# (target %, stop %) overlays. None = no price target.
OVERLAYS: list[tuple[float | None, float | None]] = [
    (None, None),
    (35.0, -1.5),
    (35.0, -8.0),
    (25.0, -10.0),
    (50.0, -15.0),
    (20.0, -7.0),
]


@dataclass
class Strategy:
    sid: str
    name: str
    tickers: dict[str, str]
    buy: callable
    sell: callable
    default_overlay: tuple[float | None, float | None] = (None, None)
    notes: str = field(default="")


# --------------------------------------------------------------------------
# indicators
# --------------------------------------------------------------------------
def disp(close: pd.Series, n: int) -> pd.Series:
    return close / close.rolling(n).mean() * 100


def chg(close: pd.Series, n: int) -> pd.Series:
    return (close / close.shift(n) - 1) * 100


def hi(close: pd.Series, n: int) -> pd.Series:
    return close.rolling(n).max()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    c = df["Close"]
    f = pd.DataFrame(index=df.index)
    for n in (10, 20, 60, 120, 200):
        f[f"disp{n}"] = disp(c, n)
    for n in (10, 20, 60, 120, 240):
        f[f"ret{n}"] = chg(c, n)
    for n in (60, 120):
        f[f"nh{n}"] = c / hi(c, n)
    # decline_from_high_ratio({N_days}) = (period_intraday_high - close) / period_intraday_high * 100
    for n in (20, 60):
        hh = df["High"].rolling(n).max()
        f[f"dd{n}"] = (hh - c) / hh * 100
    # {downside_volatility}: Ulcer Index, 14 sessions (percent drawdowns).
    ddp = (c / c.rolling(14).max() - 1) * 100
    f["ulcer"] = np.sqrt((ddp**2).rolling(14).mean())
    f["rsi"] = rsi(c)
    f["value"] = df["Volume"] * c
    return f


# --------------------------------------------------------------------------
# buy / sell rules  (f = feature row dict, v = vix dict)
# --------------------------------------------------------------------------
def s1_buy(f, v):
    a = f["disp20"] >= 100
    b = f["disp60"] >= 100
    c = f["ret60"] >= 0
    d = f["nh120"] >= 0.93
    e = f["ret20"] >= 3
    g = v["vix"] <= 32
    h = f["value"] >= CONFIG.min_daily_value
    return (a and b and c) and (d or e) and (g and h)


def s1_sell(f, v):
    return f["disp20"] <= 98 or f["ret60"] <= -5 or v["vix"] >= 40


def s2_buy(f, v):
    a = f["ret240"] >= 0
    b = f["ret120"] >= 0
    c = f["ret60"] >= 0
    d = f["disp120"] >= 100
    e = f["value"] >= CONFIG.min_daily_value
    return ((a and b) or (b and c)) and d and e


def s2_sell(f, v):
    return f["ret120"] <= 0 or f["disp120"] <= 97


def s3_buy(f, v):
    a = f["disp20"] >= 101
    b = f["disp60"] >= 100
    c = f["ret20"] >= 2
    d = f["ret60"] >= 5
    e = f["nh60"] >= 0.95
    g = f["rsi"] <= 75
    h = f["value"] >= CONFIG.min_daily_value
    return (a and b) and (c or d) and e and g and h


def s3_sell(f, v):
    return f["disp20"] <= 98 or f["rsi"] >= 80 or f["ret20"] <= -7


def s4_buy(f, v):
    a = f["disp20"] >= 100
    b = f["disp60"] >= 100
    c = f["ret20"] >= 1
    d = f["ret60"] >= 2
    e = f["nh120"] >= 0.92
    g = f["value"] >= CONFIG.min_daily_value
    return a and b and (c or d) and e and g


def s4_sell(f, v):
    return f["disp20"] <= 97 or f["ret20"] <= -5


def s5_buy(f, v):
    a = f["disp10"] >= 100
    b = f["disp60"] >= 101
    c = f["nh60"] >= 0.97
    d = f["ret10"] >= 2
    e = f["rsi"] <= 78
    g = v["vix"] <= 28
    h = f["value"] >= CONFIG.min_daily_value
    return (a and b) and (c or d) and e and g and h


def s5_sell(f, v):
    return f["disp10"] <= 97 or f["ret10"] <= -6 or v["vixchg5"] >= 25


def basket(*roles):
    return {CONFIG.symbol(role): role.replace('_', ' ') for role in roles}


STRATEGIES = [
    Strategy(
        "S1",
        "Leveraged dual-momentum rotation",
        basket("equity_2x", "small_cap_2x", "growth", "growth_2x", "semiconductor_2x", "gold_2x", "silver"),
        s1_buy,
        s1_sell,
        (35.0, -8.0),
    ),
    Strategy(
        "S2",
        "Multi-asset dual momentum",
        basket("equity", "growth", "international", "gold", "treasury", "long_treasury", "cash"),
        s2_buy,
        s2_sell,
        (25.0, -10.0),
    ),
    Strategy(
        "S3",
        "Sector rotation",
        basket("semiconductor", "technology", "materials", "healthcare", "financials", "energy", "consumer", "industrials"),
        s3_buy,
        s3_sell,
        (20.0, -7.0),
    ),
    Strategy(
        "S4",
        "Regime barbell hedge",
        basket("equity_2x", "inverse_equity_2x", "inverse_growth", "gold", "dollar", "long_treasury", "cash"),
        s4_buy,
        s4_sell,
        (20.0, -7.0),
    ),
    Strategy(
        "S5",
        "Semiconductor and growth with hedges",
        basket("semiconductor_2x", "semiconductor", "growth", "gold", "dollar", "cash"),
        s5_buy,
        s5_sell,
        (35.0, -8.0),
    ),
]


def load(tickers: list[str]) -> dict[str, pd.DataFrame]:
    data = download_ohlcv(tickers, START, END)
    short = [ticker for ticker, frame in data.items() if len(frame) <= WARMUP]
    if short:
        raise ValueError(f'Insufficient history for warmup={WARMUP}: {short}')
    return data


def load_vix() -> pd.DataFrame:
    c = download_ohlcv(["^VIX"], START, END)["^VIX"]["Close"]
    # US close is known when these close-based signals are formed.
    return pd.DataFrame({"vix": c, "vixchg5": (c / c.shift(5) - 1) * 100})


def load_regime() -> pd.Series:
    c = load([CONFIG.benchmark])[CONFIG.benchmark]["Close"]
    return (c >= c.rolling(200).mean()).astype(float)


def load_kospi() -> pd.Series:
    """Original gate: {DOW_index_close} >= moving_average({DOW_index_close},{200_days}).

    Compatibility alias: now uses configured SPY/QQQ, not DOW or the original
    KOSPI proxy. The translated original indicator is not the current data source.
    """
    return load_regime()


def load_all(refresh: bool = False):
    """Actual history on the benchmark's real sessions, never business-day proxies.

    Warmup remains part of each strategy's existing calculation. Reported windows
    must be inspected before comparing engines with different execution semantics.
    """
    # Offline fixtures are always re-read; never reuse a cache after CSV edits.
    if CONFIG.data_dir is None and CACHE.exists() and not refresh:
        with CACHE.open("rb") as fh:
            return pickle.load(fh)  # trusted, locally generated research cache only
    tickers = sorted(set(CONFIG.symbols.values()) | {"SPY", "QQQ"})
    data = load(tickers)
    vix = load_vix()
    calendar = data[CONFIG.benchmark].index
    data = {t: df.loc[df.index.intersection(calendar)] for t, df in data.items()}
    short = [t for t, df in data.items() if len(df) <= WARMUP]
    if short:
        raise ValueError(f'Insufficient overlapping sessions: {short}')
    c = data[CONFIG.benchmark]["Close"]
    regime = (c >= c.rolling(200).mean()).astype(float)
    report = pd.DataFrame(
        [
            {"ticker": t, "source": "actual adjusted OHLCV", "start": df.index[0].date(), "end": df.index[-1].date(), "sessions": len(df)}
            for t, df in data.items()
        ]
    )
    bundle = (data, vix, regime, report)
    if CONFIG.data_dir is None:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        with CACHE.open("wb") as fh:
            pickle.dump(bundle, fh)
    return bundle


# --------------------------------------------------------------------------
# engine
# --------------------------------------------------------------------------
def price_score(feats: dict[str, pd.DataFrame], day, names: list[str]) -> dict[str, float]:
    """Cross-sectional percentile rank of price momentum."""
    cols = ["ret20", "ret60", "disp20", "disp60"]
    rows = {}
    for n in names:
        f = feats[n]
        if day in f.index:
            r = f.loc[day]
            if not r[cols].isna().any():
                rows[n] = r[cols]
    if not rows:
        return {}
    m = pd.DataFrame(rows).T
    return m.rank(pct=True).mean(axis=1).mul(100).to_dict()


def backtest(
    strat: Strategy,
    data,
    feats,
    vix,
    target,
    stop,
    max_pos=MAX_POS,
    common=False,
    regime=None,
    extra_sell=None,
):
    names = list(data.keys())
    cal = sorted(set().union(*[set(d.index) for d in data.values()]))
    ready = {n: data[n].index[WARMUP] for n in names}
    start = max(ready.values()) if common else min(ready.values())
    cal = [d for d in cal if d >= start]
    if len(cal) < 250:
        return None

    cash, pos = 1.0, {}  # pos[name] = dict(shares, entry)
    pend_buy, pend_sell = [], []
    curve, trades, wins = [], 0, 0
    expo: list[float] = []

    # forward-filled mark prices so calendar gaps never zero out a holding
    mark = pd.DataFrame({n: data[n]["Close"] for n in names}).reindex(cal).ffill()

    for day in cal:
        px = {n: data[n].loc[day] for n in names if day in data[n].index}
        mk = mark.loc[day]

        # --- fills at open ---
        for n in pend_sell:
            if n in pos and n in px:
                cash += pos[n]["shares"] * px[n]["Open"] * (1 - COST)
                trades += 1
                wins += px[n]["Open"] > pos[n]["entry"]
                del pos[n]
        if pend_buy:
            slots = max_pos - len(pos)
            equity = cash + sum(pos[n]["shares"] * mk[n] for n in pos)
            for n in pend_buy[:slots]:
                if n in pos or n not in px:
                    continue
                budget = min(cash, equity / max_pos)
                if budget <= 0:
                    break
                o = px[n]["Open"]
                sh = budget / (o * (1 + COST))
                cash -= sh * o * (1 + COST)
                pos[n] = {"shares": sh, "entry": o}
        pend_buy, pend_sell = [], []

        # --- intraday target / stop ---
        for n in list(pos):
            if n not in px:
                continue
            e = pos[n]["entry"]
            lo, hi_ = px[n]["Low"], px[n]["High"]
            exit_px = None
            if stop is not None and lo <= e * (1 + stop / 100):
                exit_px = min(e * (1 + stop / 100), px[n]["Open"])
            elif target is not None and hi_ >= e * (1 + target / 100):
                exit_px = max(e * (1 + target / 100), px[n]["Open"])
            if exit_px is not None:
                cash += pos[n]["shares"] * exit_px * (1 - COST)
                trades += 1
                wins += exit_px > e
                del pos[n]

        equity = cash + sum(pos[n]["shares"] * mk[n] for n in pos)
        curve.append((day, equity))
        expo.append(0.0 if equity <= 0 else (equity - cash) / equity)

        # --- signals on close ---
        vrow = vix.reindex([day], method="ffill").iloc[0]
        v = {"vix": float(vrow["vix"]), "vixchg5": float(vrow["vixchg5"])}
        if np.isnan(v["vix"]):
            continue

        for n in list(pos):
            f = feats[n]
            if day not in f.index:
                continue
            row = f.loc[day].to_dict()
            if any(pd.isna(row[k]) for k in ("disp10", "disp20", "disp60", "ret10", "ret20", "ret60")):
                continue
            if strat.sell(row, v) or (extra_sell is not None and extra_sell(row, v)):
                pend_sell.append(n)

        cands = []
        risk_on = True if regime is None else bool(regime.get(day, 0.0))
        for n in names:
            if not risk_on:
                break
            if n in pos or n in pend_sell or day not in feats[n].index or day < ready[n]:
                continue
            row = feats[n].loc[day].to_dict()
            if any(pd.isna(x) for x in row.values()):
                continue
            try:
                if strat.buy(row, v):
                    cands.append(n)
            except (TypeError, ValueError):
                continue
        if cands:
            sc = price_score(feats, day, cands)
            pend_buy = sorted(cands, key=lambda n: -sc.get(n, 0))

    eq = pd.Series(dict(curve)).sort_index().dropna()
    eq = eq[eq > 0]
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] ** (1 / yrs) - 1) * 100
    mdd = ((eq / eq.cummax()) - 1).min() * 100
    dr = eq.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    sharpe = dr.mean() / dr.std() * np.sqrt(252) if dr.std() > 0 else 0.0
    return {
        "start": eq.index[0].date(),
        "end": eq.index[-1].date(),
        "years": yrs,
        "cagr": cagr,
        "mdd": mdd,
        "sharpe": sharpe,
        "trades": trades,
        "winrate": wins / trades * 100 if trades else 0,
        "exposure": float(np.mean(expo)) * 100 if expo else 0.0,
        "final": eq.iloc[-1],
        "curve": eq,
    }


def buyhold(data, tickers):
    cal = sorted(set().union(*[set(data[t].index) for t in tickers if t in data]))
    start = max(data[t].index[WARMUP] for t in tickers if t in data)
    cal = [d for d in cal if d >= start]
    sub = pd.DataFrame({t: data[t]["Close"].reindex(cal).ffill() for t in tickers if t in data})
    sub = sub.dropna()
    eq = (sub / sub.iloc[0]).mean(axis=1)
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    return {
        "cagr": (eq.iloc[-1] ** (1 / yrs) - 1) * 100,
        "mdd": ((eq / eq.cummax()) - 1).min() * 100,
        "start": eq.index[0].date(),
        "years": yrs,
    }


def main():
    data, vix, _regime, report = load_all()
    feats = {t: build_features(df) for t, df in data.items()}
    print(f'Benchmark={CONFIG.benchmark}; currency=USD; cost/side={COST:.2%}; warmup={WARMUP}')
    print('Actual adjusted ETF history (no synthetic extension):')
    print(report.to_string(index=False))
    print('Exploratory overlays, not optimized or validated for this market.')
    for s in STRATEGIES:
        sub = {t: data[t] for t in s.tickers}
        subf = {t: feats[t] for t in sub}
        print(f'\n{s.sid} {s.name}; max positions={MAX_POS}')
        bh = buyhold(data, list(s.tickers))
        print(f"Basket buy-and-hold: CAGR={bh['cagr']:.2f}% MDD={bh['mdd']:.2f}% start={bh['start']}")
        print('Common basket window only; different baskets may start on different dates.')
        for tgt, stp in OVERLAYS:
            result = backtest(s, sub, subf, vix, tgt, stp, common=True)
            if result is None:
                print('Insufficient evaluation history (need 250 sessions after warmup).')
                continue
            print(f"target={tgt} stop={stp}: CAGR={result['cagr']:.2f}% MDD={result['mdd']:.2f}% Sharpe={result['sharpe']:.2f} {result['start']}..{result['end']}")

if __name__ == '__main__':
    main()
