"""Load a declarative workflow that validates a research-only ticker request."""

import asyncio
from pathlib import Path

from agent_framework import Workflow


DEFINITION = """kind: Workflow
name: declarative-investment-intake
description: Validates a research request before analyst review.
"""


async def main() -> None:
    try:
        from agent_framework_declarative import WorkflowFactory
    except ImportError as error:
        raise SystemExit(
            "Install agent-framework-declarative to use this beta pattern."
        ) from error
    path = Path("output/agent_framework/patterns/declarative-investment-workflow.yaml")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFINITION, encoding="utf-8")
    workflow: Workflow = await WorkflowFactory().create_from_file(path, safe_mode=True)
    print(await workflow.run("MSFT research request; analysis only, no order."))


if __name__ == "__main__":
    asyncio.run(main())
