"""Data contracts for the Agent Framework research tools."""

from pydantic import BaseModel


class BacktestMetrics(BaseModel):
    cumulative_return: float
    cagr: float
    maximum_drawdown: float
    sharpe_ratio: float
    final_value: float
