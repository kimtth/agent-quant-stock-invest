from textwrap import dedent
from typing import Dict
from autogen import ConversableAgent
from utils.const import DATASET_STOCK, DATASET_SIGNALS
import autogen


class StockAnalysisAgent:
    def __init__(self, llm_config: Dict):
        self.__llm_config = llm_config
        self.__stock_analysis_agent_prompt = self._stock_analysis_agent_prompt()

    @staticmethod
    def _stock_analysis_agent_prompt() -> str:
        return dedent(
            f"""
            # Role:
            You are responsible for creating, analyzing, and processing stock data to generate insights.

            # Tasks:
            1. Create the "{DATASET_STOCK}" file from available stock data. This file will not be provided, and you must generate it.
            - COMPLETE CONDITION: The "{DATASET_STOCK}" file exists in the 'WORK_DIR'.

            2. After the signals are created, use the "{DATASET_STOCK}" and "{DATASET_SIGNALS}" files to perform a backtest of the stock strategy.
            - Analyze the stock data and use the provided buy/sell signals to generate performance metrics.
            - Provide insights and metrics such as CAGR (Compound Annual Growth Rate), MDD (Maximum Drawdown), and cumulative returns.

            Reply TERMINATE when the task is done.
            """
        )

    def create_agent(self) -> ConversableAgent:
        return autogen.AssistantAgent(
            name="stock_analysis_agent",
            system_message=self.__stock_analysis_agent_prompt,
            llm_config=self.__llm_config,
        )
