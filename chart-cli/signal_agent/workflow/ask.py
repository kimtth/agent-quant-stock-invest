"""Agent Framework workflow behind the dashboard `/ask` command.

    ground_question ─▶ answer_question

`ground_question` recomputes the indicators for the snapshot on screen, so the
analyst agent can only reason about numbers the dashboard actually showed.
"""

from __future__ import annotations

import json
from typing import Any

from agent_framework import WorkflowBuilder, WorkflowContext, executor
from typing_extensions import Never

from .. import providers
from ..features import extract_all, features_json
from ..models import AskAnswer, AskReply, AskRequest, AssetFeatures, MarketSnapshot
from .agents import AgentFailure, AgentSpec, AgentTeam, utc_now

ANALYST_INSTRUCTIONS = (
    "You are a market analyst answering one question about a watchlist. You receive the "
    "user question and precomputed indicators (price, period change, fast SMA, slow SMA, "
    "RSI(14), momentum, annualised volatility, drawdown) for every symbol on screen. "
    "Answer in at most 90 words using only those numbers, name the symbols you rely on, "
    "and add up to three short highlights. Never invent symbols, prices, news, or "
    "fundamentals, say plainly when the data cannot answer the question, and never "
    "recommend a trade. This is research, not investment advice."
)

SPECS = {"analyst": AgentSpec("market_analyst", ANALYST_INSTRUCTIONS, AskAnswer)}

MAX_QUESTION_CHARS = 600
MAX_HIGHLIGHTS = 3


class AskWorkflow:
    """Two-stage graph: ground the question in indicators, then answer it."""

    def __init__(self) -> None:
        self.team = AgentTeam(SPECS)

    def connect(self, provider: providers.Provider) -> None:
        self.team.connect(provider)

    def build(self):
        @executor(id="ground_question")
        async def ground(message: str, ctx: WorkflowContext[str]) -> None:
            request = AskRequest.model_validate_json(message)
            snapshot = request.snapshot or MarketSnapshot(generated_at=utc_now())
            await ctx.send_message(
                json.dumps(
                    {
                        "question": request.question.strip()[:MAX_QUESTION_CHARS],
                        "focus_symbol": request.focus_symbol,
                        "period_label": snapshot.period_label,
                        "features": [
                            item.model_dump() for item in extract_all(snapshot)
                        ],
                    }
                )
            )

        @executor(id="answer_question")
        async def answer(message: str, ctx: WorkflowContext[Never, str]) -> None:
            state = json.loads(message)
            features = [
                AssetFeatures.model_validate(item) for item in state["features"]
            ]
            reply = await self._answer(state, features)
            await ctx.yield_output(reply.model_dump_json())

        return WorkflowBuilder(start_executor=ground).add_edge(ground, answer).build()

    def empty_reply(self, question: str, error: str = "no workflow output") -> AskReply:
        """Reply used when the graph produced no output at all."""
        return _reply(
            question, "The workflow returned no answer for that question.", error=error
        )

    async def _answer(
        self, state: dict[str, Any], features: list[AssetFeatures]
    ) -> AskReply:
        question = state["question"]
        if not question:
            return _reply(
                question,
                "Ask a question after /ask, for example: "
                "/ask which symbol has the weakest momentum?",
            )
        if not features:
            return _reply(
                question,
                "No symbol on screen has enough price history to answer that yet.",
            )
        if not self.team.ready:
            return self._digest(state, features)

        prompt = (
            f"Question: {question}\n"
            f"Period: {state['period_label']}\n"
            f"Selected symbol: {state['focus_symbol'] or 'none'}\n"
            f"Indicators (JSON):\n{features_json(features)}"
        )
        try:
            parsed = await self.team.run("analyst", prompt, AskAnswer)
        except AgentFailure as failure:
            digest = self._digest(state, features)
            digest.error = str(failure)
            return digest

        return _reply(
            question,
            parsed.answer.strip(),
            highlights=parsed.highlights[:MAX_HIGHLIGHTS],
            mode="agent",
        )

    def _digest(self, state: dict[str, Any], features: list[AssetFeatures]) -> AskReply:
        """Deterministic indicator digest used when no chat provider is available."""
        best = max(features, key=lambda item: item.momentum_pct)
        worst = min(features, key=lambda item: item.momentum_pct)
        hottest = max(features, key=lambda item: item.rsi)
        coldest = min(features, key=lambda item: item.rsi)
        up = sum(1 for item in features if item.trend == "up")
        down = sum(1 for item in features if item.trend == "down")

        highlights = [
            f"{best.symbol} leads momentum at {best.momentum_pct:.1f}%; "
            f"{worst.symbol} lags at {worst.momentum_pct:.1f}%.",
            f"RSI range: {coldest.symbol} {coldest.rsi:.0f} to "
            f"{hottest.symbol} {hottest.rsi:.0f}.",
            f"Trend split: {up} up, {down} down, {len(features) - up - down} flat.",
        ]
        selected = next(
            (item for item in features if item.symbol == state["focus_symbol"]), None
        )
        if selected is not None:
            highlights.insert(
                0,
                f"{selected.symbol}: price {selected.price:.2f}, RSI {selected.rsi:.0f}, "
                f"volatility {selected.volatility_pct:.1f}%, trend {selected.trend}.",
            )

        return _reply(
            state["question"],
            "No chat model is connected, so here is the indicator digest for the "
            f"{state['period_label']} window across {len(features)} symbols. "
            "Run /model to attach a provider for a written answer.",
            highlights=highlights[:MAX_HIGHLIGHTS],
        )


def _reply(
    question: str,
    answer: str,
    *,
    highlights: list[str] | None = None,
    mode: str = "offline",
    error: str = "",
) -> AskReply:
    return AskReply(
        generated_at=utc_now(),
        mode="agent" if mode == "agent" else "offline",
        question=question,
        answer=answer,
        highlights=highlights or [],
        error=error,
    )
