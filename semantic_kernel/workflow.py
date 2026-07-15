"""Explicit Semantic Kernel orchestration over native investment plugins."""

from pathlib import Path

from semantic_kernel import Kernel

from .models import StrategyRun, WorkflowRequest, WorkflowResult
from .tools import (
    BacktestingPlugin,
    MarketResearchPlugin,
    ReportingPlugin,
    SignalGenerationPlugin,
    StockDataPlugin,
    StrategyIdeasPlugin,
)

WORK_DIR = Path("output") / "semantic_kernel"


class InvestmentWorkflow:
    """Run strategy ideas → data → signals → backtest → chart deterministically."""

    def __init__(self, output_dir: Path = WORK_DIR) -> None:
        self.output_dir = output_dir
        self.kernel = Kernel()
        self.strategies = StrategyIdeasPlugin(output_dir)
        for name, plugin in (
            ("strategy_ideas", self.strategies),
            ("market_research", MarketResearchPlugin()),
            ("stock_data", StockDataPlugin(output_dir)),
            ("signal_generation", SignalGenerationPlugin(output_dir)),
            ("backtesting", BacktestingPlugin(output_dir)),
            ("reporting", ReportingPlugin(output_dir)),
        ):
            self.kernel.add_plugin(plugin, plugin_name=name)

    def run(self, request: WorkflowRequest) -> WorkflowResult:
        self.strategies.create_strategy_ideas()
        runs: list[StrategyRun] = []
        for idea in request.strategies or self.strategies.load():
            directory = self.output_dir / "_".join(
                idea.name.lower().replace("-", " ").split()
            )
            data, signal = StockDataPlugin(directory), SignalGenerationPlugin(directory)
            backtest, report = BacktestingPlugin(directory), ReportingPlugin(directory)
            data.fetch_stock_data(request.ticker, request.start_date, request.end_date)
            signals = signal.generate(idea)
            metrics, results, metrics_file = backtest.run(request.initial_capital)
            runs.append(
                StrategyRun(
                    strategy=idea,
                    metrics=metrics,
                    output_directory=directory,
                    stock_data_file=directory / "stock_data.csv",
                    signals_file=signals,
                    results_file=results,
                    metrics_file=metrics_file,
                    plot_file=Path(report.plot_performance()),
                )
            )
        return WorkflowResult(
            ticker=request.ticker,
            strategy_ideas_file=self.output_dir / "strategy_ideas.json",
            runs=runs,
        )


def generate_reproducible_output(
    request: WorkflowRequest, output_dir: Path
) -> WorkflowResult:
    return InvestmentWorkflow(output_dir).run(request)
