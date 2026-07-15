import asyncio
from types import SimpleNamespace

from tests.agent_framework_patterns.helpers import (
    FakeAsyncCredential,
    FakeFoundryClient,
    configure_foundry_environment,
    load_pattern,
)


def test_foundry_evaluation_uses_groundedness_and_relevance(monkeypatch, capsys) -> None:
    module = load_pattern("agent-evaluation-foundry.py")
    client = FakeFoundryClient()
    captured = {}

    async def fake_evaluate_agent(**kwargs):
        captured.update(kwargs)
        return [SimpleNamespace(provider="test", passed=2, total=2)]

    configure_foundry_environment(monkeypatch)
    monkeypatch.setattr(module, "AzureCliCredential", FakeAsyncCredential)
    monkeypatch.setattr(module, "FoundryChatClient", lambda **kwargs: client)
    monkeypatch.setattr(module, "FoundryEvals", lambda **kwargs: kwargs)
    monkeypatch.setattr(module, "evaluate_agent", fake_evaluate_agent)

    asyncio.run(module.main())

    assert captured["evaluators"]["evaluators"] == ["groundedness", "relevance"]
    assert client.agents[0].run_calls == [
        (
            "Draft a cautious equity research brief with assumptions, two risks, "
            "and two limitations. Use at most 150 words.",
            {"stream": False},
        )
    ]
    assert "Cautious research response." in capsys.readouterr().out