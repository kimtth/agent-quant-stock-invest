"""Development-only REPL for Agent Framework signal-generation scripts.

This REPL reads the workflow's price CSV and writes a validated signal CSV. It is
not a security boundary; run it only in an isolated development environment.
"""

from __future__ import annotations

import ast
import builtins
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import re
import traceback

import numpy as np
import pandas as pd
import ta

DATASET_STOCK = "stock_data.csv"
DATASET_SIGNALS = "stock_signals.csv"
GENERATED_SIGNAL_SCRIPT = "generated_signal_strategy.py"

_ALLOWED_IMPORTS = {"pandas", "numpy", "ta"}
_DISALLOWED_NAMES = {
    "__import__",
    "breakpoint",
    "compile",
    "delattr",
    "eval",
    "exec",
    "getattr",
    "globals",
    "help",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}
_SAFE_BUILTINS = {
    name: getattr(builtins, name)
    for name in (
        "Exception",
        "KeyError",
        "TypeError",
        "ValueError",
        "abs",
        "all",
        "any",
        "bool",
        "dict",
        "enumerate",
        "float",
        "int",
        "isinstance",
        "len",
        "list",
        "max",
        "min",
        "print",
        "range",
        "round",
        "set",
        "sorted",
        "str",
        "sum",
        "tuple",
        "zip",
    )
}
_SAFE_BUILTINS["__import__"] = builtins.__import__


class ResearchPythonRepl:
    """Execute and validate one Agent Framework signal-generation script."""

    def __init__(self, work_dir: Path) -> None:
        self.work_dir = Path(work_dir)
        self.input_path = self.work_dir / DATASET_STOCK
        self.output_path = self.work_dir / DATASET_SIGNALS
        self.script_path = self.work_dir / GENERATED_SIGNAL_SCRIPT

    def clear_run_artifacts(self) -> None:
        """Remove output that could make a later tool call appear successful."""
        for path in (self.output_path, self.script_path):
            path.unlink(missing_ok=True)

    def execute(self, code: str) -> str:
        """Run code against the known CSV contract and report actionable diagnostics."""
        self.work_dir.mkdir(parents=True, exist_ok=True)
        if not self.input_path.is_file():
            return (
                f"ERROR: Input data is missing: {self.input_path}. "
                "Call fetch_stock_data before running a signal script."
            )

        source = self._extract_source(code)
        try:
            tree = ast.parse(source, filename=str(self.script_path), mode="exec")
            self._validate_ast(tree)
        except (SyntaxError, ValueError) as error:
            return f"ERROR: REPL rejected the submitted script: {error}"

        self.clear_run_artifacts()
        self.script_path.write_text(source, encoding="utf-8")
        stdout = StringIO()
        namespace = {
            "__builtins__": _SAFE_BUILTINS,
            "INPUT_PATH": str(self.input_path),
            "OUTPUT_PATH": str(self.output_path),
            "WORK_DIR": str(self.work_dir),
            "INPUT_FILE": DATASET_STOCK,
            "OUTPUT_FILE": DATASET_SIGNALS,
            "pd": pd,
            "pandas": pd,
            "np": np,
            "numpy": np,
            "ta": ta,
        }
        try:
            with redirect_stdout(stdout):
                exec(compile(tree, str(self.script_path), "exec"), namespace, namespace)
            return self._validate_output(stdout.getvalue())
        except Exception as error:
            return (
                "ERROR: REPL execution failed. "
                f"{type(error).__name__}: {error}\n"
                f"Traceback:\n{traceback.format_exc()}\n"
                "Fix the script and call run_python_repl again."
            )

    def _validate_output(self, stdout: str) -> str:
        if not self.output_path.is_file():
            return (
                f"ERROR: Script completed but did not create {self.output_path}. "
                "Write BuySignal, SellSignal, and Description to OUTPUT_PATH."
            )

        try:
            prices = pd.read_csv(self.input_path)
            signals = pd.read_csv(self.output_path)
        except Exception as error:
            return f"ERROR: Unable to read the generated signal CSV: {error}"

        required = {"BuySignal", "SellSignal", "Description"}
        missing = required.difference(signals.columns)
        if missing:
            return (
                "ERROR: Signal CSV is missing required columns: "
                f"{', '.join(sorted(missing))}."
            )
        if len(prices) != len(signals):
            return (
                "ERROR: Signal rows must align with price rows "
                f"({len(signals)} signals for {len(prices)} prices)."
            )

        try:
            signals["BuySignal"] = self._to_boolean(signals["BuySignal"], "BuySignal")
            signals["SellSignal"] = self._to_boolean(signals["SellSignal"], "SellSignal")
        except ValueError as error:
            return f"ERROR: {error}"
        signals["Description"] = signals["Description"].fillna("").astype(str)
        signals.loc[:, ["BuySignal", "SellSignal", "Description"]].to_csv(
            self.output_path, index=False
        )

        buy_count = int(signals["BuySignal"].sum())
        sell_count = int(signals["SellSignal"].sum())
        message = (
            "SUCCESS: REPL executed and validated the signal contract. "
            f"Generated {buy_count} buy signals and {sell_count} sell signals. "
            f"Script: {self.script_path}; signals: {self.output_path}."
        )
        return f"{message}\nOutput:\n{stdout}" if stdout else message

    @staticmethod
    def _extract_source(code: str) -> str:
        source = code.strip()
        fenced = re.fullmatch(r"```(?:python)?\s*\n?(.*?)\n?```", source, re.DOTALL)
        return fenced.group(1).strip() if fenced else source

    @staticmethod
    def _to_boolean(values: pd.Series, column: str) -> pd.Series:
        if pd.api.types.is_bool_dtype(values):
            return values.fillna(False).astype(bool)
        if pd.api.types.is_numeric_dtype(values):
            return values.fillna(0).astype(float).ne(0)
        normalized = values.fillna("false").astype(str).str.strip().str.lower()
        valid = {"true", "false", "1", "0", "yes", "no", "y", "n"}
        invalid = normalized.loc[~normalized.isin(valid)].unique()
        if len(invalid):
            raise ValueError(
                f"{column} must contain booleans, 0/1, or true/false values; "
                f"found {', '.join(map(str, invalid[:3]))}."
            )
        return normalized.isin({"true", "1", "yes", "y"})

    @staticmethod
    def _validate_ast(tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".", 1)[0] not in _ALLOWED_IMPORTS:
                        raise ValueError(f"Import '{alias.name}' is not allowed.")
            elif isinstance(node, ast.ImportFrom):
                if not node.module or node.module.split(".", 1)[0] not in _ALLOWED_IMPORTS:
                    raise ValueError(f"Import from '{node.module}' is not allowed.")
            elif isinstance(node, ast.Name) and node.id in _DISALLOWED_NAMES:
                raise ValueError(f"'{node.id}' is not available in the REPL.")
            elif isinstance(node, ast.Attribute) and node.attr.startswith("_"):
                raise ValueError("Private attributes are not available in the REPL.")
