"""Create a long-running harness agent for research planning, not trading."""

import asyncio
import os

from agent_framework import AgentSession, create_harness_agent
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
    agent = create_harness_agent(
        client,
        name="investment_research_harness",
        description="Plans evidence-led equity research.",
        agent_instructions="Plan research, track assumptions, disclose risks and limitations, and never place or recommend trades.",
        max_context_window_tokens=32_000,
        max_output_tokens=4_000,
    )
    try:
        async with agent:
            print(
                (
                    await agent.run(
                        "Build a research plan for comparing two broad-market ETFs.",
                        session=AgentSession(),
                    )
                ).text
            )
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
