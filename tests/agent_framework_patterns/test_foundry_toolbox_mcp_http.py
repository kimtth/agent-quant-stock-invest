import asyncio

from tests.agent_framework_patterns.helpers import (
    FakeAsyncCredential,
    FakeFoundryClient,
    configure_foundry_environment,
    load_pattern,
)


def test_toolbox_pattern_limits_mcp_tools_to_read_only_operations(monkeypatch, capsys) -> None:
    module = load_pattern("foundry-toolbox-mcp-http.py")
    client = FakeFoundryClient()
    created = []
    configure_foundry_environment(monkeypatch)
    monkeypatch.setenv("FOUNDRY_INVESTMENT_TOOLBOX_URL", "https://tools.example.test/mcp")
    monkeypatch.setattr(module, "AzureCliCredential", FakeAsyncCredential)
    monkeypatch.setattr(module, "FoundryChatClient", lambda **kwargs: client)
    monkeypatch.setattr(module, "MCPStreamableHTTPTool", lambda **kwargs: created.append(kwargs) or kwargs)

    asyncio.run(module.main())

    assert created[0]["allowed_tools"] == ["search_filings", "get_market_snapshot"]
    assert created[0]["approval_mode"] == "never_require"
    assert "Cautious research response." in capsys.readouterr().out