"""Checkpoint a two-stage investment research workflow for safe resumption."""

import asyncio
from pathlib import Path
from typing_extensions import Never

from agent_framework import (
    FileCheckpointStorage,
    WorkflowBuilder,
    WorkflowContext,
    executor,
)


@executor(id="validate_research_request")
async def validate(ticker: str, ctx: WorkflowContext[str]) -> None:
    symbol = ticker.upper().strip()
    if not symbol.isalnum() or len(symbol) > 12:
        raise ValueError("Use a valid ticker symbol.")
    await ctx.send_message(
        f"Validated {symbol}; collect dated public research before analysis."
    )


@executor(id="research_gate")
async def gate(message: str, ctx: WorkflowContext[Never, str]) -> None:
    await ctx.yield_output(
        f"{message} Human review is required; no order can be placed by this workflow."
    )


async def main() -> None:
    storage = FileCheckpointStorage(Path("checkpoints") / "investment_patterns")
    workflow = (
        WorkflowBuilder(
            start_executor=validate,
            output_from=[gate],
            checkpoint_storage=storage,
            name="investment_research_gate",
        )
        .add_edge(validate, gate)
        .build()
    )
    async for event in workflow.run("MSFT", stream=True):
        if event.type == "output":
            print(event.data)


if __name__ == "__main__":
    asyncio.run(main())
