import os
from textwrap import dedent
from pydantic import BaseModel, field_validator
from typing import List, Optional


class Settings(BaseModel):
    work_dir: str = "_output"
    backtest_results_file: str = "backtest_results.xlsx"
    backtest_metrics_file: str = "backtest_metrics.txt"
    dataset_stock: str = "stock_data.csv"
    dataset_signals: str = "stock_signals.csv"
    llm_model_names: Optional[List[str]] = os.getenv("MODEL_NAMES")

    @field_validator("llm_model_names")
    def split_model_names(cls, v):
        if isinstance(v, str):
            return v.split(",")
        return v


settings = Settings()

WORK_DIR = settings.work_dir
BACKTEST_RESULTS_FILE = settings.backtest_results_file
BACKTEST_METRICS_FILE = settings.backtest_metrics_file
DATASET_STOCK = settings.dataset_stock
DATASET_SIGNALS = settings.dataset_signals
MODEL_NAMES = settings.llm_model_names
SUMMARY_PROMPT = dedent(
    """
        # Task
        - Return the performance metrics based on the backtesting results.
        - Add a brief summary of the strategy and indicators used.
        - Do not include duplicates information in the summary.
        - The performance metrics should include the following:
            Cumulative return, CAGR, MDD, and Sharpe Ratio.
        - Desired output should be markdown.

        # Desired output
            ### Strategy Performance Summary

            **Indicators Used:**
            - Moving Average (10-day)

            **Strategy Summary:**
            The 10-day Moving Average (MA) calculates the average price of the stock over the past 10 days. 
            It helps smooth price data to identify trends. 
            
            In this strategy, buy signals are generated when the stock price crosses above the 10-day MA (bullish), 
            and sell signals are triggered when the price crosses below the 10-day MA (bearish).

            This approach aims to capture momentum while managing risk through volatility adjustments.

            ### Performance Metrics

            | Metric              | Value    |
            |---------------------|----------|
            | **Cumulative Return**| 120%     |
            | **CAGR**             | 15.5%    |
            | **Maximum Drawdown** | -12.3%   |
            | **Sharpe Ratio**     | 1.34     |
        """
)
