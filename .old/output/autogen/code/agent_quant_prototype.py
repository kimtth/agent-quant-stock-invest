import os
import autogen
import yfinance as yf
import pandas as pd
from autogen.coding import LocalCommandLineCodeExecutor
from autogen import GroupChat, GroupChatManager, Agent
from datetime import datetime
from typing import Any, Dict, List, Literal, Annotated, Union
from pydantic import BaseModel
from textwrap import dedent
from utils.web_search import WebSearch
from dotenv import load_dotenv


class CustomBaseModel(BaseModel):
    class Config:
        arbitrary_types_allowed = True


# Model for stock signals
class SignalModel(CustomBaseModel):
    BuySignal: List[bool]
    SellSignal: List[bool]
    Description: str


class BacktestPerformanceMetrics(CustomBaseModel):
    cumulative_return: str
    cagr: str
    mdd: str
    sharpe_ratio: str


load_dotenv()

WORK_DIR = "_output"
BACKTEST_RESULTS_FILE = "backtest_results.xlsx"
BACKTEST_METRICS_FILE = "backtest_metrics.txt"
DATASET_STOCK = "stock_data.csv"
DATASET_SIGNALS = "stock_signals.csv"
# Load MODEL_NAMES, then generate model list by splitting the string by comma
MODEL_NAMES = os.getenv("MODEL_NAMES")
if MODEL_NAMES is not None:
    MODEL_NAMES = MODEL_NAMES.split(",")

config_file_path = os.path.join(os.path.dirname(__file__), "OAI_CONFIG_LIST.json")
config_list = autogen.config_list_from_json(
    config_file_path,
    filter_dict={
        "model": MODEL_NAMES,
    },
)

assert len(config_list) > 0
print("models to use: ", [config_list[i]["model"] for i in range(len(config_list))])

llm_config = {
    # https://microsoft.github.io/autogen/docs/Migration-Guide#migrating-to-02
    # https://microsoft.github.io/autogen/docs/FAQ/#handle-rate-limit-error-and-timeout-error
    # https://github.com/microsoft/autogen/issues/454
    "config_list": config_list,
    "cache_seed": 44,
    "temperature": 0.7,
    "timeout": 800,
    "max_retries": 8,
}

# **Functions for Tool Use**


# Function for fetching stock data using yfinance
def fetch_data(ticker: str, start_date: str, end_date: str) -> Dict[str, Any]:
    data = yf.download(ticker, start=start_date, end=end_date)
    return data.to_dict()


# Function for saving data to CSV
def save_data_to_csv(data: Dict[str, Any], file_path: str) -> str:
    df = pd.DataFrame.from_dict(data)
    df["Date"] = df.index
    df.to_csv(file_path, index=False)
    return f'Data saved to "{file_path}"'


# Function for loading data from CSV
def load_data_from_csv(file_path: str) -> Dict[str, Any]:
    df = pd.read_csv(file_path)
    return df.to_dict()


# Function for loading signal data from CSV
def generate_signals_model(data: Dict[str, Any]) -> SignalModel:
    df = pd.DataFrame.from_dict(data)
    return SignalModel(
        BuySignal=df["BuySignal"].tolist(),
        SellSignal=df["SellSignal"].tolist(),
        # get first value from the Description column
        Description=df["Description"].iloc[0],
    )


# Function for calculating CAGR
def calculate_cagr(start_value: float, end_value: float, periods: float) -> float:
    # def calculate_cagr(start_value: float, end_value: float, periods, postions: pd.Series) -> float:
    # Count the number of active periods (non-zero positions)
    # active_periods = (postions != 0).sum()
    # If no active periods, return 0 CAGR to avoid division by zero
    # if active_periods == 0:
    #     return 0
    # Calculate CAGR based on active periods
    return (end_value / start_value) ** (1 / periods) - 1


# Function for calculating Maximum Drawdown
def calculate_mdd(cumulative_returns: pd.Series, postions: pd.Series) -> float:
    # Filter out neutral positions (0), calculate MDD based on active positions
    active_returns = cumulative_returns[postions.shift(1) != 0]
    # Calculate drawdowns
    drawdown = active_returns / active_returns.cummax() - 1
    # Return the maximum drawdown (most negative value)
    return drawdown.min()


# Function for calculating Sharpe Ratio
def calculate_sharpe_ratio(
    returns: pd.Series,
    postions: pd.Series,
    risk_free_rate: float,
    period: str = "daily",
) -> float:
    # Filter out periods with neutral positions (position == 0)
    active_returns = returns[postions != 0]
    # If there are no active returns, return 0 (no Sharpe Ratio can be calculated)
    if active_returns.empty:
        return 0
    # Calculate the standard deviation of active returns
    std_dev = active_returns.std()
    # Return 0 if standard deviation is zero to avoid division by zero
    if std_dev == 0:
        return 0
    # Calculate Sharpe Ratio based on period
    if period == "daily":
        # Convert annual risk-free rate to daily
        adjusted_risk_free_rate = risk_free_rate / 252
        sharpe_ratio = (active_returns.mean() - adjusted_risk_free_rate) / std_dev
    elif period == "yearly":
        # Use annualized Sharpe Ratio with 252 trading days
        sharpe_ratio = ((active_returns.mean() - risk_free_rate) / std_dev) * (252**0.5)
    else:
        raise ValueError(f"Unsupported period: {period}. Use 'daily' or 'yearly'.")

    return sharpe_ratio


# Backtesting strategy based on buy/sell signals
def backtest_strategy_perf(
    data: Dict[str, Any], signals: SignalModel
) -> BacktestPerformanceMetrics:
    data = pd.DataFrame.from_dict(data)
    assert isinstance(data, pd.DataFrame)
    data["BuySignal"] = pd.Series(signals.BuySignal)
    data["SellSignal"] = pd.Series(signals.SellSignal)
    data["Position"] = data["BuySignal"].astype(int) - data["SellSignal"].astype(int)

    # The shift(1) method shifts the "Position" column down by one row.
    # This is done to align the position taken at the end of the previous day with the return of the current day.
    # The "Position" column indicates whether the strategy is in a buy (1), sell (-1), or neutral (0) position.
    # If the position is -1, the return is the inverse of the stock's return. If the position is 0, the return is zero.
    postions = pd.Series(data["Position"])
    
    # Calculate returns based on positions
    returns = pd.Series(data["Adj Close"]).pct_change()
    data["Returns"] = returns

    # Adjust returns based on position signals (shifting by 1 day to align position with returns)
    adjusted_returns = returns * data["Position"].shift(1).fillna(0)

    # For cash (Position = -1), returns should be neutral (0)
    adjusted_returns[data["Position"] == -1] = 0
    adjusted_returns[data["Position"] == 0] = 0
    data["Adjusted Returns"] = adjusted_returns
    
    # Calculate cumulative returns
    cumulative_returns = (1 + adjusted_returns).cumprod().fillna(1)
    data["Cumulative Returns"] = cumulative_returns
    
    # Calculate drawdown
    cumulative_max = cumulative_returns.cummax()
    drawdown  = (cumulative_max - cumulative_returns) / cumulative_max
    
    # Calculate MDD for each date
    mdd_series = drawdown.cummax()  # Maximum drawdown up to each date
    data["MDD"] = mdd_series
    mdd = drawdown.max() # Maximum drawdown over the period

    start_value = cumulative_returns.iloc[0]
    end_value = cumulative_returns.iloc[-1]
    periods = len(cumulative_returns) / 252  # Assuming 252 trading days in a year

    cagr = calculate_cagr(start_value, end_value, periods)
    mdd = calculate_mdd(cumulative_returns, postions)
    sharpe = calculate_sharpe_ratio(
        returns, postions, risk_free_rate=0.02, period="daily"
    )

    # Store data in a file
    timstamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    assert isinstance(data, pd.DataFrame)
    backtest_results_file_path = os.path.join(WORK_DIR, BACKTEST_RESULTS_FILE)
    data.to_excel(backtest_results_file_path, index=False)

    # Store calulated metrics in a file
    backtest_metrics_file_path = os.path.join(WORK_DIR, BACKTEST_METRICS_FILE)
    with open(backtest_metrics_file_path, "w") as f:
        f.write(f"Backtest Results {timstamp_str}\n")
        # Store start and end value, periods
        f.write(f"Start Value: {start_value:.2%}\n")
        f.write(f"End Value: {end_value:.2%}\n")
        f.write(f"Cumulative Return: {end_value:.2%}\n")
        f.write(f"CAGR: {cagr:.2%}\n")
        f.write(f"MDD: {mdd:.2%}\n")
        f.write(f"Sharpe Ratio: {sharpe:.2f}\n")

    return BacktestPerformanceMetrics(
        cumulative_return=f"Cumulative Return: {end_value:.2%}",
        cagr=f"CAGR: {cagr:.2%}",
        mdd=f"MDD: {mdd:.2%}",
        sharpe_ratio=f"Sharpe Ratio: {sharpe:.2f}",  # Include the Sharpe ratio
    )


def fetch_stock_data(
    ticker: Annotated[str, "Stock symbol to fetch data for"] = "MSFT",
    start_date: Annotated[str, "Start date in format YYYY-MM-DD"] = "2020-01-01",
    end_date: Annotated[
        str, "End date in format YYYY-MM-DD"
    ] = datetime.today().strftime("%Y-%m-%d"),
    data_file_path: Annotated[str, "File path to store/load data"] = DATASET_STOCK,
) -> str:
    if os.path.exists(data_file_path):
        data = load_data_from_csv(data_file_path)
    else:
        data = fetch_data(ticker, start_date, end_date)
        save_data_to_csv(data, data_file_path)
    return f"Stock data loaded from {data_file_path} with {len(data['Close'])} records."


def fetch_stock_signals(file_path: str) -> SignalModel:
    data = load_data_from_csv(file_path)
    signals = generate_signals_model(data)
    return SignalModel(
        BuySignal=signals["BuySignal"],
        SellSignal=signals["SellSignal"],
        Description=signals["Description"][0],
    )


def backtest_stock_strategy(
    stock_price_file_path: Annotated[str, "a file path of Stock price data"],
    stock_signals_file_path: Annotated[str, "a file path of Stock signal data"],
) -> BacktestPerformanceMetrics:
    price_dict = load_data_from_csv(stock_price_file_path)
    signals_dict = load_data_from_csv(stock_signals_file_path)
    signals = generate_signals_model(signals_dict)
    backtest_performance_metrics = backtest_strategy_perf(price_dict, signals)
    return backtest_performance_metrics


custom_signal_analysis_agent_prompt = dedent(
    f"""
    - You are responsible for using the `ta` library to create python code for generating buy and sell signals for the stock investing.
    - Do not create the code for stock data fetching. The `{DATASET_STOCK}` file will be provided by the `stock_analysis_agent`.
    - Do not execute the code. Provide the code to the `user_proxy` for execution.
    - Do not explain why the code is written in a specific way. Do not explain why.
    - Do not include the code for backtesting the strategy.
    - Create only python function `generate_signals`.  Do not create other function.
    - Include the columns `BuySignal`, `SellSignal`, and `Description` in the DataFrame.
    - Use the following code template for importing libraries and defining variables:  
        ```
        import ta
        import pandas as pd
        import os

        WORK_DIR = '.'
        INPUT_FILE = {DATASET_STOCK}
        OUTPUT_FILE = {DATASET_SIGNALS}

        abs_path = os.path.abspath(WORK_DIR)
        ```

    **Example 1:**

    - Input:
        Generate buy/sell signals using MACD and 10 days Moving Average.

    - Function:
        ```python
        import ta
        import pandas as pd
        import os   

        WORK_DIR = '.'
        INPUT_FILE = {DATASET_STOCK}
        OUTPUT_FILE = {DATASET_SIGNALS}

        abs_path = os.path.abspath(WORK_DIR)

        def generate_signals():
            try:
                file_input_path = os.path.join(abs_path, INPUT_FILE)
                df = pd.read_csv(file_input_path)

                df["MA10"] = ta.trend.sma_indicator(df["Adj Close"], window=10)
                df["MACD"] = ta.trend.MACD(df["Close"])
                df["BuySignal"] = (df["Adj Close"] > df["MA10"]) & (df["MACD"] > 0)
                df["SellSignal"] = (df["Adj Close"] < df["MA10"]) & (df["MACD"] < 0)
                df["Description"] = "Generated signals using MACD and Moving Average 10 days"

                df_output = df[["BuySignal", "SellSignal", "Description"]]

                file_output_path = os.path.join(abs_path, OUTPUT_FILE),
                df_output.to_csv(file_output_path, index=False)   

                print(f"Signals generated and saved to {{file_output_path}}")
            except Exception as e:
                print(f"An unexpected error occurred: {{e}}")
        
        generate_signals()
        ```
    """
)

stock_analysis_agent_prompt = dedent(
    f"""
    You are responsible for creating, analyzing, and processing stock data to generate insights.

    Tasks:
    1. Create the "{DATASET_STOCK}" file from available stock data. This file will not be provided, and you must generate it.
    - COMPLETE CONDITION: The "{DATASET_STOCK}" file exists in the 'WORK_DIR'.

    2. After the signals are created, use the "{DATASET_STOCK}" and "{DATASET_SIGNALS}" files to perform a backtest of the stock strategy.
    - Analyze the stock data and use the provided buy/sell signals to generate performance metrics.
    - Provide insights and metrics such as CAGR (Compound Annual Growth Rate), MDD (Maximum Drawdown), and cumulative returns.

    Reply TERMINATE when the task is done.
    """
)

user_proxy_prompt = dedent(
    f"""
    You are responsible for executing the Python code provided by other agents and accessing the data in the 'WORK_DIR'.

    Tasks:
    1. Execute the Python code from `custom_signal_analysis_agent` to generate the "{DATASET_SIGNALS}" file.
    - The code will generate buy/sell signals and save them in the "{DATASET_SIGNALS}" file in the 'WORK_DIR'.
    - If the code execution fails, retry executing the code.

    If the task is successful, reply TERMINATE. 
    If more steps are required, reply CONTINUE, or explain why the task has not been solved yet.
    """
)

# **Agent Configuration**

# 1. Create an AssistantAgent for stock analysis
stock_analysis_agent = autogen.AssistantAgent(
    name="stock_analysis_agent",
    system_message=stock_analysis_agent_prompt,
    llm_config=llm_config,
)


# 2. Create an AssistantAgent for ta library expert
custom_signal_analysis_agent = autogen.AssistantAgent(
    name="custom_signal_analysis_agent",
    system_message=custom_signal_analysis_agent_prompt,
    llm_config=llm_config,
)

# 3. Create a UserProxyAgent
user_proxy = autogen.UserProxyAgent(
    name="user_proxy",
    is_termination_msg=lambda x: x.get("content", "") is not None
    and x.get("content", "").rstrip().endswith("TERMINATE"),
    # "ALWAYS": "An attentive HUMAN user who can answer questions about the task, and can perform tasks such as running Python code or inputting command line commands at a Linux terminal and reporting back the execution results.",
    # "TERMINATE": "A user that can run Python code or input command line commands at a Linux terminal and report back the execution results.",
    # "NEVER": "A computer terminal that performs no other action than running Python scripts (provided to it quoted in ```python code blocks), or sh shell scripts (provided to it quoted in ```sh code blocks).",
    human_input_mode="NEVER",  # Literal['ALWAYS', 'TERMINATE', 'NEVER']
    max_consecutive_auto_reply=15,
    code_execution_config={
        "executor": LocalCommandLineCodeExecutor(
            work_dir=WORK_DIR, timeout=600, execution_policies={"python": True}
        ),
    },
    system_message=user_proxy_prompt,
)

# Customised message, this is always the first message in the context
speaker_select_msg_prompt = dedent(
    f"""
    You are a manager responsible for coordinating a group chat between three agents: `stock_analysis_agent`, `custom_signal_analysis_agent`, and `user_proxy`.

    Your role is to oversee the stock analysis workflow, which consists of the following tasks:
    1. Creating stock data ("{DATASET_STOCK}") using the `stock_analysis_agent`.
    2. Generating buy/sell signals code by coordinating the `custom_signal_analysis_agent` 
    3. Ensuring the `user_proxy` executes the provided code.
    4. Analyzing stock investing performance using both the stock data and signals, with the `stock_analysis_agent` conducting backtests and providing performance metrics.

    Your job is to ensure smooth communication between agents, keep the workflow on track, and monitor task completion. 
    Coordinate the agents so that each step is completed in sequence and the group chat remains efficient.
    """
)
# Customised prompt, this is always the last message in the context
speaker_select_prompt = dedent(
    """
    Read the above conversation.
    Select ONLY THE NAME of the next job role from agentlist to speak. Do not explain why.
    """
)


def custom_speaker_selection_func(
    last_speaker: Agent, groupchat: GroupChat
) -> Union[Agent, Literal["auto", "manual", "random", "round_robin"], None]:
    # https://microsoft.github.io/autogen/docs/topics/groupchat/customized_speaker_selection/
    """Define a customized speaker selection function.
    **Workflow:**

    - DO NOT call Step 2, without completing Step 1.
    - DO NOT call Step 3, without completing Step 1 and 2.
    - REPEAT the each step until the task meet COMPLETE CONDITION.

    **Step 1. Creation of "{DATASET_STOCK}"**:
        - Create the `{DATASET_STOCK}` file. the file will not be provided.
        - The `stock_analysis_agent` will create the `{DATASET_STOCK}`.
        - COMPLETE CONDITION: `{DATASET_STOCK}` exists in the 'WORK_DIR'.

    **Step 2. Creation of "{DATASET_SIGNALS}"**:
        - Create the `{DATASET_SIGNALS}` file. the file will not be provided.
        - The `custom_signal_analysis_agent` create the python code for buy and sell signals using the `ta` library.
        - The `user_proxy` should execute the python code provided by the `custom_signal_analysis_agent`.
        - The python code will generate signals and save them into the "{DATASET_SIGNALS}" file, including buy and sell signals, in the 'WORK_DIR'.
        - COMPLETE CONDITION: `{DATASET_SIGNALS}` exists in the 'WORK_DIR'.

    **Step 3. Stock Data Analysis**:
        - The `stock_analysis_agent` analyzes stock data and generates insights.
        - The `stock_analysis_agent` will use the "{DATASET_STOCK}" and "{DATASET_SIGNALS}" files in the 'WORK_DIR'.
        - The `stock_analysis_agent` will use the generated signals to backtest a strategy.
        - The `stock_analysis_agent` should provide performance metrics using the provided functions.
        - COMPLETE CONDITION: The `stock_analysis_agent` replies with the performance metrics.
    """
    stock_data_path = os.path.join(WORK_DIR, DATASET_STOCK)
    stock_signals_path = os.path.join(WORK_DIR, DATASET_SIGNALS)
    messages = groupchat.messages

    # Transition to `user_proxy` to execute the code provided by `custom_signal_analysis_agent`
    if last_speaker.name == "custom_signal_analysis_agent" and not os.path.exists(
        stock_signals_path
    ):
        return groupchat.agent_by_name("user_proxy")
    # Check if the user_proxy has executed the code successfully
    elif last_speaker.name == "user_proxy":
        # If the code execution failed, repeat the task by reassigning to `custom_signal_analysis_agent`
        if "exitcode: 1" in messages[-1]["content"]:
            return groupchat.agent_by_name("custom_signal_analysis_agent")
        elif not os.path.exists(stock_data_path):
            return groupchat.agent_by_name("stock_analysis_agent")
        else:
            return "auto"
    else:
        return "auto"


# https://microsoft.github.io/autogen/docs/tutorial/conversation-patterns#constrained-speaker-selection
allowed_transitions = {
    custom_signal_analysis_agent: [user_proxy],
    user_proxy: [stock_analysis_agent, custom_signal_analysis_agent],
    stock_analysis_agent: [user_proxy, custom_signal_analysis_agent],
}

group_chat = GroupChat(
    agents=[stock_analysis_agent, custom_signal_analysis_agent, user_proxy],
    # https://microsoft.github.io/autogen/docs/notebooks/JSON_mode_example#defining-allowed-speaker-transitions
    allowed_or_disallowed_speaker_transitions=allowed_transitions,
    speaker_transitions_type="allowed",  #  either 'allowed' or 'disallowed'.
    messages=[],
    max_round=10,
    # https://microsoft.github.io/autogen/docs/topics/groupchat/resuming_groupchat#example-of-resuming-a-terminated-groupchat
    speaker_selection_method=custom_speaker_selection_func,
    select_speaker_message_template=speaker_select_msg_prompt,  # when mode is auto
    select_speaker_prompt_template=speaker_select_prompt,  # when mode is auto
    max_retries_for_selecting_speaker=5,  # New
    select_speaker_auto_verbose=False,  # New
)

group_chat_manager = GroupChatManager(
    groupchat=group_chat,
    llm_config=llm_config,
    is_termination_msg=lambda x: x.get("content", "") is not None
    and "TERMINATE" in x.get("content", ""),
)


# **Tool Use**
# **Register functions for stock analysis with both the user proxy and assistant agent**
@user_proxy.register_for_execution()
@stock_analysis_agent.register_for_llm(
    description="Create stock price data from a file path or API."
)
def create_stock_data(
    ticker: Annotated[str, "Stock symbol to analyze"] = "MSFT",
    start_date: Annotated[
        str, "Start date in format YYYY-MM-DD"
    ] = datetime.today().strftime("%Y-%m-%d"),
    end_date: Annotated[
        str, "End date in format YYYY-MM-DD"
    ] = datetime.today().strftime("%Y-%m-%d"),
) -> str:
    price_data_file_path = os.path.join(WORK_DIR, DATASET_STOCK)
    fetch_stock_data(ticker, start_date, end_date, price_data_file_path)
    return f"Stock data loaded from {price_data_file_path}"


@user_proxy.register_for_execution()
@stock_analysis_agent.register_for_llm(
    description="Search for description of indicators on the web."
)
@custom_signal_analysis_agent.register_for_llm(
    description="Search for examples of using the `ta` library on the web."
)
def search_ideas_from_web(
    search_query_str: Annotated[str, "Search query for web search"]
) -> str:
    search = WebSearch()
    results = search.search_query(search_query_str)
    output = ""
    if results is not None:
        for title, link, snippet in results:
            output += f"{title}\n {snippet}\n\n"
    return output


@user_proxy.register_for_execution()
@stock_analysis_agent.register_for_llm(
    description="Execute a backtesting strategy based on buy/sell signals."
)
def execute_backtesting_strategy(
    stock_price_file_path: Annotated[str, "Stock price data file path"],
    stock_signals_file_path: Annotated[str, "Stock buy/sell signal data file path"],
) -> BacktestPerformanceMetrics:
    backtest_performance_metrics = backtest_stock_strategy(
        stock_price_file_path, stock_signals_file_path
    )
    return backtest_performance_metrics


# Example of initiating chat to run stock analysis
if __name__ == "__main__":
    # Start logging
    autogen.runtime_logging.start()

    if os.path.exists(WORK_DIR):
        pass
        # os.system(f"rm -rf {WORK_DIR}")
    else:
        os.mkdir(WORK_DIR)

    # https://microsoft.github.io/autogen/docs/FAQ/#why-is-code-not-saved-as-file
    # 2023-01-01 / 10 days Moving Average and MACD / 20 days Moving Average / 20 days Moving Average and 120 days Moving Average.
    today = datetime.today().strftime("%Y-%m-%d")
    user_message = dedent(
        f"""
        save the code to disk.

        Run complete stock analysis for MSFT from 1995-01-01 to {today}. 
        Generate buy/sell signals using 10 days Moving Average.
        Based on the generated signals, backtest the strategy and provide performance metrics.
        """
    )

    summary_prompt = dedent(
        """
        Return the performance metrics in Markdown format based on the backtesting results.
        Don't forget to include the cumulative return, CAGR, MDD, and Sharpe Ratio.
        """
    )
    # https://microsoft.github.io/autogen/docs/notebooks/agentchat_auto_feedback_from_code_execution
    # file_path="_output\{DATASET_STOCK}",  # custom_context: how to use the file.  file_path = context.get("file_path")
    try:
        chat_res = user_proxy.initiate_chat(
            recipient=group_chat_manager,
            message=user_message,
            summary_method="last_msg",  # reflection_with_llm or last_msg
            summary_args={
                "summary_prompt": summary_prompt,
            },
        )
    except Exception as e:
        print(e)

    # Output the final chat history showing the original 4 messages and the resumed message
    for i, message in enumerate(group_chat.messages):
        print(
            f"#{i + 1}, {message['name']}: {message['content'][:80]}".replace(
                "\n", " "
            ),
            f"{'...' if len(message['content']) > 80 else ''}".replace("\n", " "),
        )

    # print(chat_res.cost)
    print(chat_res.summary)

    # Stop logging
    autogen.runtime_logging.stop()
