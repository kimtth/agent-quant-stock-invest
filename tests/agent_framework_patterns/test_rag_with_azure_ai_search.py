import asyncio
import sys
from types import ModuleType

from tests.agent_framework_patterns.helpers import (
    FakeAsyncCredential,
    FakeFoundryClient,
    configure_foundry_environment,
    load_pattern,
)


def test_ai_search_pattern_uses_semantic_index_context(monkeypatch, capsys) -> None:
    module = load_pattern("rag-with-azure-ai-search.py")
    client = FakeFoundryClient()
    configured = []

    class Provider:
        def __init__(self, **kwargs):
            configured.append(kwargs)

    dependency = ModuleType("agent_framework_azure_ai_search")
    dependency.AzureAISearchContextProvider = Provider
    configure_foundry_environment(monkeypatch)
    monkeypatch.setenv("AZURE_AI_SEARCH_ENDPOINT", "https://search.example.test")
    monkeypatch.setenv("AZURE_AI_SEARCH_INDEX", "filings")
    monkeypatch.setitem(sys.modules, "agent_framework_azure_ai_search", dependency)
    monkeypatch.setattr(module, "DefaultAzureCredential", FakeAsyncCredential)
    monkeypatch.setattr(module, "FoundryChatClient", lambda **kwargs: client)

    asyncio.run(module.main())

    assert configured[0]["mode"] == "semantic"
    assert configured[0]["index_name"] == "filings"
    assert "Cautious research response." in capsys.readouterr().out