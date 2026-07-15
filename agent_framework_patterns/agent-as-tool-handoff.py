"""Delegate an equity question to valuation and risk specialists in-process."""

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
    valuation = client.as_agent(
        name="valuation_specialist",
        instructions="Analyse valuation drivers and assumptions only; do not make a trade recommendation.",
    )
    risk = client.as_agent(
        name="risk_specialist",
        instructions="Identify market, balance-sheet, concentration, and uncertainty risks only.",
    )
    coordinator = client.as_agent(
        name="portfolio_research_coordinator",
        instructions=(
            "Route each question to the most relevant specialist, synthesize their work, "
            "and include limitations. This is research, not investment advice."
        ),
        tools=[
            valuation.as_tool(name="analyse_valuation", propagate_session=True),
            risk.as_tool(name="analyse_risks", propagate_session=True),
        ],
    )
    try:
        async with valuation, risk, coordinator:
            print(
                (
                    await coordinator.run(
                        "Compare valuation drivers and risks for MSFT."
                    )
                ).text
            )
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
