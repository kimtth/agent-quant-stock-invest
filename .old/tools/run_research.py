"""Run any research script with a shared, explicit SPY/QQQ configuration."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HELPERS = {"market_config", "market_data", "portfolio_history", "run_research"}
SCRIPTS = sorted(p.stem for p in ROOT.glob("*.py") if p.stem not in HELPERS)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", choices=SCRIPTS)
    parser.add_argument("--config", type=Path, help="JSON configuration; CLI values override it")
    parser.add_argument("--benchmark", choices=["SPY", "QQQ"])
    parser.add_argument("--start", help="Inclusive history start, YYYY-MM-DD")
    parser.add_argument("--end", help="Exclusive history end, YYYY-MM-DD")
    parser.add_argument("--cost-bps", type=float, help="One-way turnover cost in basis points")
    parser.add_argument("--warmup", type=int)
    parser.add_argument("--min-daily-value", type=float, help="Minimum daily dollar volume in USD")
    for arg in ("data-dir", "history-csv", "compare-csv", "workbook", "output", "cache-dir"):
        parser.add_argument(f"--{arg}", type=Path)
    args = parser.parse_args(argv)
    from market_config import load_config

    values = load_config(args.config).manifest()
    for key in ("benchmark", "start", "end", "warmup", "min_daily_value",
                "data_dir", "history_csv", "compare_csv", "workbook", "output", "cache_dir"):
        value = getattr(args, key)
        if value is not None:
            values[key] = str(value.resolve()) if isinstance(value, Path) else value
    if args.cost_bps is not None:
        values["cost"] = args.cost_bps / 10_000
    with tempfile.TemporaryDirectory(prefix="global-research-") as directory:
        config_path = Path(directory) / "config.json"
        config_path.write_text(json.dumps(values), encoding="utf-8")
        config = load_config(config_path)
        print("Research contract:", json.dumps(config.manifest(), sort_keys=True), flush=True)
        print("USD nominal returns; cash earns zero unless a cash ETF is held. "
              "Exploratory in-sample results, not investment recommendations.", flush=True)
        env = os.environ.copy()
        env["GLOBAL_RESEARCH_CONFIG"] = str(config_path)
        result = subprocess.run([sys.executable, str(ROOT / f"{args.script}.py")], env=env)
    return result.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileNotFoundError) as exc:
        raise SystemExit(str(exc)) from exc