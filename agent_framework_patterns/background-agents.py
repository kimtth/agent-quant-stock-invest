"""Delegate concurrent investment research tasks to background harness agents."""

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
    fundamentals = create_harness_agent(
        client,
        name="fundamentals_researcher",
        description="Analyses financial-statement questions.",
        agent_instructions="Research fundamentals and missing evidence only.",
        max_context_window_tokens=32_000,
        max_output_tokens=3_000,
    )
    risks = create_harness_agent(
        client,
        name="risk_researcher",
        description="Analyses investment risks.",
        agent_instructions="Research risks and uncertainty only.",
        max_context_window_tokens=32_000,
        max_output_tokens=3_000,
    )
    parent = create_harness_agent(
        client,
        name="investment_orchestrator",
        agent_instructions="Delegate independent research, wait for results, and synthesize without trade advice.",
        max_context_window_tokens=32_000,
        max_output_tokens=4_000,
        background_agents=[fundamentals, risks],
    )
    try:
        async with fundamentals, risks, parent:
            print(
                (
                    await parent.run(
                        "Research fundamental and risk questions to ask before analysing an equity ETF.",
                        session=AgentSession(),
                    )
                ).text
            )
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
