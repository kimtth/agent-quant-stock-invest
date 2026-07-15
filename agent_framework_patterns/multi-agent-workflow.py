"""Run a data-flow workflow for an investment research brief."""

import asyncio
import os
from typing_extensions import Never

from agent_framework import WorkflowBuilder, WorkflowContext, executor
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
    market = client.as_agent(
        name="market_context",
        instructions="Summarize market context and data assumptions for the ticker; research only.",
    )
    risk = client.as_agent(
        name="risk_review",
        instructions="List material investment risks, uncertainty, and missing evidence; never advise a trade.",
    )
    writer = client.as_agent(
        name="brief_writer",
        instructions="Write a balanced research brief from supplied context and risks. Include limitations and no recommendation.",
    )

    @executor(id="market_context")
    async def collect(question: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message((await market.run(question)).text)

    @executor(id="risk_review")
    async def review(context: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message((await risk.run(context)).text)

    @executor(id="brief_writer")
    async def summarize(risks: str, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output((await writer.run(risks)).text)

    workflow = (
        WorkflowBuilder(
            start_executor=collect,
            output_from=[summarize],
            name="equity_research_workflow",
        )
        .add_edge(collect, review)
        .add_edge(review, summarize)
        .build()
    )
    try:
        async with market, risk, writer:
            async for event in workflow.run(
                "Research MSFT's current opportunity and key risks.", stream=True
            ):
                if event.type == "output":
                    print(event.data)
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
