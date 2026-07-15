"""Ground investment research in an Azure AI Search corpus."""

import asyncio
import os

from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv


async def main() -> None:
    load_dotenv(override=False)
    try:
        from agent_framework_azure_ai_search import AzureAISearchContextProvider
    except ImportError as error:
        raise SystemExit(
            "Install agent-framework-azure-ai-search to use this pattern."
        ) from error
    credential = DefaultAzureCredential()
    provider = AzureAISearchContextProvider(
        endpoint=os.environ["AZURE_AI_SEARCH_ENDPOINT"],
        index_name=os.environ["AZURE_AI_SEARCH_INDEX"],
        credential=credential,
        mode="semantic",
    )
    agent = FoundryChatClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    ).as_agent(
        name="filing_grounded_researcher",
        instructions="Use retrieved investment filings and cite the evidence. Report gaps and never advise a trade.",
        context_providers=[provider],
    )
    try:
        async with agent:
            print(
                (
                    await agent.run(
                        "Summarize the documented risks in the indexed annual report."
                    )
                ).text
            )
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
