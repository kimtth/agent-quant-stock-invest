# ============================================================================
# Main Entry Point
# ============================================================================

import asyncio

from dotenv import load_dotenv
from agent_workflow import QuantInvestWorkflow


async def main() -> None:
    """
    Main execution function demonstrating the correct Agent Framework pattern.

    Demonstrates:
    - Loading environment variables
    - Creating workflow orchestrator
    - Running analysis task
    - Printing results
    """
    # Load environment variables
    load_dotenv()

    # Initialize workflow orchestrator
    workflow = QuantInvestWorkflow()

    # Create the workflow (agents + executors + edges)
    built_workflow = await workflow.create_workflow()

    # Define analysis task
    task = """
    Analyze Apple (AAPL) stock using a momentum trading strategy:
    1. Fetch historical data from 2023-01-01 to 2024-01-01
    2. Generate buy/sell signals using MACD and RSI indicators
    3. Backtest the strategy with initial capital of $10,000
    4. Report performance metrics (CAGR, total return, final value)
    """

    # Run the workflow
    await workflow.run_task(built_workflow, task)

    # This server needs to be outside the workflow run to keep it alive
    # Launch server with the workflow
    # from agent_framework.devui import serve
    # Expose the workflow at http://localhost:8090
    # serve(entities=[built_workflow], port=8090, auto_open=True)

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
