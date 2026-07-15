"""Classify recoverable research failures without fabricating market data."""

import asyncio
import os

from agent_framework import AgentFrameworkException
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv


async def main() -> None:
    load_dotenv(override=False)
    credential = AzureCliCredential()
    agent = FoundryChatClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    ).as_agent(
        name="resilient_researcher",
        instructions="Provide research only. If evidence is unavailable, say so rather than guessing.",
    )
    try:
        async with agent:
            try:
                print(
                    (
                        await agent.run(
                            "Summarize the known risks of a small-cap equity allocation."
                        )
                    ).text
                )
            except AgentFrameworkException as error:
                print(
                    f"Research service failure: {error}. No market-data claim was produced."
                )
            except (TimeoutError, OSError) as error:
                print(
                    f"Transient transport failure: {error}. Retry after verifying data freshness."
                )
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
