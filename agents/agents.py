from typing import Dict, Any

from agent_framework.azure import AzureOpenAIResponsesClient
from pydantic import BaseModel

from .tools import AgentQuantTools
from .prompts import (
    DATA_AGENT_INSTRUCTIONS,
    SIGNAL_AGENT_INSTRUCTIONS,
    BACKTEST_AGENT_INSTRUCTIONS,
    SUMMARY_AGENT_INSTRUCTIONS,
)


class AgentCompletedResult(BaseModel):
    """Model for the result of an agent's completed execution."""

    success: bool
    message: str


class CreateQuantAgent:
    """Factory class for creating specialized quantitative trading agents."""

    def __init__(
        self, client: AzureOpenAIResponsesClient, function_tools: AgentQuantTools
    ) -> None:
        self.client = client
        self.tools = function_tools

    async def create_agents(self) -> Dict[str, Any]:
        """Create all specialized agents for the quantitative trading workflow."""

        data_agent = self.client.as_agent(
            name="stock_data_fetcher",
            instructions=DATA_AGENT_INSTRUCTIONS,
            tools=[self.tools.fetch_stock_data],
            default_options={"response_format": AgentCompletedResult},
        )

        signal_agent = self.client.as_agent(
            name="signal_generator",
            instructions=SIGNAL_AGENT_INSTRUCTIONS,
            tools=[self.tools.execute_python_code],
            default_options={"response_format": AgentCompletedResult},
        )

        backtest_agent = self.client.as_agent(
            name="backtester",
            instructions=BACKTEST_AGENT_INSTRUCTIONS,
            tools=[self.tools.backtest_strategy],
            default_options={"response_format": AgentCompletedResult},
        )

        summary_agent = self.client.as_agent(
            name="summary_reporter",
            instructions=SUMMARY_AGENT_INSTRUCTIONS,
        )

        return {
            "data_agent": data_agent,
            "signal_agent": signal_agent,
            "backtest_agent": backtest_agent,
            "summary_agent": summary_agent,
        }

