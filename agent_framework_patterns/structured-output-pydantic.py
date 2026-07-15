"""Produce a validated, research-only investment thesis with Pydantic."""

import asyncio
import os

from pydantic import BaseModel, Field
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv


class InvestmentThesis(BaseModel):
    ticker: str = Field(description="Uppercase equity ticker.")
    thesis: str = Field(description="Evidence-led research thesis, not advice.")
    catalysts: list[str]
    risks: list[str]
    limitations: list[str]
    confidence: float = Field(ge=0, le=1)


async def main() -> None:
    load_dotenv(override=False)
    credential = AzureCliCredential()
    client = FoundryChatClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )
    agent = client.as_agent(
        name="structured_equity_analyst",
        instructions="Return a cautious research-only equity thesis. Include uncertainties and never recommend a transaction.",
        default_options={"response_format": InvestmentThesis},
    )
    try:
        async with agent:
            response = await agent.run(
                "Create a thesis for MSFT based only on stated assumptions."
            )
            thesis = InvestmentThesis.model_validate_json(response.text)
            print(thesis.model_dump_json(indent=2))
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
