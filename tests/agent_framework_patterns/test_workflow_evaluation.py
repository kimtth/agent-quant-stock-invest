import asyncio

from tests.agent_framework_patterns.helpers import (
    FakeAsyncCredential,
    FakeFoundryClient,
    configure_foundry_environment,
    load_pattern,
)


def test_workflow_evaluation_passes_local_risk_evaluator_to_framework(monkeypatch, capsys) -> None:
    module = load_pattern("workflow-evaluation.py")
    client = FakeFoundryClient()
    captured = {}

    async def fake_evaluate_workflow(**kwargs):
        captured.update(kwargs)
        return "all checks passed"

    configure_foundry_environment(monkeypatch)
    monkeypatch.setattr(module, "AzureCliCredential", FakeAsyncCredential)
    monkeypatch.setattr(module, "FoundryChatClient", lambda **kwargs: client)
    monkeypatch.setattr(module, "evaluate_workflow", fake_evaluate_workflow)

    asyncio.run(module.main())

    assert captured["queries"] == ["Research an equity ETF."]
    assert "all checks passed" in capsys.readouterr().out