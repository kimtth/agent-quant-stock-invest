import asyncio
import sys
from pathlib import Path
from types import ModuleType

from tests.agent_framework_patterns.helpers import load_pattern


def test_declarative_workflow_writes_definition_and_runs_loaded_workflow(monkeypatch, tmp_path, capsys) -> None:
    module = load_pattern("declarative-workflow.py")

    class Workflow:
        async def run(self, request):
            assert request.startswith("MSFT research request")
            return "validated"

    class Factory:
        async def create_from_file(self, path, safe_mode):
            assert safe_mode and Path(path).read_text(encoding="utf-8") == module.DEFINITION
            return Workflow()

    dependency = ModuleType("agent_framework_declarative")
    dependency.WorkflowFactory = Factory
    monkeypatch.setitem(sys.modules, "agent_framework_declarative", dependency)
    monkeypatch.chdir(tmp_path)

    asyncio.run(module.main())

    assert "kind: Workflow" in (tmp_path / "output/agent_framework/patterns/declarative-investment-workflow.yaml").read_text()
    assert "validated" in capsys.readouterr().out