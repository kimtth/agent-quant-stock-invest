import asyncio
import sys
from types import ModuleType

from tests.agent_framework_patterns.helpers import (
    FakeAsyncCredential,
    FakeFoundryClient,
    configure_foundry_environment,
    load_pattern,
)


def test_azure_monitor_pattern_disables_sensitive_telemetry(monkeypatch, capsys) -> None:
    module = load_pattern("observability-azure-monitor.py")
    client = FakeFoundryClient()
    configured = {}
    dependency = ModuleType("agent_framework.observability")
    dependency.configure_azure_monitor = lambda **kwargs: configured.update(kwargs)
    configure_foundry_environment(monkeypatch)
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=test")
    monkeypatch.setitem(sys.modules, "agent_framework.observability", dependency)
    monkeypatch.setattr(module, "AzureCliCredential", FakeAsyncCredential)
    monkeypatch.setattr(module, "FoundryChatClient", lambda **kwargs: client)

    asyncio.run(module.main())

    assert configured["enable_sensitive_telemetry"] is False
    assert "Cautious research response." in capsys.readouterr().out