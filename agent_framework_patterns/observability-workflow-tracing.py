"""Trace deterministic investment research workflow stages with OpenTelemetry."""

import asyncio
import os
from typing_extensions import Never

from agent_framework import WorkflowBuilder, WorkflowContext, executor
from agent_framework.observability import configure_otel_providers


@executor(id="validate_data_freshness")
async def validate(as_of_date: str, ctx: WorkflowContext[str]) -> None:
    await ctx.send_message(f"Data as of {as_of_date} validated for research use.")


@executor(id="risk_disclosure")
async def disclose(message: str, ctx: WorkflowContext[Never, str]) -> None:
    await ctx.yield_output(
        f"{message} Risks, assumptions, and limitations must be reviewed by a human; no orders are permitted."
    )


async def main() -> None:
    configure_otel_providers(
        enable_console_exporters=os.getenv("ENABLE_CONSOLE_OTEL_EXPORTERS", "").lower()
        in {"1", "true", "yes"}
    )
    workflow = (
        WorkflowBuilder(
            start_executor=validate,
            output_from=[disclose],
            name="traced_investment_workflow",
        )
        .add_edge(validate, disclose)
        .build()
    )
    async for event in workflow.run("2026-07-15", stream=True):
        if event.type == "output":
            print(event.data)


if __name__ == "__main__":
    asyncio.run(main())
