# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass
import os
from collections.abc import AsyncIterable

from agent_framework import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    Executor,
    Message,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    WorkflowRunState,
    handler,
    response_handler,
)
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from pydantic import BaseModel

"""
Sample: Human in the loop quantitative investment agent

A financial analysis agent researches stocks and provides investment recommendations,
then requests human approval or feedback via RequestInfoExecutor. The loop continues
until the human approves, requests modifications, or exits.

Purpose:
Show how to integrate human approval gates in a financial AI agent workflow using
RequestInfoExecutor for critical investment decisions.

Demonstrate:
- Multi-turn financial analysis with human oversight
- Using Pydantic response_format for structured investment recommendations
- Human approval checkpoints before executing investment decisions
- Iterative refinement based on human feedback

Sample Output:
>>---------------------------------------------------------------------------
============================================================
QUANTITATIVE INVESTMENT AGENT WITH HUMAN OVERSIGHT
============================================================
Enter stock ticker to analyze (e.g., MSFT, AAPL): MSFT

Analyzing MSFT...

[Status: Processing agent response...]
[Status: Awaiting human decision...]

============================================================
INVESTMENT RECOMMENDATION
============================================================
Ticker: MSFT
Action: BUY
Confidence: MEDIUM
Rationale: Microsoft combines durable earnings power (large recurring Office/365 and commercial cloud revenue) with strong growth catalysts (Azure cloud expansion and AI monetization via OpenAI partnership and Copilot integrations). The company generates substantial free cash flow, maintains a strong balance sheet that supports share buybacks and dividends, and benefits from high operating margins and scale advantages versus peers. Key risks include a premium valuation relative to the market, competitive pressure in cloud/AI from AWS and Google, regulatory scrutiny, and execution risk in turning AI investments into sustainable incremental revenue. Given the balance of consistent cash-generation, leadership in cloud and enterprise AI, and clear near- to medium-term catalysts, the stock is recommended as a buy for investors seeking large-cap growth with income characteristics, while monitoring valuation and regulatory developments.
============================================================

Type one of:
  approve - Execute this recommendation
  refine <feedback> - Request modifications (e.g., 'refine focus on risk factors')
  exit - Cancel and exit

Your decision: approve

============================================================
WORKFLOW COMPLETE
============================================================
Investment recommendation for MSFT approved and ready for execution.
============================================================
<<---------------------------------------------------------------------------
"""


@dataclass
class InvestmentApprovalRequest:
    """Request sent to human for investment decision approval."""

    prompt: str = ""
    recommendation: str = ""
    ticker: str = ""


class InvestmentRecommendation(BaseModel):
    """Structured output from the investment agent."""

    ticker: str
    action: str  # BUY, SELL, or HOLD
    rationale: str
    confidence: str  # HIGH, MEDIUM, LOW


class InvestmentTurnManager(Executor):
    """Coordinates turns between the investment agent and human oversight.

    Responsibilities:
    - Initiate stock analysis requests
    - After each agent recommendation, request human approval
    - Process human feedback to refine or approve recommendations
    - Complete workflow upon human approval or exit
    """

    def __init__(self, id: str | None = None):
        super().__init__(id=id or "investment_turn_manager")

    @handler
    async def start(self, ticker: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        """Start the investment analysis workflow."""
        user = Message(
            "user",
            text=f"Analyze {ticker} and provide an investment recommendation with rationale.",
        )
        await ctx.send_message(AgentExecutorRequest(messages=[user], should_respond=True))

    @handler
    async def on_agent_response(
        self,
        result: AgentExecutorResponse,
        ctx: WorkflowContext,
    ) -> None:
        """Handle agent's investment recommendation and request human approval."""
        text = result.agent_response.text or ""

        try:
            recommendation = InvestmentRecommendation.model_validate_json(text)

            prompt = (
                f"\n{'='*60}\n"
                f"INVESTMENT RECOMMENDATION\n"
                f"{'='*60}\n"
                f"Ticker: {recommendation.ticker}\n"
                f"Action: {recommendation.action}\n"
                f"Confidence: {recommendation.confidence}\n"
                f"Rationale: {recommendation.rationale}\n"
                f"{'='*60}\n\n"
                f"Type one of:\n"
                f"  approve - Execute this recommendation\n"
                f"  refine <feedback> - Request modifications (e.g., 'refine focus on risk factors')\n"
                f"  exit - Cancel and exit\n"
            )

            await ctx.request_info(
                request_data=InvestmentApprovalRequest(
                    prompt=prompt,
                    recommendation=text,
                    ticker=recommendation.ticker,
                ),
                response_type=str,
            )
        except Exception:
            # Fallback if parsing fails
            prompt = (
                f"\n{'='*60}\n"
                f"INVESTMENT ANALYSIS\n"
                f"{'='*60}\n"
                f"{text}\n"
                f"{'='*60}\n\n"
                f"Type one of: approve, refine <feedback>, or exit\n"
            )
            await ctx.request_info(
                request_data=InvestmentApprovalRequest(
                    prompt=prompt,
                    recommendation=text,
                    ticker="",
                ),
                response_type=str,
            )

    @response_handler
    async def on_human_feedback(
        self,
        original_request: InvestmentApprovalRequest,
        feedback: str,
        ctx: WorkflowContext[AgentExecutorRequest, str],
    ) -> None:
        """Process human approval or refinement request."""
        reply = (feedback or "").strip().lower()
        ticker = original_request.ticker

        if reply == "approve":
            await ctx.yield_output(
                f"Investment recommendation for {ticker} approved and ready for execution."
            )
            return

        # Handle refinement requests
        if reply.startswith("refine"):
            refinement_feedback = reply[6:].strip() if len(reply) > 6 else "provide more details"
            user_msg = Message(
                "user",
                text=(
                    f"Please refine your recommendation based on this feedback: {refinement_feedback}. "
                    f'Return a JSON object matching the schema: {{"ticker": str, "action": str, "rationale": str, "confidence": str}}'
                ),
            )
            await ctx.send_message(AgentExecutorRequest(messages=[user_msg], should_respond=True))
        else:
            # Invalid input - re-prompt
            user_msg = Message(
                "user",
                text='Please provide a valid investment recommendation in JSON format.',
            )
            await ctx.send_message(AgentExecutorRequest(messages=[user_msg], should_respond=True))


async def process_event_stream(
    stream: AsyncIterable[WorkflowEvent],
) -> tuple[dict[str, str] | None, str | None]:
    """Process workflow events, collect request_info prompts and final output."""
    requests: list[tuple[str, InvestmentApprovalRequest]] = []
    workflow_output: str | None = None

    async for event in stream:
        if event.type == "request_info" and isinstance(event.data, InvestmentApprovalRequest):
            requests.append((event.request_id, event.data))
        elif event.type == "output" and isinstance(event.data, str):
            workflow_output = event.data
        elif event.type == "status":
            if event.state == WorkflowRunState.IN_PROGRESS_PENDING_REQUESTS:
                print("[Status: Processing agent response...]")
            elif event.state == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS:
                print("[Status: Awaiting human decision...]")

    if requests:
        responses: dict[str, str] = {}
        for request_id, request in requests:
            print(request.prompt)
            answer = input("Your decision: ").strip().lower()  # noqa: ASYNC250
            if answer == "exit":
                print("\nWorkflow cancelled by user.")
                return None, None
            responses[request_id] = answer
        return responses, workflow_output

    return None, workflow_output


async def main() -> None:
    """Run the human-in-the-loop investment agent workflow."""
    load_dotenv()

    print("\n" + "=" * 60)
    print("QUANTITATIVE INVESTMENT AGENT WITH HUMAN OVERSIGHT")
    print("=" * 60)
    ticker = input("Enter stock ticker to analyze (e.g., MSFT, AAPL): ").strip().upper()

    if not ticker:
        print("No ticker provided. Exiting.")
        return

    # Create investment analysis agent (Azure CLI credential — run `az login` first)
    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )
    agent = client.as_agent(
        name="investment_analyst",
        instructions=(
            "You are a quantitative investment analyst. "
            "Analyze stocks and provide structured investment recommendations. "
            "Consider: financial metrics, market trends, risk factors, and growth potential. "
            'Return ONLY a JSON object matching: {"ticker": str, "action": "BUY/SELL/HOLD", "rationale": str, "confidence": "HIGH/MEDIUM/LOW"}. '
            "No additional text or explanations outside the JSON."
        ),
        default_options={"response_format": InvestmentRecommendation},
    )

    # Build the workflow: TurnManager ↔ AgentExecutor loop
    turn_manager = InvestmentTurnManager(id="investment_turn_manager")
    agent_exec = AgentExecutor(agent=agent, id="investment_agent")

    workflow = (
        WorkflowBuilder(start_executor=turn_manager)
        .add_edge(turn_manager, agent_exec)
        .add_edge(agent_exec, turn_manager)
        .build()
    )

    print(f"\nAnalyzing {ticker}...\n")

    pending_responses: dict[str, str] | None = None
    workflow_output: str | None = None

    stream = workflow.run(ticker, stream=True, include_status_events=True)
    pending_responses, workflow_output = await process_event_stream(stream)

    while pending_responses is not None and workflow_output is None:
        stream = workflow.run(responses=pending_responses, stream=True, include_status_events=True)
        pending_responses, workflow_output = await process_event_stream(stream)

    if workflow_output:
        print(f"\n{'='*60}")
        print("WORKFLOW COMPLETE")
        print(f"{'='*60}")
        print(workflow_output)
        print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())