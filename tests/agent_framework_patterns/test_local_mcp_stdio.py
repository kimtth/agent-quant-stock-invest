import asyncio

from tests.agent_framework_patterns.helpers import (
    FakeAsyncCredential,
    FakeFoundryClient,
    configure_foundry_environment,
    load_pattern,
)


def test_local_mcp_pattern_configures_only_price_history_tool(monkeypatch, capsys) -> None:
    module = load_pattern("local-mcp-stdio.py")
    client = FakeFoundryClient()
    created = []
    configure_foundry_environment(monkeypatch)
    monkeypatch.setenv("MARKET_DATA_MCP_COMMAND", "python")
    monkeypatch.setenv("MARKET_DATA_MCP_ARGS", "server.py --offline")
    monkeypatch.setattr(module, "AzureCliCredential", FakeAsyncCredential)
    monkeypatch.setattr(module, "FoundryChatClient", lambda **kwargs: client)
    monkeypatch.setattr(module, "MCPStdioTool", lambda **kwargs: created.append(kwargs) or kwargs)

    asyncio.run(module.main())

    assert created[0]["args"] == ["server.py", "--offline"]
    assert created[0]["allowed_tools"] == ["get_price_history"]
    assert "Cautious research response." in capsys.readouterr().out