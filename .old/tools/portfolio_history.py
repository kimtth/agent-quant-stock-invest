"""Validated daily portfolio histories, with no import-time file or network I/O.

Required CSV columns: date, return, asset, cash, held. English return values
are decimals. Accepted original export aliases are: 날짜, 일일수익률, 총자산,
남은 현금, 남은 종목수; only 일일수익률 is divided by 100. ``assets`` is also
accepted for asset. Optional buys (alias 매수 종목수) is a non-negative integer;
it is never inferred from returns or holdings. Dates must be ISO YYYY-MM-DD,
unique, and strictly increasing. Ambiguous aliases are rejected.

CSV histories retain their supplied daily returns and cost treatment. Filtering
uses start inclusive/end exclusive and does not reapply costs or warmup.
Benchmark fallback is normalized adjusted-Close buy-and-hold, gross of costs,
with the first observation as a zero-return anchor, cash=0, held=1, buys=None.
It is not an execution log. Overlay results scale historical daily returns;
residual exposure is a scenario assumption, not observed order execution.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path


ALIASES = {
    "date": ("date", "날짜"),
    "return": ("return", "일일수익률"),
    "asset": ("asset", "assets", "총자산"),
    "cash": ("cash", "남은 현금"),
    "held": ("held", "남은 종목수"),
    "buys": ("buys", "매수 종목수"),
}

RESEARCH_NOTICE = (
    "Counterfactual return overlays, not actual trade executions. Residual "
    "exposure is assumed; execution costs/slippage are not simulated. "
    "Historical grid search is in-sample research, not out-of-sample evidence."
)


@dataclass
class Row:
    date: str
    ret: float
    asset: float
    cash: float
    held: int
    buys: int | None = None


def _date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("date must be ISO YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ValueError("date must be ISO YYYY-MM-DD")
    return value


def _number(value: str, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _count(value: str, field: str) -> int:
    result = _number(value, field)
    if result < 0 or not result.is_integer():
        raise ValueError(f"{field} must be a non-negative integer")
    return int(result)


def read_history(
    path: str | Path, *, require_buys: bool = False,
    start: str | None = None, end: str | None = None,
) -> list[Row]:
    """Validate the entire CSV before selecting [start, end); never sort silently."""
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"History CSV not found: {source}. Set history_csv/compare_csv to an existing CSV.")
    if start is not None:
        _date(start)
    if end is not None:
        _date(end)
    if start is not None and end is not None and start >= end:
        raise ValueError("start must precede exclusive end")
    rows: list[Row] = []
    try:
        with source.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh, strict=True)
            headers = reader.fieldnames or []
            if len(headers) != len(set(headers)):
                raise ValueError("duplicate CSV column names")
            columns = {}
            for field, aliases in ALIASES.items():
                found = [alias for alias in aliases if alias in headers]
                if len(found) > 1:
                    raise ValueError(f"ambiguous columns for {field}: {found}; supply only one alias")
                if not found and (field != "buys" or require_buys):
                    raise ValueError(f"missing required column {field}; accepted aliases: {', '.join(aliases)}")
                if found:
                    columns[field] = found[0]
            previous = ""
            for line, raw in enumerate(reader, 2):
                try:
                    if None in raw or any(v is None for v in raw.values()):
                        raise ValueError("row width does not match CSV header")
                    day = _date(raw[columns["date"]].strip())
                    if day <= previous:
                        raise ValueError("dates must be unique and strictly increasing; remove duplicates and order rows")
                    ret = _number(raw[columns["return"]], "return")
                    if columns["return"] == "일일수익률":
                        ret /= 100.0
                    asset = _number(raw[columns["asset"]], "asset")
                    cash = _number(raw[columns["cash"]], "cash")
                    held = _count(raw[columns["held"]], "held")
                    buys = _count(raw[columns["buys"]], "buys") if "buys" in columns else None
                    if ret <= -1:
                        raise ValueError("return must be greater than -1 (English returns are decimals)")
                    if asset <= 0:
                        raise ValueError("asset must be positive")
                    if not 0 <= cash <= asset:
                        raise ValueError("cash must be non-negative and no greater than asset")
                    rows.append(Row(day, ret, asset, cash, held, buys))
                    previous = day
                except ValueError as exc:
                    raise ValueError(f"row {line}: {exc}") from exc
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        raise ValueError(f"Invalid history CSV {source}: {exc}") from exc
    if not rows:
        raise ValueError(f"History CSV {source} has no data rows; supply daily history.")
    rows = [r for r in rows if (start is None or r.date >= start) and (end is None or r.date < end)]
    if not rows:
        raise ValueError(f"History CSV {source} has no rows in [{start}, {end}); adjust the configured dates.")
    return rows


def benchmark_history() -> list[Row]:
    """Build gross SPY/QQQ hold observations from actual adjusted Close only."""
    import pandas as pd
    from market_config import CONFIG
    from market_data import download_ohlcv

    data = download_ohlcv([CONFIG.benchmark], CONFIG.start, CONFIG.end)
    frame = data.get(CONFIG.benchmark)
    if frame is None or frame.empty or "Close" not in frame:
        raise ValueError(f"No adjusted Close data for {CONFIG.benchmark}; provide data_dir or history_csv.")
    try:
        index = pd.DatetimeIndex(pd.to_datetime(frame.index, errors="coerce"))
        close = pd.to_numeric(frame["Close"], errors="coerce")
    except (TypeError, ValueError) as exc:
        raise ValueError("Benchmark requires valid daily dates and one numeric adjusted Close column.") from exc
    if index.isna().any() or index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("Benchmark dates must be valid, unique, and strictly increasing.")
    dates = [d.date().isoformat() for d in index]
    if len(set(dates)) != len(dates):
        raise ValueError("Benchmark must have one observation per date.")
    if any(not math.isfinite(float(v)) or v <= 0 for v in close):
        raise ValueError("Benchmark adjusted Close must be finite and positive.")
    selected = [(day, float(v)) for day, v in zip(dates, close) if CONFIG.start <= day < CONFIG.end]
    if len(selected) < 2:
        raise ValueError("Benchmark needs at least two adjusted Close observations in the configured date range.")
    first = previous = selected[0][1]
    rows = []
    for day, price in selected:
        ret, asset = price / previous - 1, price / first
        if not math.isfinite(ret) or ret <= -1 or not math.isfinite(asset) or asset <= 0:
            raise ValueError("Benchmark price ratios must produce finite positive equity and returns greater than -1.")
        rows.append(Row(day, ret, asset, 0.0, 1))
        previous = price
    return rows


def mar(cagr: float, mdd: float) -> float:
    """MAR is undefined without drawdown; report NaN rather than divide by zero."""
    return cagr / -mdd if mdd < 0 else float("nan")