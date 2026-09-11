from enum import Enum, IntEnum
import os
import numpy as np
import yfinance as yf
import pandas as pd
from typing import Any, Dict, Annotated
from datetime import datetime
from .const import WORK_DIR, BACKTEST_RESULTS_FILE, BACKTEST_METRICS_FILE, DATASET_STOCK
from .datamodels import SignalModel, BacktestPerformanceMetrics


class StockDataHandler:
    def __init__(
        self, ticker: str, start_date: str, end_date: str, data_file_path: str
    ):
        self.ticker = ticker
        self.start_date = start_date
        self.end_date = end_date
        self.data_file_path = data_file_path
        self.data = None

    def fetch_data(self) -> Dict[str, Any]:
        self.data = yf.download(self.ticker, start=self.start_date, end=self.end_date)
        return self.data.to_dict()

    def save_data_to_csv(self) -> str:
        df = pd.DataFrame.from_dict(self.data)
        df["Date"] = df.index
        df.to_csv(self.data_file_path, index=False)
        return f'Data saved to "{self.data_file_path}"'

    def load_data_from_csv(self) -> Dict[str, Any]:
        df = pd.read_csv(self.data_file_path)
        self.data = df
        return df.to_dict()

    def get_data(self) -> Dict[str, Any]:
        if os.path.exists(self.data_file_path):
            return self.load_data_from_csv()
        else:
            self.fetch_data()
            self.save_data_to_csv()
            return self.data.to_dict()


class SignalGenerator:
    def __init__(self, data: Dict[str, Any]):
        self.data = data

    def generate_signals_model(self) -> SignalModel:
        df = pd.DataFrame.from_dict(self.data)
        return SignalModel(
            BuySignal=df["BuySignal"].tolist(),
            SellSignal=df["SellSignal"].tolist(),
            Description=df["Description"].iloc[0],
        )


class PerformanceMetricsCalculator:
    @staticmethod
    def calculate_cagr(start_value: float, end_value: float, periods: float) -> float:
        return (end_value / start_value) ** (1 / periods) - 1

    @staticmethod
    def calculate_mdd(cumulative_returns: pd.Series, positions: pd.Series) -> float:
        active_returns = cumulative_returns[positions.shift(1) != 0]
        drawdown = active_returns / active_returns.cummax() - 1
        return drawdown.min()

    @staticmethod
    def calculate_sharpe_ratio(
        returns: pd.Series,
        positions: pd.Series,
        risk_free_rate: float,
        period: str = "daily",
    ) -> float:
        active_returns = returns[positions != 0]
        if active_returns.empty:
            return 0
        std_dev = active_returns.std()
        if std_dev == 0:
            return 0
        if period == "daily":
            adjusted_risk_free_rate = risk_free_rate / 252
            sharpe_ratio = (active_returns.mean() - adjusted_risk_free_rate) / std_dev
        elif period == "yearly":
            sharpe_ratio = ((active_returns.mean() - risk_free_rate) / std_dev) * (
                252**0.5
            )
        else:
            raise ValueError(f"Unsupported period: {period}. Use 'daily' or 'yearly'.")
        return sharpe_ratio


# Define the Position Enum
class Position(IntEnum):
    BUY = 1
    SELL = 2
    HOLD = 3
    NO_HOLD = 4


class Backtester:
    def __init__(self, data: Dict[str, Any], signals: SignalModel):
        self.data = pd.DataFrame.from_dict(data)
        self.signals = signals
        self.results = None

    def backtest_strategy_perf(self) -> BacktestPerformanceMetrics:
        # Step 1: Initialize Buy and Sell Signals
        self.data["BuySignal"] = pd.Series(self.signals.BuySignal).astype(int)
        self.data["SellSignal"] = pd.Series(self.signals.SellSignal).astype(int)

        # Step 2: Define HoldSignal
        # If buy signal, hold, if sell signal, no hold
        # If same buy signal as previous day, hold
        # If same sell signal as previous day, no hold
        # If no buy or sell signal, hold
        self.data["HoldSignal"] = np.where(
            (self.data["BuySignal"] == 0) & (self.data["SellSignal"] == 0),
            Position.HOLD,
            np.where(
                (self.data["BuySignal"] == 1)
                & (self.data["BuySignal"].shift(1, fill_value=0) == 1),
                Position.HOLD,
                np.where(
                    (self.data["SellSignal"] == 1)
                    & (self.data["SellSignal"].shift(1, fill_value=0) == 1),
                    Position.NO_HOLD,
                    np.where(
                        self.data["BuySignal"] == 1, Position.HOLD, Position.NO_HOLD
                    ),
                ),
            ),
        )

        # Step 3: Initialize columns for valid sells and positions
        self.data["ValidSell"] = False
        self.data["ValidHold"] = False
        buy_occurred = False

        # Determine sell and hold can establish when buy signal occurred before.
        # If there is no buy signal before a sell signal, it is not a valid sell
        # If there is a buy signal before a hold signal, it is a valid hold
        for i in range(len(self.data)):
            if self.data.loc[i, "BuySignal"] == 1:
                buy_occurred = True  # A buy has occurred
                continue
            if self.data.loc[i, "SellSignal"] == 1 and buy_occurred:
                self.data.loc[i, "ValidSell"] = True  # Valid sell
                buy_occurred = False  # Reset after valid sell
            if self.data.loc[i, "HoldSignal"] == Position.HOLD and buy_occurred:
                self.data.loc[i, "ValidHold"] = True  # Valid hold

        # Step 4: Calculate Position
        self.data["Position"] = np.where(
            (self.data["HoldSignal"] == Position.HOLD) & (self.data["ValidHold"] == True),
            Position.HOLD,
            np.where(
                self.data["BuySignal"] == 1,
                Position.BUY,
                np.where(
                    (self.data["SellSignal"] == 1) & (self.data["ValidSell"] == True),
                    Position.SELL,
                    Position.NO_HOLD,
                ),
            ),
        )

        # Step 5: Calculate raw returns based on adjusted close prices
        self.data["Returns"] = self.data["Adj Close"].ffill().pct_change().fillna(0)

        # Step 6: Shift positions for returns calculation
        # Investment stock for current date is determined by previous date's position
        self.data["Adjusted Position"] = self.data["Position"].shift(1).fillna(0)

        # Step 7: Shift close prices for returns calculation
        self.data["Close(PrevDay)"] = self.data["Close"].shift(1)

        # fix: ("unsupported operand type(s) for /: 'float' and 'str'",)
        self.data["Open"] = pd.to_numeric(self.data["Open"], errors='coerce')
        self.data["Close(PrevDay)"] = pd.to_numeric(self.data["Close(PrevDay)"], errors='coerce')

        # Step 8: Calculate adjusted returns
        self.data["Adjusted Returns"] = np.where(
            self.data["Adjusted Position"] == Position.NO_HOLD,
            0,
            np.where(
                self.data["Adjusted Position"] == Position.SELL,
                # When a signal to sell is generated, sell at the open price
                # Therefore, returns are calculated as (Open / Close(PrevDay)) - 1
                (self.data["Open"] / self.data["Close(PrevDay)"] - 1).fillna(0),
                np.where(
                    (self.data["Adjusted Position"] == Position.BUY)
                    | (self.data["Adjusted Position"] == Position.HOLD),
                    # When a signal to buy is generated, or when holding, returns are same as daily returns
                    self.data["Returns"],
                    0,  # Default
                ),
            ),
        )

        cumulative_returns = (1 + self.data["Adjusted Returns"]).cumprod().fillna(1)
        self.data["Cumulative Returns"] = cumulative_returns

        cumulative_max = cumulative_returns.cummax()
        drawdown = (cumulative_max - cumulative_returns) / cumulative_max
        mdd_series = drawdown.cummax()
        self.data["MDD"] = mdd_series
        mdd = drawdown.max()

        start_value = cumulative_returns.iloc[0]
        end_value = cumulative_returns.iloc[-1]
        periods = len(cumulative_returns) / 252

        # calculate cumulative return by start and end value
        perf_cumulative_returns = (end_value / start_value) - 1
        positions = pd.Series(self.data["Adjusted Position"])
        returns = pd.Series(self.data["Adjusted Returns"])

        cagr = PerformanceMetricsCalculator.calculate_cagr(
            start_value, end_value, periods
        )
        mdd = PerformanceMetricsCalculator.calculate_mdd(cumulative_returns, positions)
        sharpe = PerformanceMetricsCalculator.calculate_sharpe_ratio(
            returns, positions, risk_free_rate=0.02, period="daily"
        )

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        backtest_results_file_path = os.path.join(WORK_DIR, BACKTEST_RESULTS_FILE)
        self.data.to_excel(backtest_results_file_path, index=False)

        backtest_metrics_file_path = os.path.join(WORK_DIR, BACKTEST_METRICS_FILE)
        with open(backtest_metrics_file_path, "w") as f:
            f.write(f"Backtest Results {timestamp_str}\n")
            f.write(f"Start Value: {start_value:.2f}\n")
            f.write(f"End Value: {end_value:.2f}\n")
            f.write(f"Cumulative Return: {perf_cumulative_returns:.2%}\n")
            f.write(f"CAGR: {cagr:.2%}\n")
            f.write(f"MDD: {mdd:.2%}\n")
            f.write(f"Sharpe Ratio: {sharpe:.2f}\n")

        self.results = BacktestPerformanceMetrics(
            cumulative_return=f"Cumulative Return: {perf_cumulative_returns:.2%}",
            cagr=f"CAGR: {cagr:.2%}",
            mdd=f"MDD: {mdd:.2%}",
            sharpe_ratio=f"Sharpe Ratio: {sharpe:.2f}",
        )
        return self.results


def fetch_stock_data(
    ticker: Annotated[str, "Stock symbol to fetch data for"] = "MSFT",
    start_date: Annotated[str, "Start date in format YYYY-MM-DD"] = "2020-01-01",
    end_date: Annotated[
        str, "End date in format YYYY-MM-DD"
    ] = datetime.today().strftime("%Y-%m-%d"),
    data_file_path: Annotated[str, "File path to store/load data"] = DATASET_STOCK,
) -> str:
    handler = StockDataHandler(ticker, start_date, end_date, data_file_path)
    data = handler.get_data()
    return f"Stock data loaded from {data_file_path} with {len(data['Close'])} records."


def fetch_stock_signals(file_path: str) -> SignalModel:
    handler = StockDataHandler("", "", "", file_path)
    data = handler.load_data_from_csv()
    generator = SignalGenerator(data)
    return generator.generate_signals_model()


def backtest_stock_strategy(
    stock_price_file_path: Annotated[str, "a file path of Stock price data"],
    stock_signals_file_path: Annotated[str, "a file path of Stock signal data"],
) -> BacktestPerformanceMetrics:
    try:
        price_handler = StockDataHandler("", "", "", stock_price_file_path)
        price_dict = price_handler.load_data_from_csv()
    except Exception as e:
        return f"Error loading stock price data: {e}"

    try:
        signals_handler = StockDataHandler("", "", "", stock_signals_file_path)
        signals_dict = signals_handler.load_data_from_csv()
    except Exception as e:
        return f"Error loading stock signals data: {e}"

    try:
        generator = SignalGenerator(signals_dict)
        signals = generator.generate_signals_model()
    except Exception as e:
        return f"Error generating signals: {e}"

    try:
        backtester = Backtester(price_dict, signals)
        return backtester.backtest_strategy_perf()
    except Exception as e:
        return f"Error during backtesting: {e}"
