import asyncio
import json

from tests.agent_framework_patterns.helpers import (
    FakeAsyncCredential,
    FakeFoundryClient,
    configure_foundry_environment,
    load_pattern,
)


def test_session_history_loads_existing_state_and_persists_updated_state(monkeypatch, tmp_path, capsys) -> None:
    module = load_pattern("session-history-persistence.py")
    client = FakeFoundryClient()

    class Session:
        loaded = None

        @classmethod
        def from_dict(cls, value):
            cls.loaded = value
            return cls()

        def to_dict(self):
            return {"turns": 2}

    path = tmp_path / "output/agent_framework/patterns/research_session.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"turns": 1}), encoding="utf-8")
    configure_foundry_environment(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "AgentSession", Session)
    monkeypatch.setattr(module, "AzureCliCredential", FakeAsyncCredential)
    monkeypatch.setattr(module, "FoundryChatClient", lambda **kwargs: client)

    asyncio.run(module.main())

    assert Session.loaded == {"turns": 1}
    assert json.loads(path.read_text(encoding="utf-8")) == {"turns": 2}
    assert "Cautious research response." in capsys.readouterr().out