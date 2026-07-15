"""Offline doubles shared by the pattern behavior tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PATTERNS = ROOT / "agent_framework_patterns"


def load_pattern(script_name: str):
    """Load a hyphenated standalone pattern without executing its main block."""
    path = PATTERNS / script_name
    spec = importlib.util.spec_from_file_location(
        f"pattern_{script_name.replace('-', '_').replace('.py', '')}", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configure_foundry_environment(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_AI_PROJECT_ENDPOINT", "https://example.test/projects/investment")
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "test-model")


class FakeResponse:
    def __init__(self, text: str = "Cautious research response.") -> None:
        self.text = text


class FakeAgent:
    def __init__(self, response_text: str = "Cautious research response.", **settings: Any) -> None:
        self.response_text = response_text
        self.settings = settings
        self.run_calls: list[tuple[str, dict[str, Any]]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        return None

    def as_tool(self, **settings: Any) -> dict[str, Any]:
        return {"agent": self, **settings}

    def run(self, prompt: str, *, stream: bool = False, **kwargs: Any):
        self.run_calls.append((prompt, {"stream": stream, **kwargs}))
        if stream:
            async def updates():
                yield FakeResponse("First update. ")
                yield FakeResponse("Second update.")

            return updates()

        async def response() -> FakeResponse:
            return FakeResponse(self.response_text)

        return response()


class FakeFoundryClient:
    def __init__(self, **settings: Any) -> None:
        self.settings = settings
        self.agents: list[FakeAgent] = []
        self.tool_requests: list[tuple[str, dict[str, Any]]] = []

    def as_agent(self, **settings: Any) -> FakeAgent:
        agent = FakeAgent(**settings)
        self.agents.append(agent)
        return agent

    def get_bing_grounding_tool(self, **settings: Any) -> dict[str, Any]:
        self.tool_requests.append(("bing", settings))
        return {"kind": "bing", **settings}

    def get_file_search_tool(self, **settings: Any) -> dict[str, Any]:
        self.tool_requests.append(("file_search", settings))
        return {"kind": "file_search", **settings}


class FakeAsyncCredential:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeSyncCredential:
    pass