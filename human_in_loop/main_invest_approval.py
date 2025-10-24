# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass
import os

from agent_framework import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    ChatMessage,
    Executor,
    RequestInfoEvent,
    RequestInfoExecutor,
    RequestInfoMessage,
    RequestResponse,
    Role,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
    handler,
)
from agent_framework.azure import AzureOpenAIChatClient
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
class InvestmentApprovalRequest(RequestInfoMessage):
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
        """Start the investment analysis workflow.

        Args:
            ticker: Stock symbol to analyze
        """
        user = ChatMessage(
            Role.USER,
            text=f"Analyze {ticker} and provide an investment recommendation with rationale.",
        )
        await ctx.send_message(AgentExecutorRequest(messages=[user], should_respond=True))

    @handler
    async def on_agent_response(
        self,
        result: AgentExecutorResponse,
        ctx: WorkflowContext[InvestmentApprovalRequest],
    ) -> None:
        """Handle agent's investment recommendation and request human approval."""
        text = result.agent_run_response.text or ""

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

            await ctx.send_message(
                InvestmentApprovalRequest(
                    prompt=prompt,
                    recommendation=text,
                    ticker=recommendation.ticker,
                )
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
            await ctx.send_message(
                InvestmentApprovalRequest(
                    prompt=prompt,
                    recommendation=text,
                    ticker="",
                )
            )

    @handler
    async def on_human_feedback(
        self,
        feedback: RequestResponse[InvestmentApprovalRequest, str],
        ctx: WorkflowContext[AgentExecutorRequest, str],
    ) -> None:
        """Process human approval or refinement request."""
        reply = (feedback.data or "").strip().lower()
        ticker = getattr(feedback.original_request, "ticker", "")

        if reply == "approve":
            await ctx.yield_output(
                f"Investment recommendation for {ticker} approved and ready for execution."
            )
            return

        # Handle refinement requests
        if reply.startswith("refine"):
            refinement_feedback = reply[6:].strip() if len(reply) > 6 else "provide more details"
            user_msg = ChatMessage(
                Role.USER,
                text=(
                    f"Please refine your recommendation based on this feedback: {refinement_feedback}. "
                    f'Return a JSON object matching the schema: {{"ticker": str, "action": str, "rationale": str, "confidence": str}}'
                ),
            )
            await ctx.send_message(AgentExecutorRequest(messages=[user_msg], should_respond=True))
        else:
            # Invalid input - re-prompt
            user_msg = ChatMessage(
                Role.USER,
                text='Please provide a valid investment recommendation in JSON format.',
            )
            await ctx.send_message(AgentExecutorRequest(messages=[user_msg], should_respond=True))


async def main() -> None:
    """Run the human-in-the-loop investment agent workflow."""

    # Load environment variables
    load_dotenv()

    # Get stock ticker from user
    print("\n" + "=" * 60)
    print("QUANTITATIVE INVESTMENT AGENT WITH HUMAN OVERSIGHT")
    print("=" * 60)
    ticker = input("Enter stock ticker to analyze (e.g., MSFT, AAPL): ").strip().upper()

    if not ticker:
        print("No ticker provided. Exiting.")
        return

    # Create the investment analysis agent
    chat_client = AzureOpenAIChatClient(
        endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"]
    )
    agent = chat_client.create_agent(
        instructions=(
            "You are a quantitative investment analyst. "
            "Analyze stocks and provide structured investment recommendations. "
            "Consider: financial metrics, market trends, risk factors, and growth potential. "
            'Return ONLY a JSON object matching: {"ticker": str, "action": "BUY/SELL/HOLD", "rationale": str, "confidence": "HIGH/MEDIUM/LOW"}. '
            "No additional text or explanations outside the JSON."
        ),
        response_format=InvestmentRecommendation,
    )

    # Build the workflow
    turn_manager = InvestmentTurnManager(id="investment_turn_manager")
    agent_exec = AgentExecutor(agent=agent, id="investment_agent")
    request_info_executor = RequestInfoExecutor(id="request_info")

    workflow = (
        WorkflowBuilder()
        .set_start_executor(turn_manager)
        .add_edge(turn_manager, agent_exec)
        .add_edge(agent_exec, turn_manager)
        .add_edge(turn_manager, request_info_executor)
        .add_edge(request_info_executor, turn_manager)
        .build()
    )

    # Execute human-in-the-loop workflow
    pending_responses: dict[str, str] | None = None
    completed = False
    workflow_output: str | None = None

    print(f"\nAnalyzing {ticker}...\n")

    while not completed:
        stream = (
            workflow.send_responses_streaming(pending_responses)
            if pending_responses
            else workflow.run_stream(ticker)
        )

        events = [event async for event in stream]
        pending_responses = None

        requests: list[tuple[str, str]] = []
        for event in events:
            if isinstance(event, RequestInfoEvent) and isinstance(event.data, InvestmentApprovalRequest):
                requests.append((event.request_id, event.data.prompt))
            elif isinstance(event, WorkflowOutputEvent):
                workflow_output = str(event.data)
                completed = True

        # Status monitoring
        pending_status = any(
            isinstance(e, WorkflowStatusEvent) and e.state == WorkflowRunState.IN_PROGRESS_PENDING_REQUESTS
            for e in events
        )
        idle_with_requests = any(
            isinstance(e, WorkflowStatusEvent) and e.state == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS
            for e in events
        )

        if pending_status:
            print("[Status: Processing agent response...]")
        if idle_with_requests:
            print("[Status: Awaiting human decision...]")

        # Collect human responses
        if requests and not completed:
            responses: dict[str, str] = {}
            for req_id, prompt in requests:
                print(prompt)
                answer = input("Your decision: ").strip().lower()  # noqa: ASYNC250
                if answer == "exit":
                    print("\nWorkflow cancelled by user.")
                    return
                responses[req_id] = answer
            pending_responses = responses

    # Display final result
    print(f"\n{'='*60}")
    print("WORKFLOW COMPLETE")
    print(f"{'='*60}")
    print(f"{workflow_output}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())