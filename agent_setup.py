from contextlib import AsyncExitStack
import os
from textwrap import dedent
from typing import Awaitable, Callable, Dict, Any

from agent_framework.azure import AzureOpenAIChatClient, AzureAIAgentClient
from azure.identity import DefaultAzureCredential
from pydantic import BaseModel

from agent_tools import AgentQuantTools
from constant import DATASET_STOCK, DATASET_SIGNALS, WORK_DIR


class AgentCompletedResult(BaseModel):
    """Model for the result of an agent's completed execution."""

    success: bool
    message: str


class CreateQuantAgent:
    """Factory class for creating specialized quantitative trading agents."""

    def __init__(
        self, client: AzureOpenAIChatClient, function_tools: AgentQuantTools
    ) -> None:
        """
        Initialize the agent factory.

        Args:
            client: Azure OpenAI chat client
            function_tools: Collection of AI function tools
        """
        self.client = client
        self.tools = function_tools

    async def create_agents(self) -> Dict[str, Any]:
        """
        Create all specialized agents for the quantitative trading workflow.

        Returns:
            Dict[str, Any]: Dictionary mapping agent names to agent instances
        """
        data_agent = self.client.create_agent(
            id="stock_data_fetcher",
            description="Fetches historical stock data from Yahoo Finance.",
            instructions="""You fetch stock data from Yahoo Finance.
                    Use the fetch_stock_data tool to download historical data.
                    Always specify ticker, start_date, and end_date.

                    Confirm that result files were created successfully.
                    """,
            tools=[self.tools.fetch_stock_data],
            response_format=AgentCompletedResult,
        )

        signal_agent = self.client.create_agent(
            id="signal_generator",
            description="Generates trading signals based on stock data.",
            instructions=dedent(
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
                - Column name errors (use "Adj Close" not "Close")
                - Missing .fillna(False) for boolean columns
                - Wrong ta library method names
                - Index/parsing issues with CSV
                - File not found errors (check path construction)
            """
            ),
            tools=[self.tools.execute_python_code],
            response_format=AgentCompletedResult,
        )

        backtest_agent = self.client.create_agent(
            id="backtester",
            description="Backtests trading strategies based on generated signals.",
            instructions="""You backtest trading strategies.
            Use the backtest_strategy tool to calculate performance metrics.
            Report CAGR, total return, and final portfolio value.
            
            Confirm that result files were created successfully.
            """,
            tools=[self.tools.backtest_strategy],
            response_format=AgentCompletedResult,
        )

        summary_agent = self.client.create_agent(
            id="summary_reporter",
            description="Generates a summary report of the trading strategy performance.",
            instructions="""You generate a summary report of the trading strategy performance.
            Use the summary_report tool to create a concise report.
            DO NOT include raw data or code, only a clear summary.
            Highlight key metrics and insights.
            """
        )

        return {
            "data_agent": data_agent,
            "signal_agent": signal_agent,
            "backtest_agent": backtest_agent,
            "summary_agent": summary_agent,
        }

    """
    Helper utilities for Azure Foundry AI agent usage.

    This module provides a small helper that constructs an Azure AI agent factory
    and a corresponding close coroutine. The helper demonstrates using
    AsyncExitStack to ensure async context-managed resources (credential and client)
    are cleaned up reliably.
    """

    async def _create_azure_foundry_ai_agent() -> tuple[
        Callable[..., Awaitable[Any]], Callable[[], Awaitable[None]]
    ]:
        """Create an agent factory and a close coroutine.

        Returns:
            A tuple (agent_factory, close_coroutine):
                - agent_factory: async callable(**kwargs) -> Any
                  Call with the same kwargs you would pass to AzureAIAgentClient.create_agent.
                - close_coroutine: async callable() -> None
                  Await to release resources associated with the client and credential.

        Notes:
            - The function uses AsyncExitStack so that all entered async contexts are
              closed automatically when the close coroutine is awaited.
            - This is a lightweight wrapper kept for reference; adapt as needed for
              your application's lifecycle management.
        """
        async with AsyncExitStack() as stack:
            # Enter async contexts for credential and client so they are cleaned up.
            cred = await stack.enter_async_context(DefaultAzureCredential())
            client = await stack.enter_async_context(
                AzureAIAgentClient(
                    project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
                    agent_id=os.environ["AZURE_AI_AGENT_ID"],
                    credential=cred,
                )
            )

            async def agent(**kwargs: Any) -> Any:
                """Agent factory that creates an agent using the managed client."""
                return await stack.enter_async_context(client.create_agent(**kwargs))

            async def close() -> None:
                """Close and release all resources managed by the AsyncExitStack."""
                await stack.aclose()

        return agent, close
