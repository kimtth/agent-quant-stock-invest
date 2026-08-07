"""Shared agent plumbing for the workflows in this package.

Every workflow builds a small set of agents on the active provider, asks one of
them for a structured answer, and falls back to a deterministic rule when the
provider is missing or the call fails.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, NamedTuple, TypeVar

from pydantic import BaseModel

from .. import providers

ModelT = TypeVar("ModelT", bound=BaseModel)


def utc_now() -> str:
    """Timestamp format shared by every payload sent to the dashboard."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AgentSpec(NamedTuple):
    """How to build one agent: its name, its system prompt, its output schema."""

    name: str
    instructions: str
    schema: type[BaseModel]


class AgentFailure(RuntimeError):
    """An agent could not be reached, or answered off-contract.

    The message is short enough for a terminal panel, so callers can put it
    straight into the payload they return.
    """


class AgentTeam:
    """The agents one workflow needs, plus a uniform way to call them.

    A team is always usable: with no provider connected `ready` is False and the
    workflow takes its rule-based path instead of raising.
    """

    def __init__(self, specs: Mapping[str, AgentSpec]) -> None:
        self.specs = dict(specs)
        self.agents: dict[str, Any] = {}
        self.provider = providers.Provider()

    def connect(self, provider: providers.Provider) -> None:
        """Build every agent on `provider`; leave the team empty on failure."""
        self.provider = provider
        self.agents = provider.make_agents(
            {key: tuple(spec) for key, spec in self.specs.items()}
        )

    @property
    def ready(self) -> bool:
        return bool(self.agents)

    @property
    def mode(self) -> str:
        return "agent" if self.agents else "offline"

    @property
    def error(self) -> str:
        return self.provider.error

    async def run(self, key: str, prompt: str, schema: type[ModelT]) -> ModelT:
        """Send `prompt` to one agent and validate the reply against `schema`.

        Every error path raises `AgentFailure`, so callers need one `except`
        clause rather than one per SDK exception type.
        """
        agent = self.agents.get(key)
        if agent is None:
            raise AgentFailure(f"{key} agent is not connected")
        try:
            response = await agent.run(prompt)
            return providers.parse_model(response.text, schema)
        except Exception as exc:  # noqa: BLE001 - one short message for the caller
            raise AgentFailure(
                f"{self.specs[key].name} failed: {providers.summarize_error(exc)}"
            ) from exc
