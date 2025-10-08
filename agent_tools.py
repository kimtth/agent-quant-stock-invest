import os
import sys
import traceback
from io import StringIO
from typing import Annotated

import numpy as np
import pandas as pd
from pydantic import Field
# from agent_framework import ai_function > Do not use this annotation when tools are defined in class.

from constant import (
    WORK_DIR,
    DATASET_STOCK,
    DATASET_SIGNALS,
    BACKTEST_RESULTS_FILE,
    BACKTEST_METRICS_FILE,
)


class AgentQuantTools:
    """Collection of AI function tools for quantitative trading analysis."""

    def __init__(self) -> None:
        # Ensure working directory exists
        os.makedirs(WORK_DIR, exist_ok=True)

    def fetch_stock_data(
        self,
        ticker: Annotated[
            str, Field(description="Stock ticker symbol (e.g., MSFT, AAPL)")
        ],
        start_date: Annotated[
            str, Field(description="Start date in YYYY-MM-DD format")
        ],
        end_date: Annotated[str, Field(description="End date in YYYY-MM-DD format")],
    ) -> str:
        """
        Fetch historical stock data from Yahoo Finance and save to CSV.

        Args:
            ticker: Stock ticker symbol
            start_date: Start date for data retrieval
            end_date: End date for data retrieval

        Returns:
            str: Status message indicating success or failure
        """
        try:
            import yfinance as yf

            output_path = os.path.join(WORK_DIR, DATASET_STOCK)
            df = yf.download(
                ticker, start=start_date, end=end_date, progress=False, auto_adjust=True
            )

            if df.empty:
                return f"ERROR: No data found for {ticker} between {start_date} and {end_date}"
            else:
                df.to_csv(output_path)
                self._clean_stock_data(output_path)

            return (
                f"SUCCESS: Fetched {len(df)} rows for {ticker}. Saved to {output_path}"
            )
        except Exception as e:
            return f"ERROR: {str(e)}\n{traceback.format_exc()}"
    
    def _clean_stock_data(self, input_path: str) -> str:
        """
        Clean and reformat stock data CSV file.

        This function reads the input CSV, performs cleaning operations such as
        handling missing values, ensuring correct data types, and saves the cleaned
        data to the specified output file.

        Returns:
            str: Status message indicating success or failure
        """
        try:
            output_path = os.path.join(WORK_DIR, DATASET_STOCK)

            if not os.path.exists(input_path):
                return f"ERROR: Input file {input_path} does not exist."

            df = pd.read_csv(input_path, parse_dates=True)

            df.drop(index=[df.index[0], df.index[1]], inplace=True)
            df.dropna(inplace=True)  # Remove rows with missing values
            df.reset_index(inplace=True)
            df.rename(columns={"Price": "Date"}, inplace=True)
            
            expected_cols = ["Open", "High", "Low", "Close", "Volume"]
            # Keep only available expected cols in that order
            available_expected = [c for c in expected_cols if c in df.columns]
            df = df[["Date"] + available_expected]

            df.to_csv(output_path, index=False)
            return f"SUCCESS: Cleaned data saved to {output_path}."
        except Exception as e:
            return f"ERROR: {str(e)}"

    def execute_python_code(
        self,
        code: Annotated[
            str, Field(description="Python code to execute for generating signals")
        ],
    ) -> str:
        """
        Execute Python code to generate buy/sell signals.

        The code should read from stock_data.csv and write to stock_signals.csv.
        If execution fails, returns detailed error message so agent can fix the code and retry.

        Available libraries in execution environment:
        - pandas (as pd)
        - numpy (as np)
        - ta (technical analysis library)
        - os

        Args:
            code: Python code string to execute

        Returns:
            str: Execution status and any output or error details
        """
        try:
            # Import libraries that will be available in the execution environment
            try:
                import ta
            except ImportError:
                return "ERROR: 'ta' library not installed. Run: pip install ta"

            # Ensure directory exists
            os.makedirs(WORK_DIR, exist_ok=True)
            
            # Verify input file exists (WORK_DIR is already absolute)
            input_path = os.path.join(WORK_DIR, DATASET_STOCK)
            if not os.path.exists(input_path):
                return f"ERROR: Input file not found: {input_path}\nPlease run fetch_stock_data first."

            # Capture stdout
            old_stdout = sys.stdout
            sys.stdout = captured_output = StringIO()

            # Create execution environment with pre-imported libraries
            exec_globals = {
                "__builtins__": __builtins__,
                "os": os,
                "pd": pd,
                "pandas": pd,
                "np": np,
                "numpy": np,
                "ta": ta,
                "WORK_DIR": WORK_DIR,
                "INPUT_FILE": DATASET_STOCK,
                "OUTPUT_FILE": DATASET_SIGNALS,
            }

            # Execute the code
            exec(code, exec_globals)

            # Restore stdout
            sys.stdout = old_stdout
            output = captured_output.getvalue()

            # Check if output file was created
            output_path = os.path.join(WORK_DIR, DATASET_SIGNALS)
            if os.path.exists(output_path):
                # Verify file has content
                file_size = os.path.getsize(output_path)
                if file_size == 0:
                    return f"ERROR: {output_path} was created but is empty"
                
                signals_df = pd.read_csv(output_path)
                buy_count = (
                    signals_df["BuySignal"].sum()
                    if "BuySignal" in signals_df.columns
                    else 0
                )
                sell_count = (
                    signals_df["SellSignal"].sum()
                    if "SellSignal" in signals_df.columns
                    else 0
                )

                result = "SUCCESS: Code executed successfully.\n"
                result += f"Generated {buy_count} buy signals and {sell_count} sell signals.\n"
                result += f"Saved to {output_path} ({file_size} bytes)\n"
                if output:
                    result += f"Output: {output}"
                return result
            else:
                return f"ERROR: Code executed but {output_path} was not created.\nOutput: {output}"

        except Exception as e:
            sys.stdout = old_stdout
            # Return detailed error with traceback so agent can fix the code
            error_details = traceback.format_exc()
            return f"ERROR: Code execution failed.\n\nError: {str(e)}\n\nFull traceback:\n{error_details}\n\nPlease fix the code and try again."

    def backtest_strategy(
        self,
        initial_capital: Annotated[
            float, Field(description="Initial investment capital")
        ] = 10000.0,
    ) -> str:
        """
        Backtest a trading strategy and calculate performance metrics.

        Reads stock data and signals, simulates trading, calculates CAGR, MDD, Sharpe.
        Implements proper position tracking with BUY, SELL, HOLD, and NO_HOLD states.

        Args:
            initial_capital: Starting investment amount

        Returns:
            str: Summary of performance metrics including CAGR, MDD, Sharpe Ratio
        """
        try:
            from datetime import datetime

            stock_path = os.path.join(WORK_DIR, DATASET_STOCK)
            signals_path = os.path.join(WORK_DIR, DATASET_SIGNALS)
            output_path = os.path.join(WORK_DIR, BACKTEST_RESULTS_FILE)
            metrics_path = os.path.join(WORK_DIR, BACKTEST_METRICS_FILE)

            # Check if files exist and provide helpful error message
            if not os.path.exists(stock_path):
                return f"ERROR: Stock data file not found at: {stock_path}\nPlease run fetch_stock_data first."
            
            if not os.path.exists(signals_path):
                return f"ERROR: Signals file not found at: {signals_path}\nPlease run generate_signals first."

            # Read data
            stock_df = pd.read_csv(stock_path, parse_dates=True)
            signals_df = pd.read_csv(signals_path, parse_dates=True)

            # Merge stock data with signals
            df = stock_df.join(signals_df[["BuySignal", "SellSignal"]])

            # Convert signals to integers
            df["BuySignal"] = df["BuySignal"].astype(int)
            df["SellSignal"] = df["SellSignal"].astype(int)

            # Define Position States
            POSITION_BUY = 1
            POSITION_SELL = 2
            POSITION_HOLD = 3
            POSITION_NO_HOLD = 4

            # Step 1: Define HoldSignal logic
            df["HoldSignal"] = np.where(
                (df["BuySignal"] == 0) & (df["SellSignal"] == 0),
                POSITION_HOLD,
                np.where(
                    (df["BuySignal"] == 1)
                    & (df["BuySignal"].shift(1, fill_value=0) == 1),
                    POSITION_HOLD,
                    np.where(
                        (df["SellSignal"] == 1)
                        & (df["SellSignal"].shift(1, fill_value=0) == 1),
                        POSITION_NO_HOLD,
                        np.where(df["BuySignal"] == 1, POSITION_HOLD, POSITION_NO_HOLD),
                    ),
                ),
            )

            # Step 2: Determine valid sells and holds
            df["ValidSell"] = False
            df["ValidHold"] = False
            buy_occurred = False

            for i in range(len(df)):
                if df["BuySignal"].iloc[i] == 1:
                    buy_occurred = True
                    continue
                if df["SellSignal"].iloc[i] == 1 and buy_occurred:
                    df.loc[df.index[i], "ValidSell"] = True
                    buy_occurred = False
                if df["HoldSignal"].iloc[i] == POSITION_HOLD and buy_occurred:
                    df.loc[df.index[i], "ValidHold"] = True

            # Step 3: Calculate Position
            df["Position"] = np.where(
                # (df["ValidHold"]) eq. (df["ValidHold"] == True)
                (df["HoldSignal"] == POSITION_HOLD) & (df["ValidHold"]),
                POSITION_HOLD,
                np.where(
                    df["BuySignal"] == 1,
                    POSITION_BUY,
                    np.where(
                        (df["SellSignal"] == 1) & (df["ValidSell"]),
                        POSITION_SELL,
                        POSITION_NO_HOLD,
                    ),
                ),
            )

            # Step 4: Calculate returns
            df["Returns"] = df["Close"].ffill().pct_change().fillna(0)

            # Step 5: Shift positions for returns calculation
            df["Adjusted Position"] = df["Position"].shift(1).fillna(0)

            # Step 6: Calculate previous day close
            df["Close(PrevDay)"] = df["Close"].shift(1)

            # Ensure numeric types
            df["Open"] = pd.to_numeric(df["Open"], errors="coerce")
            df["Close(PrevDay)"] = pd.to_numeric(df["Close(PrevDay)"], errors="coerce")

            # Step 7: Calculate adjusted returns based on position
            df["Adjusted Returns"] = np.where(
                df["Adjusted Position"] == POSITION_NO_HOLD,
                0,
                np.where(
                    df["Adjusted Position"] == POSITION_SELL,
                    # Sell at open price
                    (df["Open"] / df["Close(PrevDay)"] - 1).fillna(0),
                    np.where(
                        (df["Adjusted Position"] == POSITION_BUY)
                        | (df["Adjusted Position"] == POSITION_HOLD),
                        # Buy or hold: use daily returns
                        df["Returns"],
                        0,
                    ),
                ),
            )

            # Step 8: Calculate cumulative returns
            cumulative_returns = (1 + df["Adjusted Returns"]).cumprod().fillna(1)
            df["Cumulative Returns"] = cumulative_returns

            # Step 9: Calculate Maximum Drawdown using PerformanceMetricsCalculator
            cumulative_max = cumulative_returns.cummax()
            drawdown = (cumulative_max - cumulative_returns) / cumulative_max
            mdd_series = drawdown.cummax()
            df["MDD"] = mdd_series

            # Step 10: Calculate performance metrics using PerformanceMetricsCalculator
            start_value = cumulative_returns.iloc[0]
            end_value = cumulative_returns.iloc[-1]
            periods = len(cumulative_returns) / 252  # Trading days per year

            # Cumulative return
            perf_cumulative_returns = (end_value / start_value) - 1

            # Use PerformanceMetricsCalculator for metrics
            positions = pd.Series(df["Adjusted Position"])
            returns = pd.Series(df["Adjusted Returns"])

            cagr = PerformanceMetricsCalculator.calculate_cagr(
                start_value, end_value, periods
            )
            mdd = PerformanceMetricsCalculator.calculate_mdd(
                cumulative_returns, positions
            )
            sharpe = PerformanceMetricsCalculator.calculate_sharpe_ratio(
                returns, positions, risk_free_rate=0.02, period="daily"
            )

            # Step 11: Calculate final portfolio value
            final_value = initial_capital * end_value
            total_return = (final_value - initial_capital) / initial_capital * 100

            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Save results
            df.to_excel(output_path, index=True)
            
            # Verify file was written
            if not os.path.exists(output_path):
                return f"ERROR: Failed to write backtest results to {output_path}"

            # Prepare metrics
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            metrics = {
                "Start Value": f"${initial_capital:,.2f}",
                "End Value": f"${final_value:,.2f}",
                "Total Return": f"{total_return:.2f}%",
                "Cumulative Return": f"{perf_cumulative_returns:.2%}",
                "CAGR": f"{cagr:.2%}",
                "MDD": f"{mdd:.2%}",
                "Sharpe Ratio": f"{sharpe:.2f}",
            }

            metrics_text = "\n".join([f"{k}: {v}" for k, v in metrics.items()])

            with open(metrics_path, "w", encoding="utf-8") as f:
                f.write(f"Backtest Results {timestamp_str}\n")
                f.write("=" * 40 + "\n")
                f.write(metrics_text)
            
            # Verify metrics file
            if not os.path.exists(metrics_path):
                return f"ERROR: Failed to write metrics to {metrics_path}"
            
            results_size = os.path.getsize(output_path)
            metrics_size = os.path.getsize(metrics_path)
            
            return f"SUCCESS: Backtest complete.\n\nFiles saved:\n- {output_path} ({results_size} bytes)\n- {metrics_path} ({metrics_size} bytes)\n\n{metrics_text}"
        except Exception as e:
            error_details = traceback.format_exc()
            return f"ERROR: {str(e)}\n\nFull traceback:\n{error_details}"

    def abs_path_hint(self) -> str:
        """
        Get the absolute path of the working directory.

        Returns:
            str: Absolute path of the working directory
        """
        # WORK_DIR is already absolute
        return WORK_DIR


class PerformanceMetricsCalculator:
    """Calculator for trading strategy performance metrics."""

    @staticmethod
    def calculate_cagr(start_value: float, end_value: float, periods: float) -> float:
        """
        Calculate Compound Annual Growth Rate (CAGR).

        Args:
            start_value: Starting portfolio value
            end_value: Ending portfolio value
            periods: Number of years

        Returns:
            float: CAGR as a decimal (e.g., 0.15 for 15%)
        """
        if periods <= 0 or start_value <= 0:
            return 0.0
        return (end_value / start_value) ** (1 / periods) - 1

    @staticmethod
    def calculate_mdd(cumulative_returns: pd.Series, positions: pd.Series) -> float:
        """
        Calculate Maximum Drawdown (MDD).

        Args:
            cumulative_returns: Series of cumulative returns
            positions: Series of position states

        Returns:
            float: Maximum drawdown as a decimal (e.g., 0.20 for 20%)
        """
        active_returns = cumulative_returns[positions.shift(1) != 0]
        if active_returns.empty:
            return 0.0
        drawdown = active_returns / active_returns.cummax() - 1
        return abs(drawdown.min())

    @staticmethod
    def calculate_sharpe_ratio(
        returns: pd.Series,
        positions: pd.Series,
        risk_free_rate: float,
        period: str = "daily",
    ) -> float:
        """
        Calculate Sharpe Ratio.

        Args:
            returns: Series of returns
            positions: Series of position states
            risk_free_rate: Annual risk-free rate (e.g., 0.02 for 2%)
            period: Either 'daily' or 'yearly'

        Returns:
            float: Sharpe ratio
        """
        active_returns = returns[positions != 0]
        if active_returns.empty:
            return 0.0

        std_dev = active_returns.std()
        if std_dev == 0:
            return 0.0

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
