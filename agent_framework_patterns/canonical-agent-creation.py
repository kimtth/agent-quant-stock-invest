"""Create a research-only equity analyst with Microsoft Agent Framework."""

import asyncio
import os
from typing import Annotated

from agent_framework import tool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv


@tool(approval_mode="never_require")
def valuation_snapshot(
    ticker: Annotated[str, "Listed equity ticker, such as MSFT."],
) -> str:
    """Return a bounded request for a separately verified valuation feed."""
    return f"{ticker.upper()}: provide only independently verified price, EPS, and valuation inputs."


async def main() -> None:
    load_dotenv(override=False)
    credential = AzureCliCredential()
    agent = FoundryChatClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    ).as_agent(
        name="equity_researcher",
        instructions=(
            "Produce a research-only equity brief. Call valuation_snapshot when useful, "
            "separate facts from assumptions, disclose risks, and never place or recommend trades."
        ),
        tools=[valuation_snapshot],
    )
    try:
        async with agent:
            print(
                (
                    await agent.run(
                        "Prepare a concise valuation research brief for MSFT."
                    )
                ).text
            )
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
