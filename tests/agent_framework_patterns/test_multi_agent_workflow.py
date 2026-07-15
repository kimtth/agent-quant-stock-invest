import asyncio

from tests.agent_framework_patterns.helpers import (
    FakeAsyncCredential,
    FakeFoundryClient,
    configure_foundry_environment,
    load_pattern,
)


def test_multi_agent_workflow_passes_market_context_through_risk_and_writer(monkeypatch, capsys) -> None:
    module = load_pattern("multi-agent-workflow.py")
    client = FakeFoundryClient()
    configure_foundry_environment(monkeypatch)
    monkeypatch.setattr(module, "AzureCliCredential", FakeAsyncCredential)
    monkeypatch.setattr(module, "FoundryChatClient", lambda **kwargs: client)

    asyncio.run(module.main())

    assert [agent.settings["name"] for agent in client.agents] == ["market_context", "risk_review", "brief_writer"]
    assert "Cautious research response." in capsys.readouterr().out