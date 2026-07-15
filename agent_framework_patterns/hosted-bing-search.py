"""Ground an investment news brief with the configured Foundry Bing connection."""

import asyncio
import os

from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv


async def main() -> None:
    load_dotenv(override=False)
    credential = AzureCliCredential()
    client = FoundryChatClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )
    bing = client.get_bing_grounding_tool(
        connection_id=os.environ["FOUNDRY_BING_CONNECTION_ID"]
    )
    agent = client.as_agent(
        name="news_grounded_researcher",
        instructions="Use Bing only for dated investment-news research. Cite sources, distinguish news from facts, and do not advise trades.",
        tools=[bing],
    )
    try:
        async with agent:
            print(
                (
                    await agent.run(
                        "Summarize recent, cited news that could affect a broad US equity ETF."
                    )
                ).text
            )
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
