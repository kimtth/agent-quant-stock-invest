"""Load a declarative investment research agent from a local YAML definition."""

import asyncio
from pathlib import Path

from agent_framework import Agent


DEFINITION = """kind: PromptAgent
name: declarative-investment-researcher
instructions: >-
  Produce research-only investment briefs. Label assumptions, risks, and limitations.
  Never execute or recommend a transaction.
"""


async def main() -> None:
    try:
        from agent_framework_declarative import AgentFactory
    except ImportError as error:
        raise SystemExit(
            "Install agent-framework-declarative to use this beta pattern."
        ) from error
    path = Path("output/agent_framework/patterns/declarative-investment-agent.yaml")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFINITION, encoding="utf-8")
    agent: Agent = await AgentFactory().create_from_file(path, safe_mode=True)
    async with agent:
        print((await agent.run("Create a cautious ETF research checklist.")).text)


if __name__ == "__main__":
    asyncio.run(main())
