import asyncio

from tests.agent_framework_patterns.helpers import (
    FakeAsyncCredential,
    FakeFoundryClient,
    configure_foundry_environment,
    load_pattern,
)


def test_bing_pattern_uses_configured_foundry_connection(monkeypatch, capsys) -> None:
    module = load_pattern("hosted-bing-search.py")
    client = FakeFoundryClient()
    configure_foundry_environment(monkeypatch)
    monkeypatch.setenv("FOUNDRY_BING_CONNECTION_ID", "bing-connection")
    monkeypatch.setattr(module, "AzureCliCredential", FakeAsyncCredential)
    monkeypatch.setattr(module, "FoundryChatClient", lambda **kwargs: client)

    asyncio.run(module.main())

    assert client.tool_requests == [("bing", {"connection_id": "bing-connection"})]
    assert client.agents[0].settings["tools"][0]["kind"] == "bing"
    assert "Cautious research response." in capsys.readouterr().out