"""Agent Framework workflow that generates a signal strategy, then backtests it.

    generate_signals ─▶ simulate ─▶ review_backtest

The simulation engine itself lives in `signal_agent.backtest`.
"""

# ruff: noqa: E402

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import agent_framework
from agent_framework import WorkflowBuilder, WorkflowContext, executor
import pandas as pd
from typing_extensions import Never

# The installed SDK is imported first, so add the repository package that holds
# the signal-generator REPL to the same namespace.
_LOCAL = str(Path(__file__).resolve().parents[3] / "agent_framework")
if _LOCAL not in agent_framework.__path__:
    agent_framework.__path__.insert(0, _LOCAL)
from agent_framework.research_repl import DATASET_SIGNALS, DATASET_STOCK, ResearchPythonRepl

from .. import providers
from ..backtest import DEFAULT_PLAN, BacktestEngine, rule_based_verdict
from ..models import (
    BacktestMetrics,
    BacktestRequest,
    BacktestVerdict,
    GeneratedStrategy,
    StrategyPlan,
    Trade,
)
from .agents import AgentFailure, AgentSpec, AgentTeam

GENERATOR_INSTRUCTIONS = (
    "You generate one transparent, long-only technical-analysis signal strategy for a backtest. "
    "Use the user request as the research hypothesis. Return Python code that reads INPUT_PATH and "
    "writes OUTPUT_PATH. The output must have exactly one row per input row and the columns "
    "BuySignal, SellSignal, and Description. Use only pandas as pd, numpy as np, and ta; do not "
    "access the network, shell, environment variables, or other files. Buy and sell signals must "
    "be boolean. The backtest executes the validated code separately. This is research, not advice."
)

REVIEWER_INSTRUCTIONS = (
    "You review a completed backtest. Given the strategy parameters and performance metrics, "
    "write a verdict of at most 45 words plus short strengths and weaknesses. Mention drawdown "
    "and trade count honestly, note that costs and slippage are excluded, and never recommend "
    "a trade. This is research, not investment advice."
)


SPECS = {
    "generator": AgentSpec("signal_generator", GENERATOR_INSTRUCTIONS, GeneratedStrategy),
    "reviewer": AgentSpec("backtest_reviewer", REVIEWER_INSTRUCTIONS, BacktestVerdict),
}


class BacktestWorkflow:
    """Three-stage graph: plan the strategy, stream the simulation, review the result.

    Progress frames and the final summary are both emitted with ``ctx.yield_output``,
    so the dashboard receives them on the workflow's streaming event feed as the
    simulation walks the price series.
    """

    def __init__(self) -> None:
        self.team = AgentTeam(SPECS)
        self.repl = ResearchPythonRepl(Path("output") / "chart_cli")

    def connect(self, provider: providers.Provider) -> None:
        self.team.connect(provider)

    def build(self):
        @executor(id="generate_signals")
        async def plan(message: str, ctx: WorkflowContext[str]) -> None:
            request = BacktestRequest.model_validate_json(message)
            chosen, buy, sell, mode, error = await self._generate_signals(request)
            await ctx.send_message(
                json.dumps(
                    {
                        "request": request.model_dump(),
                        "plan": chosen.model_dump(),
                        "buy": buy,
                        "sell": sell,
                        "mode": mode,
                        "error": error,
                    }
                )
            )

        @executor(id="simulate")
        async def simulate(message: str, ctx: WorkflowContext[str, str]) -> None:
            state = json.loads(message)
            request = BacktestRequest.model_validate(state["request"])
            engine = BacktestEngine(
                request,
                StrategyPlan.model_validate(state["plan"]),
                buy_signals=list(state.get("buy", [])),
                sell_signals=list(state.get("sell", [])),
            )
            if not engine.usable:
                state["error"] = "not enough price history to backtest"
                await ctx.send_message(json.dumps(state))
                return

            delay = max(0, request.frame_delay_ms) / 1000
            for frame in engine.frames():
                await ctx.yield_output(frame.model_dump_json())
                if delay:
                    await asyncio.sleep(delay)

            state["plan"] = engine.plan.model_dump()
            state["metrics"] = engine.metrics.model_dump()
            state["engine"] = {
                "equity_curve": engine.equity_curve,
                "trades": [trade.model_dump() for trade in engine.trades],
            }
            await ctx.send_message(json.dumps(state))

        @executor(id="review_backtest")
        async def review(message: str, ctx: WorkflowContext[Never, str]) -> None:
            state = json.loads(message)
            request = BacktestRequest.model_validate(state["request"])
            engine = BacktestEngine(request, StrategyPlan.model_validate(state["plan"]))
            saved = state.get("engine", {})
            engine.equity_curve = list(saved.get("equity_curve", []))
            engine.trades = [
                Trade.model_validate(item) for item in saved.get("trades", [])
            ]
            if state.get("metrics"):
                engine.metrics = BacktestMetrics.model_validate(state["metrics"])

            verdict, mode, error = await self._review(engine, state)
            await ctx.yield_output(
                engine.summary(
                    mode=mode, verdict=verdict, error=error
                ).model_dump_json()
            )

        return (
            WorkflowBuilder(start_executor=plan)
            .add_edge(plan, simulate)
            .add_edge(simulate, review)
            .build()
        )

    async def _generate_signals(
        self, request: BacktestRequest
    ) -> tuple[StrategyPlan, list[bool], list[bool], str, str]:
        if not self.team.ready:
            return (
                DEFAULT_PLAN,
                [],
                [],
                "offline",
                "A chat provider is required to generate a signal strategy. Use /model first.",
            )
        closes = request.history
        self.repl.work_dir.mkdir(parents=True, exist_ok=True)
        dates = (
            pd.to_datetime(request.timestamps, unit="ms", errors="coerce").astype(str)
            if len(request.timestamps) == len(closes)
            else pd.RangeIndex(len(closes)).astype(str)
        )
        data = pd.DataFrame(
            {
                "Date": dates,
                "Adj Close": closes,
                "Close": closes,
            }
        )
        data.to_csv(self.repl.work_dir / DATASET_STOCK, index=False)
        prompt = (
            f"Symbol: {request.symbol} ({request.kind_label})\n"
            f"Bars: {len(closes)}\n"
            f"First close: {closes[0] if closes else 0:.4f}\n"
            f"Last close: {closes[-1] if closes else 0:.4f}\n"
            f"Min close: {min(closes) if closes else 0:.4f}\n"
            f"Max close: {max(closes) if closes else 0:.4f}\n"
            f"Research request: {request.criteria or 'Develop one transparent technical-analysis strategy.'}\n"
            "Use INPUT_PATH and OUTPUT_PATH exactly as supplied in your executable code."
        )
        for _ in range(3):
            try:
                generated = await self.team.run("generator", prompt, GeneratedStrategy)
            except AgentFailure as failure:
                return DEFAULT_PLAN, [], [], "offline", str(failure)

            result = self.repl.execute(generated.code)
            if result.startswith("SUCCESS:"):
                signals = pd.read_csv(self.repl.work_dir / DATASET_SIGNALS)
                plan = StrategyPlan(name=generated.name, rationale=generated.rationale)
                return (
                    plan,
                    signals["BuySignal"].astype(bool).tolist(),
                    signals["SellSignal"].astype(bool).tolist(),
                    "agent",
                    "",
                )
            prompt = (
                f"{prompt}\n\nThe previous generated script was rejected by the research REPL:\n"
                f"{result}\nCorrect the code and return a complete replacement."
            )
        return DEFAULT_PLAN, [], [], "offline", result

    async def _review(
        self, engine: BacktestEngine, state: dict[str, Any]
    ) -> tuple[str, str, str]:
        fallback = rule_based_verdict(engine)
        carried = str(state.get("error", ""))
        if not self.team.ready or state.get("mode") != "agent":
            return fallback, "offline", carried
        prompt = (
            f"Symbol: {engine.request.symbol}\n"
            f"Strategy: {engine.plan.model_dump_json()}\n"
            f"Metrics: {engine.metrics.model_dump_json()}"
        )
        try:
            review = await self.team.run("reviewer", prompt, BacktestVerdict)
        except AgentFailure as failure:
            return fallback, "offline", str(failure)

        parts = [review.verdict]
        if review.strengths:
            parts.append("Strengths: " + "; ".join(review.strengths) + ".")
        if review.weaknesses:
            parts.append("Weaknesses: " + "; ".join(review.weaknesses) + ".")
        return " ".join(parts), "agent", carried
