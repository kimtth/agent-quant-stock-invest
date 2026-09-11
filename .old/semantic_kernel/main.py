"""Run the Semantic Kernel quantitative-investment workflow.

This produces research artifacts only; it does not connect to a brokerage or execute trades.
"""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv

from .workflow import InvestmentWorkflow


def task() -> str:
    ticker = os.getenv("INVESTMENT_TICKER", "MSFT")
    start = os.getenv("INVESTMENT_START_DATE", "2020-01-01")
    end = os.getenv("INVESTMENT_END_DATE", "2026-07-01")
    capital = os.getenv("INVESTMENT_INITIAL_CAPITAL", "10000")
    return (
        f"Analyze {ticker} from {start} to {end}. Develop one transparent technical-analysis "
        f"signal strategy as Python code, execute it, backtest ${capital}, and report CAGR, "
        "total return, final value, drawdown, and Sharpe ratio."
    )


async def main() -> None:
    load_dotenv()
    workflow = InvestmentWorkflow()
    try:
        print(await workflow.run(task()))
        print(f"Semantic Kernel output directory: {workflow.output_dir.resolve()}")
    finally:
        await workflow.close()


if __name__ == "__main__":
    asyncio.run(main())
