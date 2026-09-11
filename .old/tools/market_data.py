"""Actual adjusted ETF bars only: no synthetic history or currency conversion."""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from market_config import CONFIG


def validate_bars(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [str(column).strip().title() for column in frame.columns]
    required = ["Open", "High", "Low", "Close", "Volume"]
    if any(column not in frame for column in required):
        raise ValueError(f"{symbol}: expected Date, Open, High, Low, Close, Volume")
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame.index, errors="raise")).tz_localize(None)
    if frame.index.has_duplicates or frame.index.isna().any():
        raise ValueError(f"{symbol}: duplicate or invalid dates")
    frame = frame[required].apply(pd.to_numeric, errors="raise").sort_index()
    if frame.empty or frame.isna().any().any():
        raise ValueError(f"{symbol}: empty data or missing OHLCV values")
    import numpy as np
    if not np.isfinite(frame.to_numpy()).all():
        raise ValueError(f"{symbol}: non-finite values")
    if (frame[required[:4]] <= 0).any().any() or (frame.Volume < 0).any():
        raise ValueError(f"{symbol}: prices must be positive and volume non-negative")
    if (frame.High < frame[["Open", "Close", "Low"]].max(axis=1)).any() or (
        frame.Low > frame[["Open", "Close", "High"]].min(axis=1)
    ).any():
        raise ValueError(f"{symbol}: inconsistent OHLC bars")
    return frame


def download_ohlcv(symbols: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    """Read adjusted local CSVs when configured; otherwise download from Yahoo."""
    symbols = list(dict.fromkeys(symbols))
    if not symbols:
        raise ValueError("At least one symbol is required")
    out = {}
    if CONFIG.data_dir is not None:
        for symbol in symbols:
            path = CONFIG.data_dir / f"{symbol}.csv"
            if not path.is_file():
                raise FileNotFoundError(f"Missing adjusted OHLCV input: {path}")
            frame = pd.read_csv(path)
            date_column = next((c for c in frame if c.lower() == "date"), None)
            if date_column is None:
                raise ValueError(f"{path}: Date column is required")
            out[symbol] = validate_bars(frame.set_index(date_column), symbol)
    else:
        raw = yf.download(symbols, start=start, end=end, auto_adjust=True,
                          progress=False, group_by="ticker")
        for symbol in symbols:
            if isinstance(raw.columns, pd.MultiIndex):
                level = next((i for i in range(raw.columns.nlevels)
                              if symbol in raw.columns.get_level_values(i)), None)
                if level is None:
                    raise ValueError(f"No data returned for {symbol}")
                frame = raw.xs(symbol, axis=1, level=level)
            else:
                frame = raw
            out[symbol] = validate_bars(frame.dropna(how="all"), symbol)
    for symbol, frame in out.items():
        frame = frame.loc[(frame.index >= start) & (frame.index < end)]
        if frame.empty:
            raise ValueError(f"{symbol}: no data in [{start}, {end})")
        out[symbol] = frame
    return out