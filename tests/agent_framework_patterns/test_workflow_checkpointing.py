import asyncio

import pytest

from tests.agent_framework_patterns.helpers import load_pattern


class Context:
    def __init__(self) -> None:
        self.messages = []
        self.outputs = []

    async def send_message(self, message):
        self.messages.append(message)

    async def yield_output(self, output):
        self.outputs.append(output)


def test_checkpoint_workflow_validates_ticker_and_enforces_review_gate() -> None:
    module = load_pattern("workflow-checkpointing.py")
    context = Context()

    asyncio.run(module.validate._original_func(" msft ", context))
    asyncio.run(module.gate._original_func(context.messages[0], context))

    assert context.messages == ["Validated MSFT; collect dated public research before analysis."]
    assert context.outputs == [
        "Validated MSFT; collect dated public research before analysis. Human review is required; no order can be placed by this workflow."
    ]
    with pytest.raises(ValueError, match="valid ticker"):
        asyncio.run(module.validate._original_func("MSFT!", Context()))