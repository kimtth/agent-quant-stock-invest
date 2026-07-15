import asyncio

from tests.agent_framework_patterns.helpers import (
    FakeAsyncCredential,
    FakeFoundryClient,
    configure_foundry_environment,
    load_pattern,
)


def test_error_handling_reports_framework_failure_without_market_claim(monkeypatch, capsys) -> None:
    module = load_pattern("error-handling.py")
    client = FakeFoundryClient()
    configure_foundry_environment(monkeypatch)
    monkeypatch.setattr(module, "AzureCliCredential", FakeAsyncCredential)
    monkeypatch.setattr(module, "FoundryChatClient", lambda **kwargs: client)
    agent = client.as_agent()

    async def failed_run(*args, **kwargs):
        raise module.AgentFrameworkException("unavailable")

    agent.run = failed_run
    monkeypatch.setattr(client, "as_agent", lambda **kwargs: agent)

    asyncio.run(module.main())

    output = capsys.readouterr().out
    assert "Research service failure: unavailable" in output
    assert "No market-data claim was produced." in output