"""Agent Framework workflow that turns market snapshots into advisory reports.

    extract_features ─(has features)─▶ technical_read ─▶ risk_review ─▶ compose_report
            └──────────(no features)──────────────────────────────────▶ compose_report

Executors exchange one JSON state object, so any stage can be inspected by
printing the message on an edge.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

from agent_framework import WorkflowBuilder, WorkflowContext, executor
from typing_extensions import Never

from .. import providers
from ..features import extract_all, features_json, rule_based_read, rule_based_risk
from ..models import (
    DISCLAIMER,
    AdvisoryReport,
    AdvisoryRow,
    AssetFeatures,
    MarketSnapshot,
    RiskReview,
    TechnicalRead,
)
from .agents import AgentFailure, AgentSpec, AgentTeam, utc_now

TECHNICAL_INSTRUCTIONS = (
    "You are a technical analyst. You receive precomputed indicators (fast SMA, slow SMA, "
    "RSI(14), momentum, annualised volatility, drawdown) for a watchlist. For every symbol "
    "return exactly one signal with action BUY, SELL, or HOLD, a confidence between 0 and 1, "
    "and a rationale of at most 25 words citing the indicators you used. Never invent symbols "
    "or indicator values, never mention news or fundamentals you were not given, and treat the "
    "output as research, not investment advice."
)

RISK_INSTRUCTIONS = (
    "You are a risk officer reviewing technical signals. For every symbol return an adjustment "
    "with the final action, a calibrated confidence between 0 and 1, a max_position_pct between "
    "0 and 100, and a risk note of at most 20 words. Downgrade BUY to HOLD when volatility or "
    "drawdown is extreme, cap position size as volatility rises, and classify the overall "
    "portfolio risk as LOW, MEDIUM, or HIGH. This is research, not investment advice."
)

SPECS = {
    "technical": AgentSpec("technical_analyst", TECHNICAL_INSTRUCTIONS, TechnicalRead),
    "risk": AgentSpec("risk_officer", RISK_INSTRUCTIONS, RiskReview),
}


class MarketAdvisoryWorkflow:
    """Four-stage graph: feature extraction, technical read, risk review, report."""

    def __init__(self) -> None:
        self.team = AgentTeam(SPECS)

    def connect(self, provider: providers.Provider) -> None:
        self.team.connect(provider)

    @property
    def mode(self) -> str:
        return self.team.mode

    @property
    def error(self) -> str:
        return self.team.error

    # -- workflow graph --------------------------------------------------

    def build(self):
        @executor(id="extract_features")
        async def extract(message: str, ctx: WorkflowContext[str]) -> None:
            snapshot = MarketSnapshot.model_validate_json(message)
            features = extract_all(snapshot)
            await ctx.send_message(
                pack(
                    period_label=snapshot.period_label,
                    features=[item.model_dump() for item in features],
                    mode=self.team.mode,
                    error=self.team.error,
                )
            )

        @executor(id="technical_read")
        async def technical(message: str, ctx: WorkflowContext[str]) -> None:
            state = unpack(message)
            state["technical"] = (await self._technical_read(state)).model_dump()
            await ctx.send_message(pack(**state))

        @executor(id="risk_review")
        async def risk(message: str, ctx: WorkflowContext[str]) -> None:
            state = unpack(message)
            state["risk"] = (await self._risk_review(state)).model_dump()
            await ctx.send_message(pack(**state))

        @executor(id="compose_report")
        async def compose(message: str, ctx: WorkflowContext[Never, str]) -> None:
            await ctx.yield_output(self._compose(unpack(message)).model_dump_json())

        def has_features(message: str) -> bool:
            return bool(unpack(message)["features"])

        return (
            WorkflowBuilder(start_executor=extract)
            .add_edge(extract, technical, condition=has_features)
            .add_edge(
                extract, compose, condition=lambda message: not has_features(message)
            )
            .add_edge(technical, risk)
            .add_edge(risk, compose)
            .build()
        )

    # -- stage implementations -------------------------------------------
    #
    # Both stages share one recipe: ask the agent when the team is ready, keep
    # only the symbols we sent, and degrade to the rule-based result otherwise.

    async def _technical_read(self, state: dict[str, Any]) -> TechnicalRead:
        features = load_features(state)
        rules = rule_based_read(features)
        if not self.team.ready:
            return degrade(state, "", rules)

        prompt = (
            f"Period: {state['period_label']}\n"
            f"Indicators (JSON):\n{features_json(features)}"
        )
        try:
            read = await self.team.run("technical", prompt, TechnicalRead)
        except AgentFailure as failure:
            return degrade(state, str(failure), rules)

        known = {item.symbol for item in features}
        read.signals = [signal for signal in read.signals if signal.symbol in known]
        if not read.signals:
            return degrade(state, "technical agent returned no usable signals", rules)
        return read

    async def _risk_review(self, state: dict[str, Any]) -> RiskReview:
        features = load_features(state)
        read = TechnicalRead.model_validate(state["technical"])
        rules = rule_based_risk(features, read)
        if not self.team.ready:
            return degrade(state, "", rules)

        prompt = (
            f"Indicators (JSON):\n{features_json(features)}\n\n"
            f"Technical signals (JSON):\n{read.model_dump_json()}"
        )
        try:
            review = await self.team.run("risk", prompt, RiskReview)
        except AgentFailure as failure:
            return degrade(state, str(failure), rules)

        known = {signal.symbol for signal in read.signals}
        review.adjustments = [
            item for item in review.adjustments if item.symbol in known
        ]
        if not review.adjustments:
            return degrade(state, "risk agent returned no usable adjustments", rules)
        return review

    # -- report ----------------------------------------------------------

    def empty_report(self, error: str) -> AdvisoryReport:
        """Report used when the graph produced no output at all."""
        return self._compose(unpack(pack(mode="offline", error=error)))

    def _compose(self, state: dict[str, Any]) -> AdvisoryReport:
        features = {item.symbol: item for item in load_features(state)}
        error = state["error"] or self.team.error

        if not features:
            return AdvisoryReport(
                generated_at=utc_now(),
                mode="offline",
                headline="No usable price history in this snapshot.",
                portfolio_risk="MEDIUM",
                market_note="The dashboard sent no asset with enough history to analyse.",
                risk_summary="No exposure guidance produced.",
                rows=[],
                error=error,
            )

        read = TechnicalRead.model_validate(state["technical"])
        review = RiskReview.model_validate(state["risk"])
        rationales = {signal.symbol: signal.rationale for signal in read.signals}

        rows = [
            AdvisoryRow(
                symbol=item.symbol,
                action=item.action,
                confidence=item.confidence,
                max_position_pct=item.max_position_pct,
                rationale=rationales.get(item.symbol, ""),
                risk_note=item.risk_note,
                rsi=feature.rsi,
                sma_fast=feature.sma_fast,
                sma_slow=feature.sma_slow,
                momentum_pct=feature.momentum_pct,
                volatility_pct=feature.volatility_pct,
                trend=feature.trend,
            )
            for item in review.adjustments
            if (feature := features.get(item.symbol)) is not None
        ]

        buys = sum(1 for row in rows if row.action == "BUY")
        sells = sum(1 for row in rows if row.action == "SELL")
        return AdvisoryReport(
            generated_at=utc_now(),
            mode="agent" if state["mode"] == "agent" else "offline",
            headline=(
                f"{buys} buy, {sells} sell, {len(rows) - buys - sells} hold "
                f"across {len(rows)} assets."
            ),
            portfolio_risk=review.portfolio_risk,
            market_note=read.market_note,
            risk_summary=review.risk_summary,
            rows=rows,
            disclaimer=DISCLAIMER,
            error=error,
        )


# -- shared state ---------------------------------------------------------
#
# One JSON object travels the whole graph; packing fills in every key so no
# executor has to guard against a missing one.

EMPTY_STATE: dict[str, Any] = {
    "period_label": "7D",
    "features": [],
    "technical": {},
    "risk": {},
    "mode": "agent",
    "error": "",
}

FallbackT = TypeVar("FallbackT")


def pack(**state: Any) -> str:
    return json.dumps({**EMPTY_STATE, **state})


def unpack(message: str) -> dict[str, Any]:
    return {**EMPTY_STATE, **json.loads(str(message))}


def load_features(state: dict[str, Any]) -> list[AssetFeatures]:
    return [AssetFeatures.model_validate(item) for item in state["features"]]


def degrade(state: dict[str, Any], error: str, fallback: FallbackT) -> FallbackT:
    """Switch the run to offline mode and return the rule-based result."""
    state["mode"] = "offline"
    if error:
        state["error"] = error
    return fallback
