"""Connect an investment researcher to a local, read-only MCP stdio server."""

import asyncio
import os

from agent_framework import MCPStdioTool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv


async def main() -> None:
    load_dotenv(override=False)
    credential = AzureCliCredential()
    price_server = MCPStdioTool(
        name="market_data_mcp",
        command=os.environ["MARKET_DATA_MCP_COMMAND"],
        args=os.environ.get("MARKET_DATA_MCP_ARGS", "").split(),
        allowed_tools=["get_price_history"],
        approval_mode="never_require",
    )
    agent = FoundryChatClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    ).as_agent(
        name="local_mcp_researcher",
        instructions="Use only the read-only price-history tool. Date every observation, disclose gaps, and never trade.",
        tools=[price_server],
    )
    try:
        async with agent:
            print(
                (
                    await agent.run(
                        "Summarize the available historical-price data for MSFT."
                    )
                ).text
            )
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
