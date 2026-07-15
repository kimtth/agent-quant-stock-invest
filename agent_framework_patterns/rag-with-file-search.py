"""Use a Foundry file-search vector store for filing-grounded research."""

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
    file_search = client.get_file_search_tool(
        vector_store_ids=[os.environ["FOUNDRY_INVESTMENT_VECTOR_STORE_ID"]]
    )
    agent = client.as_agent(
        name="filing_file_search_researcher",
        instructions="Answer only from retrieved filing content, cite it, describe gaps, and never advise trading.",
        tools=[file_search],
    )
    try:
        async with agent:
            print(
                (
                    await agent.run(
                        "What liquidity risks appear in the indexed filing corpus?"
                    )
                ).text
            )
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
