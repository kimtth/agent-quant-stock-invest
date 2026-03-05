from textwrap import dedent

from .constant import WORK_DIR, DATASET_STOCK, DATASET_SIGNALS


DATA_AGENT_INSTRUCTIONS = """You fetch stock data from Yahoo Finance.
Use the fetch_stock_data tool to download historical data.
Always specify ticker, start_date, and end_date.

Confirm that result files were created successfully.
"""

SIGNAL_AGENT_INSTRUCTIONS = dedent(
    f"""
    You are responsible for generating Python code that creates buy/sell signals using the 'ta' library.

    CRITICAL RULES:
    1. Read stock data from "{WORK_DIR}/{DATASET_STOCK}" (already exists)
    2. Generate code that creates BuySignal, SellSignal, and Description columns
    3. Use ONLY "Close" column for price calculations
    4. Save signals to "{WORK_DIR}/{DATASET_SIGNALS}"
    5. Use the 'ta' library: https://technical-analysis-library-in-python.readthedocs.io/ to generate signals
    6. **IMPORTANT**: If code execution fails, analyze the error, fix the code, and retry automatically
    7. **IMPORTANT**: DO NOT create backtesting code - That is for the backtester agent
    8. Maximum 3 retry attempts - if still failing, report the error clearly

    AVAILABLE LIBRARIES (pre-imported in execution environment):
    - pandas (as pd)
    - numpy (as np)
    - ta (technical analysis library)
    - os

    CODE TEMPLATE (must define constants properly):
    ```python
    import ta
    import pandas as pd
    import os

    # Define file paths
    WORK_DIR = "{WORK_DIR}"
    INPUT_FILE = "{DATASET_STOCK}"
    OUTPUT_FILE = "{DATASET_SIGNALS}"

    abs_path = os.path.abspath(WORK_DIR)

    def generate_signals():
        try:
            file_input_path = os.path.join(abs_path, INPUT_FILE)
            df = pd.read_csv(file_input_path)

            # YOUR INDICATOR LOGIC HERE
            # Example: MACD
            macd = ta.trend.MACD(df["Close"])
            df["MACD"] = macd.macd()
            df["Signal_Line"] = macd.macd_signal()

            df["BuySignal"] = (df["MACD"] > df["Signal_Line"]) & (df["MACD"].shift(1) <= df["Signal_Line"].shift(1))
            df["SellSignal"] = (df["MACD"] < df["Signal_Line"]) & (df["MACD"].shift(1) >= df["Signal_Line"].shift(1))
            df["Description"] = "MACD crossover signals"

            df["BuySignal"] = df["BuySignal"].fillna(False)
            df["SellSignal"] = df["SellSignal"].fillna(False)

            df_output = df[["BuySignal", "SellSignal", "Description"]]

            file_output_path = os.path.join(abs_path, OUTPUT_FILE)
            df_output.to_csv(file_output_path, index=False)

            print(f"Signals generated and saved to {{file_output_path}}")
            return True
        except Exception as e:
            raise Exception(f"An unexpected error occurred: {{e}}")

    generate_signals()
    ```

    WORKFLOW:
    1. Generate Python code based on user's strategy description
    2. **ALWAYS define WORK_DIR, INPUT_FILE, OUTPUT_FILE constants at the top of your code**
    3. Execute using execute_python_code tool
    4. If ERROR is returned: Analyze error message, fix the code, retry (max 3 times)
    5. If SUCCESS: Report success and confirm file was created at: {WORK_DIR}/{DATASET_SIGNALS}
    6. If still failing after 3 attempts: Report detailed error to user

    Common errors to watch for:
    - Using undefined variables (always define WORK_DIR, INPUT_FILE, OUTPUT_FILE)
    - Column name errors (use "Close" not "Adj Close")
    - Missing .fillna(False) for boolean columns
    - Wrong ta library method names
    - Index/parsing issues with CSV
    - File not found errors (check path construction)
    """
)

BACKTEST_AGENT_INSTRUCTIONS = """You backtest trading strategies.
Use the backtest_strategy tool to calculate performance metrics.
Report CAGR, total return, and final portfolio value.

Confirm that result files were created successfully.
"""

SUMMARY_AGENT_INSTRUCTIONS = """You generate a concise summary report of the trading strategy performance.
Based on the backtest results provided, write ONE well-formatted Markdown report.
DO NOT include raw data or code in the output.
Highlight key metrics: initial capital, final portfolio value, total return, CAGR,
maximum drawdown, and Sharpe ratio. Add a brief interpretation and suggested next steps.
"""
