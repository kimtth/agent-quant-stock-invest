"""Connect to a Foundry-hosted investment toolbox through streamable HTTP MCP."""

import asyncio
import os

from agent_framework import MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv


async def main() -> None:
    load_dotenv(override=False)
    credential = AzureCliCredential()
    toolbox = MCPStreamableHTTPTool(
        name="investment_toolbox",
        url=os.environ["FOUNDRY_INVESTMENT_TOOLBOX_URL"],
        allowed_tools=["search_filings", "get_market_snapshot"],
        approval_mode="never_require",
    )
    agent = FoundryChatClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    ).as_agent(
        name="toolbox_researcher",
        instructions="Use approved read-only toolbox tools, cite returned evidence, disclose limitations, and never execute trades.",
        tools=[toolbox],
    )
    try:
        async with agent:
            print(
                (
                    await agent.run(
                        "Find filing evidence about liquidity risk for the requested issuer."
                    )
                ).text
            )
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
