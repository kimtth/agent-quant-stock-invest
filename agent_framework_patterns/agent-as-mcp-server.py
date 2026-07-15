"""Expose a research-only investment agent as one MCP stdio tool."""

import anyio
import os
from typing import Annotated

from agent_framework import tool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv


@tool(approval_mode="never_require")
def realized_volatility(
    ticker: Annotated[str, "Ticker to analyse."],
    window_days: Annotated[int, "Lookback window in trading days."] = 20,
) -> str:
    """Provide a bounded research data request; it never submits an order."""
    if not 5 <= window_days <= 252:
        return "Invalid lookback: use 5 to 252 trading days."
    return f"Request a verified {window_days}-day realized-volatility observation for {ticker.upper()}."


async def run() -> None:
    load_dotenv(override=False)
    credential = AzureCliCredential()
    client = FoundryChatClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )
    agent = client.as_agent(
        name="investment_research_tool",
        description="Answers research-only questions about equity volatility.",
        instructions="Use the tool for volatility questions. State data limitations and never execute trades.",
        tools=[realized_volatility],
    )
    try:
        async with agent:
            server = agent.as_mcp_server(
                server_name="investment-research-mcp", version="1.0.0"
            )
            from mcp.server.stdio import stdio_server

            async with stdio_server() as (read_stream, write_stream):
                await server.run(
                    read_stream, write_stream, server.create_initialization_options()
                )
    finally:
        await credential.close()


if __name__ == "__main__":
    anyio.run(run)
