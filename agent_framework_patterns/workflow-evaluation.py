"""Evaluate each agent stage of a research workflow with local criteria."""

import asyncio
import os
from typing_extensions import Never

from agent_framework import (
    LocalEvaluator,
    WorkflowBuilder,
    WorkflowContext,
    evaluate_workflow,
    executor,
    keyword_check,
)
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
    analyst = client.as_agent(
        name="workflow_analyst",
        instructions="Provide investment research context and disclose assumptions.",
    )
    reviewer = client.as_agent(
        name="workflow_reviewer",
        instructions="Add risks and limitations; do not provide investment advice.",
    )

    @executor(id="analysis")
    async def analyse(query: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message((await analyst.run(query)).text)

    @executor(id="review")
    async def review(text: str, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output((await reviewer.run(text)).text)

    workflow = (
        WorkflowBuilder(start_executor=analyse, output_from=[review])
        .add_edge(analyse, review)
        .build()
    )
    try:
        async with analyst, reviewer:
            results = await evaluate_workflow(
                workflow=workflow,
                queries=["Research an equity ETF."],
                evaluators=LocalEvaluator(keyword_check("risk")),
            )
            print(results)
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
