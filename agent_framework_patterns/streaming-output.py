"""Stream a market-risk briefing as it is generated."""

import asyncio
import os

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
        name="streaming_market_brief",
        instructions="Stream a concise market-risk brief. Label assumptions and limitations; never make trade recommendations.",
    )
    try:
        async with agent:
            async for update in agent.run(
                "Explain the main risks to a diversified US equity portfolio.",
                stream=True,
            ):
                if update.text:
                    print(update.text, end="", flush=True)
            print()
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
