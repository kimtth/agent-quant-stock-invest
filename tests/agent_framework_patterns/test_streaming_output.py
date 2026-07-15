import asyncio

from tests.agent_framework_patterns.helpers import (
    FakeAsyncCredential,
    FakeFoundryClient,
    configure_foundry_environment,
    load_pattern,
)


def test_streaming_pattern_prints_each_nonempty_update(monkeypatch, capsys) -> None:
    module = load_pattern("streaming-output.py")
    client = FakeFoundryClient()
    configure_foundry_environment(monkeypatch)
    monkeypatch.setattr(module, "AzureCliCredential", FakeAsyncCredential)
    monkeypatch.setattr(module, "FoundryChatClient", lambda **kwargs: client)

    asyncio.run(module.main())

    assert capsys.readouterr().out == "First update. Second update.\n"