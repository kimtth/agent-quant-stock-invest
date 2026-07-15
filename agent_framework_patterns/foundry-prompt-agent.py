"""Convert a local investment research agent into a Foundry prompt-agent definition."""

import asyncio
import json
import os

from agent_framework.foundry import FoundryChatClient, to_prompt_agent
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
        name="publishable_investment_researcher",
        instructions="Produce investment research with dated evidence, risks, and limitations. Never recommend a transaction.",
    )
    try:
        definition = to_prompt_agent(agent)
        print(json.dumps(definition.as_dict(), indent=2, default=str))
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
