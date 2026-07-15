import asyncio

from tests.agent_framework_patterns.helpers import load_pattern


class Context:
    def __init__(self) -> None:
        self.messages = []
        self.outputs = []

    async def send_message(self, message):
        self.messages.append(message)

    async def yield_output(self, output):
        self.outputs.append(output)


def test_traced_workflow_validates_freshness_then_requires_human_review() -> None:
    module = load_pattern("observability-workflow-tracing.py")
    context = Context()

    asyncio.run(module.validate._original_func("2026-07-15", context))
    asyncio.run(module.disclose._original_func(context.messages[0], context))

    assert context.outputs == [
        "Data as of 2026-07-15 validated for research use. Risks, assumptions, and limitations must be reviewed by a human; no orders are permitted."
    ]