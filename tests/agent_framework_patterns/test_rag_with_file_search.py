import asyncio

from tests.agent_framework_patterns.helpers import (
    FakeAsyncCredential,
    FakeFoundryClient,
    configure_foundry_environment,
    load_pattern,
)


def test_file_search_pattern_uses_configured_vector_store(monkeypatch, capsys) -> None:
    module = load_pattern("rag-with-file-search.py")
    client = FakeFoundryClient()
    configure_foundry_environment(monkeypatch)
    monkeypatch.setenv("FOUNDRY_INVESTMENT_VECTOR_STORE_ID", "vector-store")
    monkeypatch.setattr(module, "AzureCliCredential", FakeAsyncCredential)
    monkeypatch.setattr(module, "FoundryChatClient", lambda **kwargs: client)

    asyncio.run(module.main())

    assert client.tool_requests == [("file_search", {"vector_store_ids": ["vector-store"]})]
    assert "Cautious research response." in capsys.readouterr().out