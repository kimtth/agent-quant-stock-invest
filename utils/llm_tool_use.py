import os
from utils.const import WORK_DIR, DATASET_STOCK
from utils.functions import fetch_stock_data, backtest_stock_strategy
from utils.web_search import WebSearch
from datetime import datetime
from typing import Annotated
from utils.datamodels import BacktestPerformanceMetrics


class ToolRegistry:
    def __init__(self, user_proxy, stock_analysis_agent, custom_signal_analysis_agent):
        self.user_proxy = user_proxy
        self.stock_analysis_agent = stock_analysis_agent
        self.custom_signal_analysis_agent = custom_signal_analysis_agent

    def register_tools(self):
        self.__register_create_stock_data()
        self.__register_search_ideas_from_web()
        self.__register_execute_backtesting_strategy()

    def __register_create_stock_data(self):
        @self.user_proxy.register_for_execution()
        @self.stock_analysis_agent.register_for_llm(
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

    def __register_search_ideas_from_web(self):
        @self.user_proxy.register_for_execution()
        @self.stock_analysis_agent.register_for_llm(
            description="Search for description of indicators on the web."
        )
        @self.custom_signal_analysis_agent.register_for_llm(
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
                    markdown_format =  f"### [{title}]({link})\n\n{snippet}\n\n"
                    output += markdown_format
            return output

    def __register_execute_backtesting_strategy(self):
        @self.user_proxy.register_for_execution()
        @self.stock_analysis_agent.register_for_llm(
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