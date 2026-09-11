"""Offline tests for the Microsoft Agent Framework signal-generation REPL."""

from pathlib import Path

import pandas as pd
import pytest

from agent_framework.research_repl import ResearchPythonRepl
from agent_framework.tools import AgentTools


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


def test_repl_executes_agent_signal_code_and_validates_contract(price_data: Path) -> None:
    result = AgentTools(price_data).run_python_repl(SIGNAL_SCRIPT)

    assert result.startswith("SUCCESS:")
    assert (price_data / "generated_signal_strategy.py").is_file()
    signals = pd.read_csv(price_data / "stock_signals.csv")
    assert list(signals.columns) == ["BuySignal", "SellSignal", "Description"]
    assert len(signals) == 8


def test_repl_rejects_unrelated_imports(price_data: Path) -> None:
    result = AgentTools(price_data).run_python_repl("import os")

    assert result.startswith("ERROR: REPL rejected")


def test_agent_framework_has_its_own_repl_implementation() -> None:
    assert ResearchPythonRepl.__module__ == "agent_framework.research_repl"