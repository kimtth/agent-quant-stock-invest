"""Shared, explicit USD research settings; importing never downloads market data."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent

DEFAULT_SYMBOLS = {
    "equity": "SPY", "equity_2x": "SSO", "growth": "QQQ", "growth_2x": "QLD",
    "small_cap": "IWM", "small_cap_2x": "UWM", "semiconductor": "SOXX",
    "semiconductor_2x": "USD", "gold": "GLD", "gold_2x": "UGL",
    "silver": "SLV", "treasury": "IEF", "long_treasury": "TLT",
    "cash": "SHY", "dollar": "UUP", "international": "VEA",
    "inverse_equity_2x": "SDS", "inverse_growth": "PSQ",
    "technology": "XLK", "healthcare": "XLV", "financials": "XLF",
    "energy": "XLE", "consumer": "XLY", "industrials": "XLI", "materials": "XLB",
}


@dataclass(frozen=True)
class ResearchConfig:
    benchmark: str = "SPY"
    start: str = "2005-01-01"
    end: str = "2026-09-01"
    cost: float = 0.001
    warmup: int = 260
    min_daily_value: float = 0.0
    symbols: dict[str, str] = field(default_factory=lambda: DEFAULT_SYMBOLS.copy())
    cache_dir: Path = TOOLS_DIR / ".cache" / "global"
    data_dir: Path | None = None
    history_csv: Path | None = None
    compare_csv: Path | None = None
    workbook: Path | None = None
    output: Path | None = None

    def __post_init__(self):
        if self.benchmark not in {"SPY", "QQQ"}:
            raise ValueError("benchmark must be SPY or QQQ")
        if date.fromisoformat(self.start) >= date.fromisoformat(self.end):
            raise ValueError("start must precede end (end is exclusive)")
        if not 0 <= self.cost < 1 or self.warmup < 260:
            raise ValueError("cost must be in [0, 1); warmup must be at least 260 sessions")
        if not 0 <= self.min_daily_value < float("inf"):
            raise ValueError("min_daily_value must be finite and non-negative (USD)")
        if set(self.symbols) != set(DEFAULT_SYMBOLS):
            raise ValueError("symbols must contain the documented asset roles")
        if any(not isinstance(s, str) or not s.strip() for s in self.symbols.values()):
            raise ValueError("symbols must be non-empty ticker strings")

    def symbol(self, role: str) -> str:
        return self.symbols[role]

    def manifest(self) -> dict:
        result = asdict(self)
        return {key: str(value) if isinstance(value, Path) else value for key, value in result.items()}


def load_config(path: str | Path | None = None) -> ResearchConfig:
    """Read a JSON config, resolving file paths relative to the config file."""
    path = path or os.environ.get("GLOBAL_RESEARCH_CONFIG")
    if not path:
        return ResearchConfig()
    source = Path(path).resolve()
    values = json.loads(source.read_text(encoding="utf-8"))
    if "symbols" in values:
        values["symbols"] = DEFAULT_SYMBOLS | values["symbols"]
    for key in ("cache_dir", "data_dir", "history_csv", "compare_csv", "workbook", "output"):
        if values.get(key) is not None:
            values[key] = (source.parent / values[key]).resolve()
    return ResearchConfig(**values)


CONFIG = load_config()