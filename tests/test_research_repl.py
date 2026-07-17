"""Offline tests for the shared agent signal-generation REPL."""

from pathlib import Path

import pandas as pd
import pytest

from agent_framework.tools import AgentTools
from agent_framework.research_repl import ResearchPythonRepl as AgentFrameworkRepl
from semantic_kernel.tools import BacktestingPlugin, PythonReplPlugin
from semantic_kernel.research_repl import ResearchPythonRepl as SemanticKernelRepl


SIGNAL_SCRIPT = """
import pandas as pd

prices = pd.read_csv(INPUT_PATH)
price = pd.to_numeric(prices["Adj Close"], errors="coerce")
short = ta.trend.sma_indicator(price, window=2)
long = ta.trend.sma_indicator(price, window=3)
signals = pd.DataFrame(
    {
        "BuySignal": ((short > long) & (short.shift() <= long.shift())).fillna(False),
        "SellSignal": ((short < long) & (short.shift() >= long.shift())).fillna(False),
        "Description": "agent-authored moving-average crossover",
    }
)
signals.to_csv(OUTPUT_PATH, index=False)
"""


@pytest.fixture
def price_data(tmp_path: Path) -> Path:
    pd.DataFrame(
        {
            "Date": pd.date_range("2024-01-01", periods=8),
            "Open": [10, 11, 12, 11, 10, 11, 12, 13],
            "High": [11, 12, 13, 12, 11, 12, 13, 14],
            "Low": [9, 10, 11, 10, 9, 10, 11, 12],
            "Close": [10, 11, 12, 11, 10, 11, 12, 13],
            "Adj Close": [10, 11, 12, 11, 10, 11, 12, 13],
            "Volume": [100] * 8,
        }
    ).to_csv(tmp_path / "stock_data.csv", index=False)
    return tmp_path


@pytest.mark.parametrize(
    "factory", [lambda path: AgentTools(path), lambda path: PythonReplPlugin(path)]
)
def test_repl_executes_agent_signal_code_and_validates_contract(
    price_data: Path, factory
) -> None:
    result = factory(price_data).run_python_repl(SIGNAL_SCRIPT)

    assert result.startswith("SUCCESS:")
    assert (price_data / "generated_signal_strategy.py").is_file()
    signals = pd.read_csv(price_data / "stock_signals.csv")
    assert list(signals.columns) == ["BuySignal", "SellSignal", "Description"]
    assert len(signals) == 8


def test_repl_rejects_unrelated_imports(price_data: Path) -> None:
    result = AgentTools(price_data).run_python_repl("import os")

    assert result.startswith("ERROR: REPL rejected")


def test_frameworks_have_distinct_repl_implementations() -> None:
    assert AgentFrameworkRepl is not SemanticKernelRepl
    assert AgentFrameworkRepl.__module__ == "agent_framework.research_repl"
    assert SemanticKernelRepl.__module__ == "semantic_kernel.research_repl"


def test_framework_tools_match_for_the_same_script_and_prices(
    price_data: Path,
) -> None:
    agent_framework_dir = price_data / "agent_framework"
    semantic_kernel_dir = price_data / "semantic_kernel"
    agent_framework_dir.mkdir()
    semantic_kernel_dir.mkdir()
    source_prices = (price_data / "stock_data.csv").read_bytes()
    for directory in (agent_framework_dir, semantic_kernel_dir):
        (directory / "stock_data.csv").write_bytes(source_prices)

    agent_framework_tools = AgentTools(agent_framework_dir)
    semantic_kernel_repl = PythonReplPlugin(semantic_kernel_dir)
    assert agent_framework_tools.run_python_repl(SIGNAL_SCRIPT).startswith("SUCCESS:")
    assert semantic_kernel_repl.run_python_repl(SIGNAL_SCRIPT).startswith("SUCCESS:")

    assert (agent_framework_dir / "stock_signals.csv").read_bytes() == (
        semantic_kernel_dir / "stock_signals.csv"
    ).read_bytes()
    assert agent_framework_tools.backtest_strategy(10_000) == BacktestingPlugin(
        semantic_kernel_dir
    ).backtest_strategy(10_000)

