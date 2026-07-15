"""Run Foundry LLM-as-a-judge evaluation for investment research quality."""

import asyncio
import os

from agent_framework import evaluate_agent
from agent_framework.foundry import FoundryChatClient, FoundryEvals
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
    agent = client.as_agent(
        name="foundry_evaluated_researcher",
        instructions="Write source-aware investment research with risks and limitations, never a trade recommendation.",
    )
    try:
        async with agent:
            query = (
                "Draft a cautious equity research brief with assumptions, two risks, "
                "and two limitations. Use at most 150 words."
            )
            response = await agent.run(query)
            print(response.text)
            evaluator = FoundryEvals(
                client=client,
                model=os.getenv(
                    "FOUNDRY_EVALUATION_MODEL",
                    os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                ),
                evaluators=["groundedness", "relevance"],
            )
            await evaluate_agent(
                agent=agent,
                queries=[query],
                evaluators=evaluator,
            )
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
