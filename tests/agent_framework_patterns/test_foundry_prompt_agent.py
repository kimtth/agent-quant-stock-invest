import asyncio

from tests.agent_framework_patterns.helpers import (
    FakeAsyncCredential,
    FakeFoundryClient,
    configure_foundry_environment,
    load_pattern,
)


def test_prompt_agent_pattern_serializes_generated_definition(monkeypatch, capsys) -> None:
    module = load_pattern("foundry-prompt-agent.py")
    client = FakeFoundryClient()

    class Definition:
        def as_dict(self):
            return {"kind": "PromptAgent", "name": "publishable_investment_researcher"}

    configure_foundry_environment(monkeypatch)
    monkeypatch.setattr(module, "AzureCliCredential", FakeAsyncCredential)
    monkeypatch.setattr(module, "FoundryChatClient", lambda **kwargs: client)
    monkeypatch.setattr(module, "to_prompt_agent", lambda agent: Definition())

    asyncio.run(module.main())

    assert '"kind": "PromptAgent"' in capsys.readouterr().out