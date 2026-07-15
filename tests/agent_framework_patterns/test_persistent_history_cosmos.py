import asyncio
import sys
from types import ModuleType

from tests.agent_framework_patterns.helpers import (
    FakeAsyncCredential,
    FakeFoundryClient,
    configure_foundry_environment,
    load_pattern,
)


def test_cosmos_pattern_builds_history_provider_from_environment(monkeypatch, capsys) -> None:
    module = load_pattern("persistent-history-cosmos.py")
    client = FakeFoundryClient()
    configured = []

    class Provider:
        def __init__(self, **kwargs):
            configured.append(kwargs)

    dependency = ModuleType("agent_framework_azure_cosmos")
    dependency.CosmosHistoryProvider = Provider
    configure_foundry_environment(monkeypatch)
    monkeypatch.setenv("AZURE_COSMOS_ENDPOINT", "https://cosmos.example.test")
    monkeypatch.setitem(sys.modules, "agent_framework_azure_cosmos", dependency)
    monkeypatch.setattr(module, "DefaultAzureCredential", FakeAsyncCredential)
    monkeypatch.setattr(module, "FoundryChatClient", lambda **kwargs: client)
    monkeypatch.setattr(module, "AgentSession", object)

    asyncio.run(module.main())

    assert configured[0]["database_name"] == "investment-agents"
    assert configured[0]["container_name"] == "research-history"
    assert "Cautious research response." in capsys.readouterr().out