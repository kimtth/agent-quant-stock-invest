"""Agent Framework orchestration for REPL-driven investment research."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent_framework import (
    FileCheckpointStorage,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowViz,
    executor,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from typing_extensions import Never

from .research_repl import DATASET_SIGNALS
from .tools import AgentTools, WORK_DIR


class QuantInvestWorkflow:
    """Foundry agents that author, execute, and evaluate a signal script."""

    def __init__(self) -> None:
        self.work_dir = WORK_DIR
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.storage = FileCheckpointStorage(Path("checkpoints"))
        self.agents: dict[str, Any] = {}
        self.tools = AgentTools(self.work_dir)

    async def create_workflow(self) -> Workflow:
        client = FoundryChatClient(
            project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=AzureCliCredential(),
        )
        self.agents = {
            "data": client.as_agent(
                name="stock_data_fetcher",
                instructions=(
                    "Fetch the requested historical OHLCV data with fetch_stock_data. "
                    "Use the ticker and dates from the user request, call the tool exactly once, "
                    "and report only its result. This is research, not investment advice."
                ),
                tools=[self.tools.fetch_stock_data],
            ),
            "signal": client.as_agent(
                name="signal_generator",
                instructions=(
                    "Design a technical-analysis hypothesis from the research request, then author "
                    "Python code and execute it with run_python_repl. The code must read INPUT_PATH "
                    "and write a CSV to OUTPUT_PATH containing one row per input row and exactly "
                    "BuySignal, SellSignal, and Description columns. Use only pandas as pd, numpy "
                    "as np, and ta; do not access the network, shell, environment variables, or any "
                    "other files. Do not return code in prose: call the REPL. When it reports an "
                    "error, correct the code and retry up to three times. This is research only."
                ),
                tools=[self.tools.run_python_repl],
            ),
            "backtest": client.as_agent(
                name="backtester",
                instructions=(
                    "Call backtest_strategy once for the validated signal file. Extract an initial "
                    "capital amount from the request when it is present; otherwise use 10000. Report "
                    "the returned metrics and state that they are historical research, not advice."
                ),
                tools=[self.tools.backtest_strategy],
            ),
            "plot": client.as_agent(
                name="performance_plotter",
                instructions="Call plot_performance once after a successful backtest and report its result.",
                tools=[self.tools.plot_performance],
            ),
            "summary": client.as_agent(
                name="summary_reporter",
                instructions=(
                    "Write a concise Markdown research report from the supplied workflow state. Include "
                    "the generated-strategy outcome, backtest metrics when available, assumptions, "
                    "limitations, and risks. Never advise, recommend, or execute trades."
                ),
            ),
        }

        @executor(id="fetch_data")
        async def fetch(task: str, ctx: WorkflowContext[str]) -> None:
            self.tools.clear_run_artifacts()
            result = await self.agents["data"].run(task)
            await ctx.send_message(self._state(task, data=result.text))

        @executor(id="generate_signals")
        async def signal(message: str, ctx: WorkflowContext[str]) -> None:
            state = self._parse_state(message)
            prompt = (
                f"Original request:\n{state['task']}\n\n"
                f"Data-agent result:\n{state['data']}"
            )
            result = await self.agents["signal"].run(prompt)
            state["signal"] = result.text
            await ctx.send_message(self._state(**state))

        @executor(id="backtest")
        async def run_backtest(message: str, ctx: WorkflowContext[str]) -> None:
            state = self._parse_state(message)
            result = await self.agents["backtest"].run(
                f"Original request:\n{state['task']}\n\n"
                f"Signal-agent result:\n{state['signal']}"
            )
            state["backtest"] = result.text
            await ctx.send_message(self._state(**state))

        @executor(id="plot_performance")
        async def create_plot(message: str, ctx: WorkflowContext[str]) -> None:
            state = self._parse_state(message)
            result = await self.agents["plot"].run(state["backtest"])
            state["plot"] = result.text
            await ctx.send_message(self._state(**state))

        @executor(id="summary_report")
        async def summary(message: str, ctx: WorkflowContext[Never, str]) -> None:
            await ctx.yield_output((await self.agents["summary"].run(message)).text)

        def valid(message: str) -> bool:
            return self._has_signals(message)

        workflow = (
            WorkflowBuilder(start_executor=fetch, checkpoint_storage=self.storage)
            .add_edge(fetch, signal)
            .add_edge(signal, run_backtest, condition=valid)
            .add_edge(run_backtest, create_plot)
            .add_edge(create_plot, summary)
            .add_edge(signal, summary, condition=lambda message: not valid(message))
            .build()
        )
        (self.work_dir / "workflow_diagram.mmd").write_text(
            WorkflowViz(workflow).to_mermaid(), encoding="utf-8"
        )
        return workflow

    async def run_task(
        self, workflow: Workflow, task: str, start_from_checkpoint: bool = False
    ) -> str:
        if start_from_checkpoint:
            checkpoints = await self.storage.list_checkpoints()
            if not checkpoints:
                return "No checkpoints available."
            latest = max(checkpoints, key=lambda item: item.timestamp)
            events = workflow.run(
                checkpoint_id=latest.checkpoint_id,
                checkpoint_storage=self.storage,
                stream=True,
            )
        else:
            events = workflow.run(task, stream=True)
        final = ""
        async for event in events:
            if event.type == "output" and isinstance(event.data, str):
                final = event.data
                print(final)
        return final

    def _has_signals(self, message: Any) -> bool:
        self._parse_state(message)
        return (self.work_dir / DATASET_SIGNALS).is_file()

    @staticmethod
    def _state(task: str, **updates: str) -> str:
        state = {
            "task": task,
            "data": "",
            "signal": "",
            "backtest": "",
            "plot": "",
        }
        state.update(updates)
        return json.dumps(state)

    @staticmethod
    def _parse_state(message: Any) -> dict[str, str]:
        try:
            state = json.loads(str(message))
        except (TypeError, ValueError):
            state = {"task": str(message)}
        return {
            key: str(state.get(key, ""))
            for key in ("task", "data", "signal", "backtest", "plot")
        }
