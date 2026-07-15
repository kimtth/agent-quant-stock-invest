"""Evaluate an investment brief with deterministic Agent Framework checks."""

import asyncio
import os

from agent_framework import LocalEvaluator, evaluate_agent, evaluator, keyword_check
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv


@evaluator
def includes_risk_and_limitations(response: str) -> bool:
    text = response.lower()
    return "risk" in text and "limitation" in text and "buy" not in text


async def main() -> None:
    load_dotenv(override=False)
    credential = AzureCliCredential()
    agent = FoundryChatClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    ).as_agent(
        name="evaluated_equity_researcher",
        instructions="Create research-only investment briefs with a Risks and Limitations section. Never issue buy or sell advice.",
    )
    try:
        async with agent:
            results = await evaluate_agent(
                agent=agent,
                queries=["Write a brief research note on an equity ETF."],
                evaluators=LocalEvaluator(
                    keyword_check("Risks"), includes_risk_and_limitations
                ),
            )
            for result in results:
                print(
                    f"{result.provider}: {result.passed}/{result.total} checks passed"
                )
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
