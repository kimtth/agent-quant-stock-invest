import os
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


class Backtester:
    def __init__(self, data: Dict[str, Any], signals: SignalModel):
        self.data = pd.DataFrame.from_dict(data)
        self.signals = signals
        self.results = None

    def backtest_strategy_perf(self) -> BacktestPerformanceMetrics:
        self.data["BuySignal"] = pd.Series(self.signals.BuySignal)
        self.data["SellSignal"] = pd.Series(self.signals.SellSignal)
        self.data["Position"] = self.data["BuySignal"].astype(int) - self.data[
            "SellSignal"
        ].astype(int)

        positions = pd.Series(self.data["Position"])
        returns = pd.Series(self.data["Adj Close"]).pct_change()
        self.data["Returns"] = returns

        # Calculate adjusted returns
        # Position = 1 (buy) - 0 (no sell) = 1 (hold position)
        # Position = 0 (no buy) - 1 (sell) = -1 (sell position or close position)
        # Position = 0 (no buy) - 0 (no sell) = 0 (no position)

        # Position = 1: Buy signal, so return is as is
        # Position = -1: Sell signal, returns are inverted (negative). 
        #   Selling a stock means you make a profit when the price goes down, and a loss when it goes up.
        # Position = 0: No trade, so return is 0
        # The `shift(1)` operation is used to apply the previous day's position to the current day's return.
        
        # Calculate adjusted returns
        self.data["Adjusted Position"] = self.data["Position"].shift(1).fillna(0)
        self.data["Adjusted Returns"] = self.data["Returns"] * self.data["Adjusted Position"]

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
    price_handler = StockDataHandler("", "", "", stock_price_file_path)
    price_dict = price_handler.load_data_from_csv()
    signals_handler = StockDataHandler("", "", "", stock_signals_file_path)
    signals_dict = signals_handler.load_data_from_csv()
    generator = SignalGenerator(signals_dict)
    signals = generator.generate_signals_model()
    backtester = Backtester(price_dict, signals)
    return backtester.backtest_strategy_perf()
