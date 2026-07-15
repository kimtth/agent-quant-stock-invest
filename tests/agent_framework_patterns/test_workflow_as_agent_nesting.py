import asyncio
from types import SimpleNamespace

from tests.agent_framework_patterns.helpers import load_pattern


class Context:
    def __init__(self) -> None:
        self.outputs = []

    async def yield_output(self, output):
        self.outputs.append(output)


def test_nested_workflow_normalizes_last_message_ticker() -> None:
    module = load_pattern("workflow-as-agent-nesting.py")
    context = Context()

    asyncio.run(module.normalize._original_func([SimpleNamespace(text="Research the scope for msft.")], context))

    assert context.outputs == ["Ticker: MSFT; research scope: public fundamentals and risks only."]