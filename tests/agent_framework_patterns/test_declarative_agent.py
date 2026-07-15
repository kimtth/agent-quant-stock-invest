import asyncio
import sys
from pathlib import Path
from types import ModuleType

from tests.agent_framework_patterns.helpers import FakeAgent, load_pattern


def test_declarative_agent_writes_definition_and_runs_loaded_agent(monkeypatch, tmp_path, capsys) -> None:
    module = load_pattern("declarative-agent.py")
    agent = FakeAgent()

    class Factory:
        async def create_from_file(self, path, safe_mode):
            assert safe_mode and Path(path).read_text(encoding="utf-8") == module.DEFINITION
            return agent

    dependency = ModuleType("agent_framework_declarative")
    dependency.AgentFactory = Factory
    monkeypatch.setitem(sys.modules, "agent_framework_declarative", dependency)
    monkeypatch.chdir(tmp_path)

    asyncio.run(module.main())

    assert "kind: PromptAgent" in (tmp_path / "output/agent_framework/patterns/declarative-investment-agent.yaml").read_text()
    assert agent.run_calls[0][0] == "Create a cautious ETF research checklist."
    assert "Cautious research response." in capsys.readouterr().out