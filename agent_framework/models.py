"""Data contracts and strategy catalog for the Agent Framework implementation."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class StrategyIdea(BaseModel):
    name: str
    indicator: Literal["macd_rsi", "moving_average", "trix_uo"]
    description: str
    rationale: str
    investing_conditions: str
    expected_outcome: str


class WorkflowRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)
    start_date: str
    end_date: str
    initial_capital: float = Field(default=10_000, gt=0)
    strategies: list[StrategyIdea] | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.upper().strip()


class BacktestMetrics(BaseModel):
    cumulative_return: float
    cagr: float
    maximum_drawdown: float
    sharpe_ratio: float
    final_value: float


class StrategyRun(BaseModel):
    strategy: StrategyIdea
    metrics: BacktestMetrics
    output_directory: Path
    stock_data_file: Path
    signals_file: Path
    results_file: Path
    metrics_file: Path
    plot_file: Path


class WorkflowResult(BaseModel):
    ticker: str
    strategy_ideas_file: Path
    runs: list[StrategyRun]


IDEAS = (
    StrategyIdea(
        name="MACD RSI momentum",
        indicator="macd_rsi",
        description="MACD crossover confirmation with RSI filtering.",
        rationale="Pairs trend momentum with an overbought guardrail.",
        investing_conditions="Enter on a bullish crossover below RSI 70; exit on a bearish crossover or RSI above 75.",
        expected_outcome="Research hypothesis for sustained momentum.",
    ),
    StrategyIdea(
        name="Moving-average trend",
        indicator="moving_average",
        description="20-day and 60-day moving-average crossover.",
        rationale="Transparent trend-following baseline.",
        investing_conditions="Enter and exit on the corresponding crossover.",
        expected_outcome="Research benchmark for persistent trends.",
    ),
    StrategyIdea(
        name="TRIX ultimate-oscillator reversal",
        indicator="trix_uo",
        description="TRIX momentum with the Ultimate Oscillator.",
        rationale="Tests reversal timing across lookback periods.",
        investing_conditions="Enter on positive TRIX with UO below 50; exit on negative TRIX or UO above 70.",
        expected_outcome="Research hypothesis for momentum transitions.",
    ),
)
