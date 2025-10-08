import autogen
from typing import Dict
from autogen import ConversableAgent
from utils.llm_tool_use import PlotToolRegistry


class StockReportAgent:
    def __init__(self, llm_config: Dict):
        self.__llm_config = llm_config
        self.__report_agent_prompt = self._stock_report_agent_prompt()

    @staticmethod
    def _stock_report_agent_prompt() -> str:
        return f"""
            # Role:
            You are responsible for generating stock performance plots. 

            # Tasks:
            - You can generate plots for the stock data and backtest results.

            If the plot creating is successful, reply TERMINATE
            If more steps are required, reply CONTINUE, or explain why the task has not been solved yet.
            If an error occurs, reply 'TERMINATE for ERROR' with the error message.
            """

    def create_agent(self):
        return autogen.AssistantAgent(
            name="stock_report_agent",
            system_message=self.__report_agent_prompt,
            llm_config=self.__llm_config,
        )
    
    def register_tools(self, user_proxy: ConversableAgent, stock_analysis_agent: ConversableAgent):
        tool_registry = PlotToolRegistry(user_proxy, stock_analysis_agent)
        tool_registry.register_tools()
