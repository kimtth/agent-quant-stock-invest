import json
import os
from utils.const import WORK_DIR, DATASET_STOCK, STRATEGY_IDEAS
from utils.functions import fetch_stock_data, backtest_stock_strategy
from utils.web_search import WebSearch
from datetime import datetime
from typing import Annotated, Dict
from autogen import ConversableAgent
from utils.const import AgentName
from utils.datamodels import BacktestPerformanceMetrics
from utils.llm_plot import plot_backtest_results


class ToolRegistry:
    def __init__(self, agent_registry: Dict[AgentName, ConversableAgent]):
        self._user_proxy = agent_registry.get(AgentName.USER_PROXY)
        self._stock_analysis_agent = agent_registry.get(AgentName.STOCK_ANALYSIS_AGENT)
        self._custom_signal_analysis_agent = agent_registry.get(
            AgentName.CUSTOM_SIGNAL_ANALYSIS_AGENT
        )
        self._strategy_idea_agent = agent_registry.get(AgentName.STRATEGY_IDEA_AGENT)
        self._stock_report_agent = agent_registry.get(AgentName.STOCK_REPORT_AGENT)

    def register_tools(self):
        self.__register_create_stock_data()
        self.__register_search_ideas_from_web()
        self.__register_execute_backtesting_strategy()

    def __register_create_stock_data(self):
        @self._user_proxy.register_for_execution()
        @self._stock_analysis_agent.register_for_llm(
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
        @self._user_proxy.register_for_execution()
        @self._stock_analysis_agent.register_for_llm(
            description="Search for description of indicators on the web."
        )
        @self._custom_signal_analysis_agent.register_for_llm(
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
                    markdown_format = f"### [{title}]({link})\n\n{snippet}\n\n"
                    output += markdown_format
            return output

    def __register_execute_backtesting_strategy(self):
        @self._user_proxy.register_for_execution()
        @self._stock_analysis_agent.register_for_llm(
            description="Execute a backtesting strategy based on buy/sell signals."
        )
        def execute_backtesting_strategy(
            stock_price_file_path: Annotated[str, "Stock price data file path"],
            stock_signals_file_path: Annotated[
                str, "Stock buy/sell signal data file path"
            ],
        ) -> BacktestPerformanceMetrics:
            try:
                backtest_performance_metrics = backtest_stock_strategy(
                    stock_price_file_path, stock_signals_file_path
                )
                return backtest_performance_metrics
            except Exception as e:
                return f"Error executing backtesting strategy: {str(e)}"


class JsonToolRegistry:
    def __init__(
        self, user_proxy: ConversableAgent, strategy_idea_agent: ConversableAgent
    ):
        self._user_proxy = user_proxy
        self._strategy_idea_agent = strategy_idea_agent

    def register_tools(self):
        self.__register_json_validation()
        self.__register_store_json_data()

    def __register_json_validation(self):
        @self._user_proxy.register_for_execution()
        @self._strategy_idea_agent.register_for_llm(
            description="Validate JSON data against a schema."
        )
        def validate_json_data(
            json_file_path: Annotated[str, "JSON file path to validate"]
        ) -> bool:
            try:
                with open(json_file_path, "r", encoding="utf8") as f:
                    json_string = f.read()
                json.loads(json_string)
                return True
            except json.JSONDecodeError:
                return False
            except Exception as e:
                return False

    def __register_store_json_data(self):
        @self._user_proxy.register_for_execution()
        @self._strategy_idea_agent.register_for_llm(
            description="Store JSON data as a file."
        )
        def store_json_data(
            json_string: Annotated[str, "JSON data as a string"]
        ) -> bool:
            try:
                # Store JSON data as a file
                with open(
                    os.path.join(WORK_DIR, STRATEGY_IDEAS), "w", encoding="utf8"
                ) as f:
                    f.write(json_string)
                return True
            except Exception as e:
                return False


class PlotToolRegistry:
    def __init__(
        self, user_proxy: ConversableAgent, stock_report_agent: ConversableAgent
    ):
        self._user_proxy = user_proxy
        self._stock_report_agent = stock_report_agent

    def register_tools(self):
        self.__register_stock_plot()

    def __register_stock_plot(self):
        @self._user_proxy.register_for_execution()
        @self._stock_report_agent.register_for_llm(
            description="Plot stock performance data."
        )
        def create_stock_perf_plot() -> str:
            # Plot the stock data
            try:
                plot_backtest_results()
                return "Stock performance plot created."
            except Exception as e:
                return f"Error creating stock performance plot: {str(e)}"

