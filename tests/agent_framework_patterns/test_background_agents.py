import asyncio

from tests.agent_framework_patterns.helpers import (
    FakeAsyncCredential,
    FakeFoundryClient,
    configure_foundry_environment,
    load_pattern,
)


def test_background_harness_agents_are_registered_with_parent(monkeypatch, capsys) -> None:
    module = load_pattern("background-agents.py")
    client = FakeFoundryClient()
    created = []

    def fake_harness(_client, **settings):
        agent = client.as_agent(**settings)
        created.append(agent)
        return agent

    configure_foundry_environment(monkeypatch)
    monkeypatch.setattr(module, "AzureCliCredential", FakeAsyncCredential)
    monkeypatch.setattr(module, "FoundryChatClient", lambda **kwargs: client)
    monkeypatch.setattr(module, "create_harness_agent", fake_harness)
    monkeypatch.setattr(module, "AgentSession", object)

    asyncio.run(module.main())

    assert [agent.settings["name"] for agent in created] == [
        "fundamentals_researcher", "risk_researcher", "investment_orchestrator"
    ]
    assert created[-1].settings["background_agents"] == created[:2]
    assert "Cautious research response." in capsys.readouterr().out