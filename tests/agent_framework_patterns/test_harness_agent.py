import asyncio

from tests.agent_framework_patterns.helpers import (
    FakeAsyncCredential,
    FakeFoundryClient,
    configure_foundry_environment,
    load_pattern,
)


def test_harness_pattern_creates_session_aware_research_agent(monkeypatch, capsys) -> None:
    module = load_pattern("harness-agent.py")
    client = FakeFoundryClient()
    created = []
    configure_foundry_environment(monkeypatch)
    monkeypatch.setattr(module, "AzureCliCredential", FakeAsyncCredential)
    monkeypatch.setattr(module, "FoundryChatClient", lambda **kwargs: client)
    monkeypatch.setattr(module, "AgentSession", object)
    monkeypatch.setattr(module, "create_harness_agent", lambda _client, **kwargs: created.append(client.as_agent(**kwargs)) or created[-1])

    asyncio.run(module.main())

    assert created[0].settings["name"] == "investment_research_harness"
    assert created[0].run_calls[0][1]["session"].__class__ is object
    assert "Cautious research response." in capsys.readouterr().out