
import autogen
from typing import Dict
from utils.const import BACKTEST_RESULTS_FILE, PLOT_FILE_NAME


class StockReportAgent:
    def __init__(self, llm_config: Dict):
        self.__llm_config = llm_config
        self.__report_agent_prompt = self._stock_report_agent_prompt()

    @staticmethod
    def _stock_report_agent_prompt() -> str:
        return f"""
            # Role:
            Plot a graph comparing stock prices over time.

            # Tasks:
            1. Load the file `"BACKTEST_RESULTS_FILE"` from the directory `"REPORT_DATA_DIR"`:
                ```python
                import seaborn as sns
                import pandas as pd
                import os

                BACKTEST_RESULTS_FILE = {BACKTEST_RESULTS_FILE}
                REPORT_DATA_DIR = '.'
                abs_path = os.path.abspath(REPORT_DATA_DIR)
                file_path = os.path.join(abs_path, BACKTEST_RESULTS_FILE)
                plot_output_path = os.path.join(abs_path, '{PLOT_FILE_NAME}')
                ```

            2. Plot the following columns:
                - Cumulative Returns: `'Cumulative Returns'`
                - MDD: `'MDD'`

            3. Create separate subplots for Cumulative Returns and MDD using `plt.subplots(2, 1)` in the same figure.
            4. Exclude any messages or descriptions from the output, providing only the Python code.
            5. Use the last days of each year and month for plotting due to the large dataset.
            6. Ensure the plot is saved in the current working directory.
            7. Provide the code to `user_proxy` for execution without running it.
            """
    
    def create_agent(self):
        return autogen.AssistantAgent(
            name="stock_report_agent",
            system_message=self.__report_agent_prompt,
            llm_config=self.__llm_config,
        )