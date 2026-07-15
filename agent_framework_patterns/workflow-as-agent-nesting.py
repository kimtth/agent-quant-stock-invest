"""Wrap a deterministic research workflow as a tool for a parent agent."""

import asyncio
import os
from typing_extensions import Never

from agent_framework import Message, WorkflowBuilder, WorkflowContext, executor
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv


@executor(id="ticker_normalizer")
async def normalize(messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:
    ticker = messages[-1].text if messages else ""
    symbol = ticker.upper().strip().split()[-1].rstrip(".?!")
    await ctx.yield_output(
        f"Ticker: {symbol}; research scope: public fundamentals and risks only."
    )


async def main() -> None:
    load_dotenv(override=False)
    workflow = WorkflowBuilder(
        start_executor=normalize, output_from=[normalize], name="ticker_scope_workflow"
    ).build()
    credential = AzureCliCredential()
    client = FoundryChatClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )
    parent = client.as_agent(
        name="nested_research_coordinator",
        instructions="Use the ticker-scope workflow, then write a research-only response with limitations and risks.",
        tools=[workflow.as_agent(name="ticker_scope").as_tool(name="scope_ticker")],
    )
    try:
        async with parent:
            print((await parent.run("Research the scope for msft.")).text)
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
