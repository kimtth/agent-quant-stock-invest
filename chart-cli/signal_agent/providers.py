"""Chat-model backends that the chart-cli workflows can run on.

Three providers are supported and can be swapped at runtime from the dashboard
`/model` command:

``foundry``   Microsoft Foundry project endpoint with Azure CLI credentials.
``openai``    Any OpenAI-compatible Chat Completions endpoint with key auth.
``copilot``   The GitHub Copilot CLI client shipped with Agent Framework.

API keys are never accepted as literals: the caller supplies the *name* of an
environment variable, so secrets stay out of the terminal, the log overlay, and
the NDJSON protocol.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, TypeVar

from pydantic import BaseModel

PROVIDERS = ("foundry", "openai", "copilot")
DEFAULT_KEY_VAR = "OPENAI_API_KEY"

# Argument hints published to the dashboard so `/model` help stays in one place.
USAGE: dict[str, str] = {
    "foundry": "[deployment]",
    "openai": "<model> [base-url] [KEY_ENV_VAR]",
    "copilot": "[model]",
    "offline": "",
}

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_STATUS = re.compile(r"[Ee]rror code:\s*(\d{3})")
_MESSAGE = re.compile(r"'message':\s*'([^']{4,400})'")

ModelT = TypeVar("ModelT", bound=BaseModel)

ERROR_LIMIT = 200


def summarize_error(exc: BaseException, limit: int = ERROR_LIMIT) -> str:
    """Reduce an SDK exception to one short line fit for a terminal panel.

    Provider exceptions embed the whole HTTP error document, which floods the
    dashboard overlay; keep the status code and the human-readable message.
    """
    text = " ".join(str(exc).split())
    status = _STATUS.search(text)
    message = _MESSAGE.search(text)
    if message:
        text = message.group(1).strip()
        if status:
            text = f"HTTP {status.group(1)}: {text}"
    elif status:
        text = f"HTTP {status.group(1)}: {text}"
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def parse_model(text: str, schema: type[ModelT]) -> ModelT:
    """Validate `text` against `schema`, tolerating fenced or prose-wrapped JSON.

    Providers without native structured output (GitHub Copilot) answer with a
    JSON object that may be wrapped in a code fence or a sentence.
    """
    candidates = [text]
    fenced = _FENCE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            return schema.model_validate_json(candidate)
        except Exception as exc:  # noqa: BLE001 - try the next candidate shape
            last_error = exc
    raise ValueError(f"no valid JSON payload in model response: {last_error}")


def _json_contract(schema: type[BaseModel]) -> str:
    return (
        "\n\nReply with a single JSON object and nothing else. No prose, no code "
        "fence, no trailing commentary. It must validate against this JSON schema:\n"
        f"{json.dumps(schema.model_json_schema())}"
    )


class Provider:
    """A resolved chat backend plus the agent factory built on top of it."""

    def __init__(
        self,
        name: str = "offline",
        model: str = "",
        endpoint: str = "",
        error: str = "",
    ) -> None:
        self.name = name
        self.model = model
        self.endpoint = endpoint
        self.error = error
        self._client: Any = None
        self._credential: Any = None

    @property
    def available(self) -> bool:
        return self.name in PROVIDERS

    def status(self) -> dict[str, Any]:
        """Non-secret description of the active backend."""
        return {
            "provider": self.name,
            "model": self.model,
            "endpoint": self.endpoint,
            "error": self.error,
        }

    def make_agents(self, specs: dict[str, tuple[str, str, Any]]) -> dict[str, Any]:
        """Build `{key: agent}` for the given specs; return `{}` when unavailable."""
        if not self.available:
            return {}
        try:
            if self.name == "copilot":
                return self._copilot_agents(specs)
            if self._client is None:
                return {}
            return {
                key: self._client.as_agent(
                    name=name,
                    instructions=instructions,
                    default_options={"response_format": schema},
                )
                for key, (name, instructions, schema) in specs.items()
            }
        except Exception as exc:  # noqa: BLE001 - degrade to the offline strategy
            self.error = f"agent setup failed: {summarize_error(exc)}"
            return {}

    def _copilot_agents(self, specs: dict[str, tuple[str, str, Any]]) -> dict[str, Any]:
        from agent_framework_github_copilot import GitHubCopilotAgent

        options: dict[str, Any] | None = {"model": self.model} if self.model else None
        return {
            key: GitHubCopilotAgent(
                instructions + _json_contract(schema),
                name=name,
                default_options=options,
            )
            for key, (name, instructions, schema) in specs.items()
        }

    async def close(self) -> None:
        if self._credential is not None:
            await self._credential.close()
            self._credential = None
        self._client = None


def create(
    name: str = "",
    *,
    model: str = "",
    endpoint: str = "",
    api_key_var: str = "",
) -> Provider:
    """Build a provider, degrading to an offline provider that carries the reason."""
    name = (name or "").strip().lower()
    explicit = name not in ("", "auto")
    if not explicit:
        name = _auto_name()
    if name in ("offline", "rules"):
        return Provider(
            "offline", error="" if explicit else "no chat provider configured"
        )
    if name not in PROVIDERS:
        return Provider("offline", error=f"unknown provider '{name}'")

    try:
        if name == "foundry":
            return _foundry(model, endpoint)
        if name == "openai":
            return _openai(model, endpoint, api_key_var)
        return _copilot(model)
    except Exception as exc:  # noqa: BLE001 - degrade to the offline strategy
        return Provider("offline", error=f"{name} setup failed: {summarize_error(exc)}")


def from_env() -> Provider:
    """Build the provider described by the process environment."""
    return create(
        os.getenv("CHART_CLI_PROVIDER", ""),
        model=os.getenv("CHART_CLI_MODEL", ""),
        endpoint=os.getenv("CHART_CLI_ENDPOINT", ""),
        api_key_var=os.getenv("CHART_CLI_API_KEY_VAR", ""),
    )


def _auto_name() -> str:
    if os.getenv("AZURE_AI_PROJECT_ENDPOINT") and os.getenv(
        "AZURE_AI_MODEL_DEPLOYMENT_NAME"
    ):
        return "foundry"
    if os.getenv(DEFAULT_KEY_VAR):
        return "openai"
    return "offline"


def _foundry(model: str, endpoint: str) -> Provider:
    endpoint = endpoint or os.getenv("AZURE_AI_PROJECT_ENDPOINT", "")
    model = model or os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "")
    if not endpoint or not model:
        return Provider(
            "offline",
            error="AZURE_AI_PROJECT_ENDPOINT/AZURE_AI_MODEL_DEPLOYMENT_NAME not set",
        )

    from agent_framework.foundry import FoundryChatClient
    from azure.identity.aio import AzureCliCredential

    provider = Provider("foundry", model=model, endpoint=endpoint)
    provider._credential = AzureCliCredential()
    provider._client = FoundryChatClient(
        project_endpoint=endpoint,
        model=model,
        credential=provider._credential,
    )
    return provider


def _openai(model: str, endpoint: str, api_key_var: str) -> Provider:
    model = model or os.getenv("OPENAI_MODEL", "")
    endpoint = endpoint or os.getenv("OPENAI_BASE_URL", "")
    api_key_var = api_key_var or DEFAULT_KEY_VAR
    api_key = os.getenv(api_key_var, "")
    if not model:
        return Provider("offline", error="openai provider needs a model name")
    if not api_key:
        return Provider("offline", error=f"environment variable {api_key_var} is empty")

    from agent_framework.openai import OpenAIChatCompletionClient

    provider = Provider("openai", model=model, endpoint=endpoint)
    provider._client = OpenAIChatCompletionClient(
        model,
        api_key=api_key,
        base_url=endpoint or None,
    )
    return provider


def _copilot(model: str) -> Provider:
    model = model or os.getenv("GITHUB_COPILOT_MODEL", "")

    import agent_framework_github_copilot  # noqa: F401 - fail fast when missing

    return Provider("copilot", model=model)
