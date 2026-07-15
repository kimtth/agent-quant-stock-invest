"""Agent Framework orchestration and deterministic artifact composition."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf
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
from pydantic import BaseModel
from typing_extensions import Never

from .models import IDEAS, StrategyRun, WorkflowRequest, WorkflowResult
from .tools import (
    AgentTools,
    DATASET_SIGNALS,
    WORK_DIR,
    backtest,
    generate_signals,
    plot,
    safe_name,
)


class ArtifactPipeline:
    """Repeatable artifact generation that does not require an LLM response."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def run(self, request: WorkflowRequest) -> WorkflowResult:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        catalog = self.output_dir / "strategy_ideas.json"
        catalog.write_text(
            json.dumps([idea.model_dump() for idea in IDEAS], indent=2),
            encoding="utf-8",
        )
        runs = [self._run(request, idea) for idea in request.strategies or IDEAS]
        return WorkflowResult(
            ticker=request.ticker, strategy_ideas_file=catalog, runs=runs
        )

    def _run(self, request: WorkflowRequest, idea) -> StrategyRun:
        directory = self.output_dir / safe_name(idea.name)
        directory.mkdir(parents=True, exist_ok=True)
        frame = yf.download(
            request.ticker,
            start=request.start_date,
            end=request.end_date,
            auto_adjust=False,
            progress=False,
        )
        if frame.empty:
            raise ValueError(f"No data returned for {request.ticker}.")
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
        data = directory / "stock_data.csv"
        frame.reset_index().to_csv(data, index=False)
        buy, sell = generate_signals(pd.read_csv(data), idea)
        signals = directory / "stock_signals.csv"
        pd.DataFrame(
            {
                "BuySignal": buy.fillna(False),
                "SellSignal": sell.fillna(False),
                "Description": idea.description,
            }
        ).to_csv(signals, index=False)
        metrics, results, metric_file = backtest(directory, request.initial_capital)
        return StrategyRun(
            strategy=idea,
            metrics=metrics,
            output_directory=directory,
            stock_data_file=data,
            signals_file=signals,
            results_file=results,
            metrics_file=metric_file,
            plot_file=plot(directory),
        )


def generate_reproducible_output(
    request: WorkflowRequest, output_dir: Path
) -> WorkflowResult:
    return ArtifactPipeline(output_dir).run(request)


class AgentCompletedResult(BaseModel):
    success: bool
    message: str


class QuantInvestWorkflow:
    """Foundry-agent executor graph with conditional backtesting and checkpoints."""

    def __init__(self) -> None:
        self.work_dir = WORK_DIR
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.storage = FileCheckpointStorage(Path("checkpoints"))
        self.agents: dict[str, Any] = {}

    async def create_workflow(self) -> Workflow:
        client = FoundryChatClient(
            project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=AzureCliCredential(),
        )
        tools, options = AgentTools(), {"response_format": AgentCompletedResult}
        self.agents = {
            "data": client.as_agent(
                name="stock_data_fetcher",
                instructions="Fetch requested OHLCV data; report research results only.",
                tools=[tools.fetch_stock_data],
                default_options=options,
            ),
            "signal": client.as_agent(
                name="signal_generator",
                instructions="Create BuySignal, SellSignal, and Description using pandas and ta; retry errors up to three times.",
                tools=[tools.execute_python_code],
                default_options=options,
            ),
            "backtest": client.as_agent(
                name="backtester",
                instructions="Call the backtest tool and report returned metrics.",
                tools=[tools.backtest_strategy],
                default_options=options,
            ),
            "summary": client.as_agent(
                name="summary_reporter",
                instructions="Write concise research-only Markdown with metrics, assumptions, limitations, and risks; never advise or trade.",
            ),
        }

        @executor(id="fetch_data")
        async def fetch(task: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message((await self.agents["data"].run(task)).text)

        @executor(id="generate_signals")
        async def signal(message: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message((await self.agents["signal"].run(message)).text)

        @executor(id="backtest")
        async def run_backtest(message: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message((await self.agents["backtest"].run(message)).text)

        @executor(id="summary_report")
        async def summary(message: str, ctx: WorkflowContext[Never, str]) -> None:
            await ctx.yield_output((await self.agents["summary"].run(message)).text)

        def valid(message: str) -> bool:
            return self._has_signals(message)

        workflow = (
            WorkflowBuilder(start_executor=fetch, checkpoint_storage=self.storage)
            .add_edge(fetch, signal)
            .add_edge(signal, run_backtest, condition=valid)
            .add_edge(run_backtest, summary)
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
        try:
            return (
                AgentCompletedResult.model_validate_json(message).success
                and (self.work_dir / DATASET_SIGNALS).is_file()
            )
        except Exception:
            return False
