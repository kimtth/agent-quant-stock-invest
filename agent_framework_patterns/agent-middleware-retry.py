"""Apply retry middleware to a read-only market-data research agent."""

import asyncio
import os

from agent_framework import agent_middleware
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv


@agent_middleware
async def retry_transient_failures(context, next_handler):
    for attempt in range(3):
        try:
            return await next_handler()
        except (TimeoutError, OSError):
            if attempt == 2:
                raise
            await asyncio.sleep(2**attempt)


async def main() -> None:
    load_dotenv(override=False)
    credential = AzureCliCredential()
    agent = FoundryChatClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    ).as_agent(
        name="fresh_market_researcher",
        instructions="Use only fresh, explicitly dated research inputs. Never execute orders.",
        middleware=[retry_transient_failures],
    )
    try:
        async with agent:
            print(
                (
                    await agent.run(
                        "Draft a dated research checklist for analysing an ETF."
                    )
                ).text
            )
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
