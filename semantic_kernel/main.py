"""Run the Semantic Kernel quantitative-investment workflow.

This produces research artifacts only; it does not connect to a brokerage or execute trades.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from .workflow import InvestmentWorkflow, WorkflowRequest


def main() -> None:
    load_dotenv()
    workflow = InvestmentWorkflow()
    result = workflow.run(
        WorkflowRequest(
            ticker=os.getenv("INVESTMENT_TICKER", "MSFT"),
            start_date=os.getenv("INVESTMENT_START_DATE", "2020-01-01"),
            end_date=os.getenv("INVESTMENT_END_DATE", "2026-07-01"),
            initial_capital=float(os.getenv("INVESTMENT_INITIAL_CAPITAL", "10000")),
        )
    )
    print(f"Completed {len(result.runs)} research backtests for {result.ticker}.")
    print(f"Semantic Kernel output directory: {workflow.output_dir.resolve()}")
    for run in result.runs:
        print(
            f"{run.strategy.name}: CAGR={run.metrics.cagr:.2%}, MDD={run.metrics.maximum_drawdown:.2%}, Sharpe={run.metrics.sharpe_ratio:.2f}"
        )
        print(f"  Results: {run.output_directory}")


if __name__ == "__main__":
    main()
