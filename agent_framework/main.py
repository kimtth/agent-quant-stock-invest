"""Run the Agent Framework investment-research workflow or Dev UI."""

import asyncio
import os

from dotenv import load_dotenv

from .workflow import QuantInvestWorkflow

DEV_UI_PORT = 8090


def task() -> str:
    ticker = os.getenv("INVESTMENT_TICKER", "MSFT")
    start = os.getenv("INVESTMENT_START_DATE", "2020-01-01")
    end = os.getenv("INVESTMENT_END_DATE", "2026-07-01")
    capital = os.getenv("INVESTMENT_INITIAL_CAPITAL", "10000")
    return f"Analyze {ticker} from {start} to {end}; generate MACD/RSI signals, backtest ${capital}, and report CAGR, total return, final value, drawdown, and Sharpe ratio."


async def build() -> tuple[QuantInvestWorkflow, object]:
    workflow = QuantInvestWorkflow()
    return workflow, await workflow.create_workflow()


async def main() -> None:
    load_dotenv()
    workflow, built = await build()
    await workflow.run_task(built, task())
    print(f"Agent Framework output directory: {workflow.work_dir.resolve()}")


if __name__ == "__main__":
    load_dotenv()
    if os.getenv("LAUNCH_DEV_UI", "false").lower() == "true":
        from agent_framework.devui import serve

        workflow, built = asyncio.run(build())
        print(f"Agent Framework output directory: {workflow.work_dir.resolve()}")
        serve(entities=[built], port=DEV_UI_PORT, auto_open=False)
    else:
        asyncio.run(main())
