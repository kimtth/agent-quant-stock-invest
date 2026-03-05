# ============================================================================
# Main Entry Point
# ============================================================================

import asyncio

from dotenv import load_dotenv
from agents.workflow import QuantInvestWorkflow

# Set to True to launch the Dev UI server instead of running the workflow directly
LAUNCH_DEV_UI = True
DEV_UI_PORT = 8090
DEV_UI_AUTO_OPEN = False


async def _create_workflow():
    """Build the workflow inside a dedicated event loop (used by Dev UI path)."""
    load_dotenv()
    wf = QuantInvestWorkflow()
    return await wf.create_workflow()


async def main() -> None:
    """Run the quantitative investment workflow directly."""
    load_dotenv()

    workflow = QuantInvestWorkflow()
    built_workflow = await workflow.create_workflow()

    # Define analysis task
    task = """
    Analyze Apple (AAPL) stock using a momentum trading strategy:
    1. Fetch historical data from 2023-01-01 to 2026-03-01
    2. Generate buy/sell signals using MACD and RSI indicators
    3. Backtest the strategy with initial capital of $10,000
    4. Report performance metrics (CAGR, total return, final value)
    """

    await workflow.run_task(built_workflow, task)

    print("\n" + "=" * 80)


if __name__ == "__main__":
    if LAUNCH_DEV_UI:
        # serve() calls uvicorn.run() → asyncio.run() internally.
        # Must NOT be inside a running event loop when calling serve().
        # Build workflow in its own temporary loop first, then hand off to serve().
        from agent_framework.devui import serve
        built_workflow = asyncio.run(_create_workflow())
        print(f"Launching Dev UI on http://localhost:{DEV_UI_PORT} ...")
        serve(entities=[built_workflow], port=DEV_UI_PORT, auto_open=DEV_UI_AUTO_OPEN)
    else:
        asyncio.run(main())

