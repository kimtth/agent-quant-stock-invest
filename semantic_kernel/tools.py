"""Native Semantic Kernel plugins for investment research."""

import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import matplotlib
import numpy as np
import pandas as pd
import ta
import yfinance as yf
from semantic_kernel.functions import kernel_function

from .models import BacktestMetrics, IDEAS, StrategyIdea

matplotlib.use("Agg")
import matplotlib.pyplot as plt


class StrategyIdeasPlugin:
    def __init__(self, output: Path) -> None:
        self.output = output

    @kernel_function(description="Create approved technical-analysis research ideas.")
    def create_strategy_ideas(self) -> str:
        self.output.mkdir(parents=True, exist_ok=True)
        path = self.output / "strategy_ideas.json"
        path.write_text(
            json.dumps([idea.model_dump() for idea in IDEAS], indent=2),
            encoding="utf-8",
        )
        return str(path)

    def load(self) -> list[StrategyIdea]:
        return [
            StrategyIdea.model_validate(item)
            for item in json.loads(
                (self.output / "strategy_ideas.json").read_text(encoding="utf-8")
            )
        ]


class MarketResearchPlugin:
    @kernel_function(description="Search public market-research sources with Bing.")
    def search_web(self, query: str, result_count: int = 5) -> str:
        key = os.getenv("BING_SEARCH_API_KEY")
        if not key:
            return json.dumps({"status": "not_configured", "results": []})
        request = Request(
            f"https://api.bing.microsoft.com/v7.0/search?{urlencode({'q': query, 'count': max(1, min(result_count, 10))})}",
            headers={"Ocp-Apim-Subscription-Key": key},
        )
        with urlopen(request, timeout=20) as response:
            items = json.load(response).get("webPages", {}).get("value", [])  # nosec B310
        return json.dumps(
            {
                "status": "ok",
                "results": [
                    {name: item.get(name) for name in ("name", "url", "snippet")}
                    for item in items
                ],
            }
        )


class StockDataPlugin:
    def __init__(self, output: Path) -> None:
        self.output = output

    @kernel_function(description="Fetch historical OHLCV data as CSV.")
    def fetch_stock_data(self, ticker: str, start_date: str, end_date: str) -> str:
        frame = yf.download(
            ticker, start=start_date, end=end_date, auto_adjust=False, progress=False
        )
        if frame.empty:
            raise ValueError(f"No data returned for {ticker}.")
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
        frame = frame.reset_index()
        self.output.mkdir(parents=True, exist_ok=True)
        path = self.output / "stock_data.csv"
        frame[
            [
                name
                for name in (
                    "Date",
                    "Open",
                    "High",
                    "Low",
                    "Close",
                    "Adj Close",
                    "Volume",
                )
                if name in frame
            ]
        ].dropna().to_csv(path, index=False)
        return str(path)


class SignalGenerationPlugin:
    def __init__(self, output: Path) -> None:
        self.output = output

    @kernel_function(description="Generate validated buy and sell signals.")
    def generate_signals(self, indicator: str, description: str) -> str:
        prices = pd.read_csv(self.output / "stock_data.csv")
        price = pd.to_numeric(prices["Adj Close"], errors="coerce")
        if indicator == "macd_rsi":
            macd, rsi = ta.trend.MACD(price), ta.momentum.RSIIndicator(price).rsi()
            buy = (
                (macd.macd() > macd.macd_signal())
                & (macd.macd().shift() <= macd.macd_signal().shift())
                & (rsi < 70)
            )
            sell = (
                (macd.macd() < macd.macd_signal())
                & (macd.macd().shift() >= macd.macd_signal().shift())
            ) | (rsi > 75)
        elif indicator == "moving_average":
            short, long = (
                ta.trend.sma_indicator(price, 20),
                ta.trend.sma_indicator(price, 60),
            )
            buy, sell = (
                (short > long) & (short.shift() <= long.shift()),
                (short < long) & (short.shift() >= long.shift()),
            )
        else:
            trix = ta.trend.TRIXIndicator(price).trix()
            oscillator = ta.momentum.UltimateOscillator(
                prices["High"], prices["Low"], price
            ).ultimate_oscillator()
            buy, sell = (
                (trix > 0) & (trix.shift() <= 0) & (oscillator < 50),
                ((trix < 0) & (trix.shift() >= 0)) | (oscillator > 70),
            )
        path = self.output / "stock_signals.csv"
        pd.DataFrame(
            {
                "BuySignal": buy.fillna(False),
                "SellSignal": sell.fillna(False),
                "Description": description,
            }
        ).to_csv(path, index=False)
        return str(path)

    def generate(self, idea: StrategyIdea) -> Path:
        return Path(self.generate_signals(idea.indicator, idea.description))


class BacktestingPlugin:
    def __init__(self, output: Path) -> None:
        self.output = output

    @kernel_function(
        description="Backtest long-only signals with next-session returns."
    )
    def backtest_strategy(self, capital: float = 10_000) -> str:
        frame, signals = (
            pd.read_csv(self.output / "stock_data.csv"),
            pd.read_csv(self.output / "stock_signals.csv"),
        )
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
        frame["Drawdown"] = (
            frame["PortfolioValue"] / frame["PortfolioValue"].cummax() - 1
        )
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
        results, metric_file = (
            self.output / "backtest_results.xlsx",
            self.output / "backtest_metrics.txt",
        )
        frame.to_excel(results, index=False)
        metric_file.write_text(
            "\n".join(f"{key}: {value}" for key, value in metrics.model_dump().items()),
            encoding="utf-8",
        )
        return metrics.model_dump_json()

    def run(self, capital: float):
        return (
            BacktestMetrics.model_validate_json(self.backtest_strategy(capital)),
            self.output / "backtest_results.xlsx",
            self.output / "backtest_metrics.txt",
        )


class ReportingPlugin:
    def __init__(self, output: Path) -> None:
        self.output = output

    @kernel_function(description="Plot cumulative return and drawdown.")
    def plot_performance(self) -> str:
        frame = pd.read_excel(self.output / "backtest_results.xlsx")
        dates = pd.to_datetime(frame["Date"])
        figure, (returns, drawdown) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
        returns.plot(dates, frame["CumulativeReturns"])
        drawdown.fill_between(dates, frame["Drawdown"], 0, alpha=0.35, color="crimson")
        path = self.output / "stock_plot.png"
        figure.tight_layout()
        figure.savefig(path, dpi=150)
        plt.close(figure)
        return str(path)
