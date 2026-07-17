"""Agent Framework tools for agent-led investment research."""

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import yfinance as yf

from .models import BacktestMetrics
from .research_repl import DATASET_STOCK, ResearchPythonRepl

matplotlib.use("Agg")
import matplotlib.pyplot as plt

WORK_DIR = Path("output") / "agent_framework"


def backtest(directory: Path, capital: float) -> tuple[BacktestMetrics, Path, Path]:
    frame, signals = (
        pd.read_csv(directory / "stock_data.csv"),
        pd.read_csv(directory / "stock_signals.csv"),
    )
    if len(frame) != len(signals):
        raise ValueError("Price and signal rows must align.")
    held, positions = False, []
    for buy, sell in zip(
        signals["BuySignal"].astype(bool),
        signals["SellSignal"].astype(bool),
        strict=True,
    ):
        held = True if buy and not held else False if sell and held else held
        positions.append(int(held))
    frame["Position"] = positions
    frame["MarketReturn"] = (
        pd.to_numeric(frame["Adj Close"], errors="coerce").pct_change().fillna(0)
    )
    frame["StrategyReturn"] = (
        frame["Position"].shift(1, fill_value=0) * frame["MarketReturn"]
    )
    frame["CumulativeReturns"] = (1 + frame["StrategyReturn"]).cumprod()
    frame["PortfolioValue"] = capital * frame["CumulativeReturns"]
    frame["Drawdown"] = frame["PortfolioValue"] / frame["PortfolioValue"].cummax() - 1
    final, years, deviation = (
        float(frame["PortfolioValue"].iloc[-1]),
        max(len(frame) / 252, 1 / 252),
        float(frame["StrategyReturn"].std(ddof=0)),
    )
    metrics = BacktestMetrics(
        cumulative_return=final / capital - 1,
        cagr=(final / capital) ** (1 / years) - 1,
        maximum_drawdown=float(frame["Drawdown"].min()),
        sharpe_ratio=0
        if deviation == 0
        else float(frame["StrategyReturn"].mean() / deviation * np.sqrt(252)),
        final_value=final,
    )
    results, metrics_file = (
        directory / "backtest_results.xlsx",
        directory / "backtest_metrics.txt",
    )
    frame.to_excel(results, index=False)
    metrics_file.write_text(
        "\n".join(f"{key}: {value}" for key, value in metrics.model_dump().items()),
        encoding="utf-8",
    )
    return metrics, results, metrics_file


def plot(directory: Path) -> Path:
    frame = pd.read_excel(directory / "backtest_results.xlsx")
    figure, (returns, drawdown) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    dates = pd.to_datetime(frame["Date"])
    returns.plot(dates, frame["CumulativeReturns"])
    drawdown.fill_between(dates, frame["Drawdown"], 0, alpha=0.35, color="crimson")
    path = directory / "stock_plot.png"
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)
    return path


class AgentTools:
    """Tools available to the specialist agents in ``QuantInvestWorkflow``."""

    def __init__(self, work_dir: Path = WORK_DIR) -> None:
        self.work_dir = Path(work_dir)
        self.repl = ResearchPythonRepl(self.work_dir)

    def clear_run_artifacts(self) -> None:
        """Clear artifacts whose presence is used to advance the workflow."""
        self.repl.clear_run_artifacts()
        for name in ("backtest_results.xlsx", "backtest_metrics.txt", "stock_plot.png"):
            (self.work_dir / name).unlink(missing_ok=True)

    def fetch_stock_data(self, ticker: str, start_date: str, end_date: str) -> str:
        """Fetch requested historical OHLCV data and save it as the REPL input CSV."""
        try:
            self.work_dir.mkdir(parents=True, exist_ok=True)
            frame = yf.download(
                ticker,
                start=start_date,
                end=end_date,
                auto_adjust=False,
                progress=False,
            )
            if frame.empty:
                return f"ERROR: No data returned for {ticker}."
            if isinstance(frame.columns, pd.MultiIndex):
                frame.columns = frame.columns.get_level_values(0)
            output_path = self.work_dir / DATASET_STOCK
            frame.reset_index().to_csv(output_path, index=False)
            return f"SUCCESS: Saved {len(frame)} rows to {output_path}."
        except Exception as error:
            return f"ERROR: {error}"

    def run_python_repl(self, code: str) -> str:
        """Execute agent-authored pandas/numpy/ta code that writes validated signals."""
        return self.repl.execute(code)

    def backtest_strategy(self, initial_capital: float = 10_000) -> str:
        """Backtest the REPL-generated signal file and return research metrics."""
        try:
            return backtest(self.work_dir, initial_capital)[0].model_dump_json()
        except Exception as error:
            return f"ERROR: {error}"

    def plot_performance(self) -> str:
        """Create a cumulative-return and drawdown chart from the latest backtest."""
        try:
            return f"SUCCESS: Created {plot(self.work_dir)}."
        except Exception as error:
            return f"ERROR: {error}"
