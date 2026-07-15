"""Agent Framework tools and deterministic research operations."""

import os
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import ta
import yfinance as yf

from .models import BacktestMetrics, StrategyIdea

matplotlib.use("Agg")
import matplotlib.pyplot as plt

WORK_DIR = Path("output") / "agent_framework"
DATASET_STOCK, DATASET_SIGNALS = "stock_data.csv", "stock_signals.csv"


def safe_name(value: str) -> str:
    return "_".join(
        "".join(char for char in word if char.isalnum()).lower()
        for word in value.split()
    )


def generate_signals(
    prices: pd.DataFrame, idea: StrategyIdea
) -> tuple[pd.Series, pd.Series]:
    price = pd.to_numeric(prices["Adj Close"], errors="coerce")
    if idea.indicator == "macd_rsi":
        macd, rsi = ta.trend.MACD(price), ta.momentum.RSIIndicator(price).rsi()
        return (
            (macd.macd() > macd.macd_signal())
            & (macd.macd().shift() <= macd.macd_signal().shift())
            & (rsi < 70),
            (
                (macd.macd() < macd.macd_signal())
                & (macd.macd().shift() >= macd.macd_signal().shift())
            )
            | (rsi > 75),
        )
    if idea.indicator == "moving_average":
        short, long = (
            ta.trend.sma_indicator(price, 20),
            ta.trend.sma_indicator(price, 60),
        )
        return (short > long) & (short.shift() <= long.shift()), (short < long) & (
            short.shift() >= long.shift()
        )
    trix = ta.trend.TRIXIndicator(price).trix()
    oscillator = ta.momentum.UltimateOscillator(
        prices["High"], prices["Low"], price
    ).ultimate_oscillator()
    return (trix > 0) & (trix.shift() <= 0) & (oscillator < 50), (
        (trix < 0) & (trix.shift() >= 0)
    ) | (oscillator > 70)


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
    def fetch_stock_data(self, ticker: str, start_date: str, end_date: str) -> str:
        try:
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
            WORK_DIR.mkdir(parents=True, exist_ok=True)
            frame.reset_index().to_csv(WORK_DIR / DATASET_STOCK, index=False)
            return f"SUCCESS: Saved {len(frame)} rows."
        except Exception as error:
            return f"ERROR: {error}"

    def execute_python_code(self, code: str) -> str:
        try:
            exec(
                code,
                {
                    "__builtins__": __builtins__,
                    "os": os,
                    "pd": pd,
                    "np": np,
                    "ta": ta,
                    "WORK_DIR": str(WORK_DIR),
                    "INPUT_FILE": DATASET_STOCK,
                    "OUTPUT_FILE": DATASET_SIGNALS,
                },
            )
            return (
                "SUCCESS"
                if (WORK_DIR / DATASET_SIGNALS).is_file()
                else "ERROR: Signal file was not created."
            )
        except Exception as error:
            return f"ERROR: {error}"

    def backtest_strategy(self, initial_capital: float = 10_000) -> str:
        try:
            return backtest(WORK_DIR, initial_capital)[0].model_dump_json()
        except Exception as error:
            return f"ERROR: {error}"
