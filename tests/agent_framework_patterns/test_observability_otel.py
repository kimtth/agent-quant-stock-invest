import asyncio

from tests.agent_framework_patterns.helpers import (
    FakeAsyncCredential,
    FakeFoundryClient,
    configure_foundry_environment,
    load_pattern,
)


def test_otel_pattern_keeps_console_exporters_off_by_default(monkeypatch, capsys) -> None:
    module = load_pattern("observability-otel.py")
    client = FakeFoundryClient()
    configured = {}
    configure_foundry_environment(monkeypatch)
    monkeypatch.setattr(module, "configure_otel_providers", lambda **kwargs: configured.update(kwargs))
    monkeypatch.setattr(module, "AzureCliCredential", FakeAsyncCredential)
    monkeypatch.setattr(module, "FoundryChatClient", lambda **kwargs: client)

    asyncio.run(module.main())

    assert configured == {"enable_console_exporters": False}
    assert "Cautious research response." in capsys.readouterr().out