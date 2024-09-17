
import autogen
from typing import Dict
from utils.const import BACKTEST_RESULTS_FILE


class StockReportAgent:
    def __init__(self, llm_config: Dict):
        self.__llm_config = llm_config
        self.__report_agent_prompt = self._stock_report_agent_prompt()

    @staticmethod
    def _stock_report_agent_prompt() -> str:
        return f"""
            # Role:
                Plot a graph comparing the stock prices over the periods of time.

            # Tasks:
                1. Load "BACKTEST_RESULTS_FILE" from "REPORT_DATA_DIR".
                   ```python
                   import seaborn as sns
                   import pandas as pd
                   import os

                   BACKTEST_RESULTS_FILE = {BACKTEST_RESULTS_FILE} 
                   REPORT_DATA_DIR = '.'  # REPORT_DATA_DIR is the directory where the file is stored.
                   abs_path = os.path.abspath(REPORT_DATA_DIR)
                   file_path = os.path.join(abs_path, BACKTEST_RESULTS_FILE)
                   ```
                2. Plot a graph with following columns:
                    - Stock price column name: 'Adj Close'
                    - Cumulative Returns column name: 'Cumulative Returns'
                    - MDD column name: 'MDD'
                3. Analyze the stock price trends and patterns.
                4. Do not include any messages or descriptions in the output, except for python code.
                5. The dataset is very large, so you can use the last days of each year and month for plotting.
                6. Please ensure that the plot is displayed and saved in the current working directory.
                7. If the task is successful, reply TERMINATE. Otherwise, reply RESTART.
            """
    
    def create_agent(self):
        return autogen.AssistantAgent(
            name="stock_report_agent",
            system_message=self.__report_agent_prompt,
            llm_config=self.__llm_config,
        )