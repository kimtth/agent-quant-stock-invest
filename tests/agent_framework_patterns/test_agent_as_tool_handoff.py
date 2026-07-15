import asyncio

from tests.agent_framework_patterns.helpers import (
    FakeAsyncCredential,
    FakeFoundryClient,
    configure_foundry_environment,
    load_pattern,
)


def test_handoff_main_builds_specialists_and_delegation_tools(monkeypatch, capsys) -> None:
    module = load_pattern("agent-as-tool-handoff.py")
    client = FakeFoundryClient()
    configure_foundry_environment(monkeypatch)
    monkeypatch.setattr(module, "AzureCliCredential", FakeAsyncCredential)
    monkeypatch.setattr(module, "FoundryChatClient", lambda **kwargs: client)

    asyncio.run(module.main())

    assert [agent.settings["name"] for agent in client.agents] == [
        "valuation_specialist", "risk_specialist", "portfolio_research_coordinator"
    ]
    assert [tool["name"] for tool in client.agents[-1].settings["tools"]] == [
        "analyse_valuation", "analyse_risks"
    ]
    assert "Cautious research response." in capsys.readouterr().out