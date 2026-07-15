"""Persist investment research session history through the Cosmos provider."""

import asyncio
import os

from agent_framework import AgentSession
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv


async def main() -> None:
    load_dotenv(override=False)
    try:
        from agent_framework_azure_cosmos import CosmosHistoryProvider
    except ImportError as error:
        raise SystemExit(
            "Install agent-framework-azure-cosmos to use this pattern."
        ) from error
    credential = DefaultAzureCredential()
    history = CosmosHistoryProvider(
        endpoint=os.environ["AZURE_COSMOS_ENDPOINT"],
        database_name=os.environ.get("AZURE_COSMOS_DATABASE", "investment-agents"),
        container_name=os.environ.get("AZURE_COSMOS_CONTAINER", "research-history"),
        credential=credential,
    )
    agent = FoundryChatClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    ).as_agent(
        name="cosmos_researcher",
        instructions="Maintain a research-only investment conversation with risk disclosure.",
        context_providers=[history],
    )
    try:
        async with agent:
            print(
                (
                    await agent.run(
                        "Track the assumptions for my ETF research.",
                        session=AgentSession(),
                    )
                ).text
            )
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
