from tests.agent_framework_patterns.helpers import (
    FakeFoundryClient,
    FakeSyncCredential,
    configure_foundry_environment,
    load_pattern,
)


def test_devui_main_registers_agent_and_honors_configured_port(monkeypatch) -> None:
    module = load_pattern("devui-local-development.py")
    client = FakeFoundryClient()
    served = {}
    configure_foundry_environment(monkeypatch)
    monkeypatch.setenv("DEV_UI_PORT", "9000")
    monkeypatch.setattr(module, "AzureCliCredential", FakeSyncCredential)
    monkeypatch.setattr(module, "FoundryChatClient", lambda **kwargs: client)

    import agent_framework.devui

    monkeypatch.setattr(agent_framework.devui, "serve", lambda **kwargs: served.update(kwargs))
    module.main()

    assert served["port"] == 9000 and served["auto_open"] is False
    assert served["entities"] == client.agents