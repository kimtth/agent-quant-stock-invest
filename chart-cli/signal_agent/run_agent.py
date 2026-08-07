"""Entry point that streams dashboard requests through the Agent Framework workflows.

Requests are newline-delimited JSON objects:
  {"kind": "advisory", "payload": <MarketSnapshot>}   -> one advisory report
  {"kind": "backtest", "payload": <BacktestRequest>}  -> progress frames, then a summary
  {"kind": "ask",      "payload": <AskRequest>}       -> one grounded answer
  {"kind": "model",    "payload": <ModelRequest>}     -> the active chat backend

Responses are single lines prefixed with `@@REPORT@@ `; the `kind` field on each
payload tells the dashboard whether it is an advisory, a frame, a summary, an
answer, or a model status.

Modes:
  --serve   read requests from stdin until the stream closes
  --demo    run a synthetic advisory and a synthetic backtest
  --input   read one request from a JSON file
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from . import providers
from .backtest import DEFAULT_PLAN, BacktestEngine
from .models import (
    AskRequest,
    BacktestRequest,
    MarketSnapshot,
    ModelRequest,
    ModelStatus,
)
from .workflow import AskWorkflow, BacktestWorkflow, MarketAdvisoryWorkflow

REPORT_PREFIX = "@@REPORT@@ "
REPO_ROOT = Path(__file__).resolve().parents[2]


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def emit(payload_json: str) -> None:
    sys.stdout.write(REPORT_PREFIX + payload_json + "\n")
    sys.stdout.flush()


class RequestRouter:
    """Owns the chat provider and the workflows, one dashboard request at a time."""

    def __init__(self) -> None:
        self.provider = providers.Provider()
        self.advisory = MarketAdvisoryWorkflow()
        self.backtest = BacktestWorkflow()
        self.ask = AskWorkflow()
        self.advisory_graph: Any = None
        self.backtest_graph: Any = None
        self.ask_graph: Any = None

    def connect(self, provider: providers.Provider | None = None) -> None:
        """Point every workflow at one provider and rebuild its graph."""
        self.provider = provider or providers.from_env()
        for workflow in (self.advisory, self.backtest, self.ask):
            workflow.connect(self.provider)
        detail = f" ({self.advisory.error})" if self.advisory.error else ""
        log(
            f"[workflow] provider={self.provider.name} "
            f"mode={self.advisory.mode}{detail}"
        )
        self.advisory_graph = self.advisory.build()
        self.backtest_graph = self.backtest.build()
        self.ask_graph = self.ask.build()

    async def close(self) -> None:
        await self.provider.close()

    async def dispatch(self, request: dict) -> None:
        kind = request.get("kind", "advisory")
        payload = request.get("payload", request)
        if kind == "backtest":
            await self._run_backtest(payload)
        elif kind == "ask":
            await self._run_ask(payload)
        elif kind == "model":
            await self._run_model(payload)
        else:
            await self._run_advisory(payload)

    async def _last_output(self, graph: Any, message: str) -> str:
        """Run a graph to completion and keep only its final output event."""
        final = ""
        async for event in graph.run(message, stream=True):
            if event.type == "output" and isinstance(event.data, str):
                final = event.data
        return final

    async def _run_advisory(self, payload: dict) -> None:
        final = await self._last_output(self.advisory_graph, json.dumps(payload))
        emit(
            final or self.advisory.empty_report("no workflow output").model_dump_json()
        )

    async def _run_ask(self, payload: dict) -> None:
        request = AskRequest.model_validate(payload)
        final = await self._last_output(self.ask_graph, request.model_dump_json())
        emit(final or self.ask.empty_reply(request.question).model_dump_json())

    async def _run_model(self, payload: dict) -> None:
        """Report the active backend, optionally switching to another one first."""
        request = ModelRequest.model_validate(payload)
        if request.action == "set":
            await self.close()
            self.connect(
                providers.create(
                    request.provider,
                    model=request.model,
                    endpoint=request.endpoint,
                    api_key_var=request.api_key_var,
                )
            )
        status = self.provider.status()
        emit(
            ModelStatus(
                provider=status["provider"],
                model=status["model"],
                endpoint=status["endpoint"],
                mode="agent" if self.advisory.mode == "agent" else "offline",
                available=[*providers.PROVIDERS, "offline"],
                usage=dict(providers.USAGE),
                default_api_key_var=providers.DEFAULT_KEY_VAR,
                error=self.advisory.error or status["error"],
            ).model_dump_json()
        )

    async def _run_backtest(self, payload: dict) -> None:
        """Forward every streamed output immediately so the chart animates live."""
        request = BacktestRequest.model_validate(payload)
        seen_summary = False
        async for event in self.backtest_graph.run(
            request.model_dump_json(), stream=True
        ):
            if event.type != "output" or not isinstance(event.data, str):
                continue
            emit(event.data)
            seen_summary = seen_summary or '"kind":"summary"' in event.data
        if not seen_summary:
            engine = BacktestEngine(request, DEFAULT_PLAN)
            emit(
                engine.summary(
                    mode="offline", verdict="", error="backtest produced no summary"
                ).model_dump_json()
            )


def demo_series(start: float, drift: float, wave: float, count: int) -> list[float]:
    return [
        round(start * (1 + drift * i / count) + wave * math.sin(i / 9), 4)
        for i in range(count)
    ]


def demo_requests() -> list[dict]:
    snapshot = MarketSnapshot(
        generated_at="1970-01-01T00:00:00Z",
        period_label="7D",
        period_days=7,
        assets=[
            {
                "symbol": "BTC",
                "kind": "crypto",
                "price": 88562.0,
                "change_pct": 3.1,
                "history": demo_series(84000, 0.06, 900, 60),
            },
            {
                "symbol": "AAPL",
                "kind": "stock",
                "price": 270.97,
                "change_pct": -2.54,
                "history": demo_series(280, -0.04, 3, 60),
            },
        ],
    )
    backtest = BacktestRequest(
        symbol="AAPL",
        kind_label="stock",
        history=demo_series(150, 0.8, 12, 400),
        timestamps=[],
        initial_capital=10000.0,
        frame_delay_ms=0,
        max_frames=20,
    )
    return [
        {"kind": "model", "payload": {"action": "status"}},
        {"kind": "advisory", "payload": snapshot.model_dump()},
        {
            "kind": "ask",
            "payload": AskRequest(
                question="Which symbol looks strongest right now and why?",
                snapshot=snapshot,
                focus_symbol="BTC",
            ).model_dump(),
        },
        {"kind": "backtest", "payload": backtest.model_dump()},
    ]


async def read_line() -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, sys.stdin.readline)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent Framework market advisory and backtest workflows"
    )
    parser.add_argument(
        "--serve", action="store_true", help="stream requests from stdin"
    )
    parser.add_argument(
        "--demo", action="store_true", help="run a synthetic advisory and backtest"
    )
    parser.add_argument("--input", type=Path, help="read one request from a JSON file")
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env", override=False)

    router = RequestRouter()
    router.connect()

    try:
        if args.demo:
            for request in demo_requests():
                await router.dispatch(request)
            return

        if args.input:
            await router.dispatch(json.loads(args.input.read_text(encoding="utf-8")))
            return

        while True:
            line = await read_line()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except ValueError as exc:
                log(f"[workflow] skipped malformed request: {exc}")
                continue
            try:
                await router.dispatch(request)
            except Exception as exc:  # noqa: BLE001 - keep the server alive for the TUI
                log(f"[workflow] request failed: {exc}")
                emit(
                    router.advisory.empty_report(
                        providers.summarize_error(exc)
                    ).model_dump_json()
                )
            if not args.serve:
                break
    finally:
        await router.close()


if __name__ == "__main__":
    asyncio.run(main())
