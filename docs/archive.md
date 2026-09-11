# Archived AutoGen, Semantic Kernel, and ETF research

These files are historical reference material, not part of the active Microsoft Agent Framework and terminal UI project. Return to the [repository overview](../README.md) for the supported entry points.

## What's inside

- **[AutoGen stock-research agents](../.old/docs/autogen.md):** a group-chat implementation for proposing strategies, generating trading signals, backtesting, and writing reports. [Browse source](../.old/autogen).
- **[Semantic Kernel research workflow](../.old/docs/semantic_kernel.md):** plugin-based agents that fetch prices, execute generated signal code, backtest, and plot results. [Browse source](../.old/semantic_kernel).
- **[ETF research guide](etf_research.md):** 24 archived scripts with shared global USD configuration, SPY/QQQ benchmark selection, generic portfolio-history inputs, and workbook extraction. [Browse source](../.old/tools) · [Browse archived sample artifacts](../.old/output). Historical Korean-market text reports, when available locally, are not results of the refactored scripts and are not comparable to new USD runs.
- **[Cross-framework comparison tests](../.old/tests/test_research_repl.py):** checks for signal validation and equivalent backtest results across the two REPL implementations.
- **[Framework comparison](../.old/docs/autogen_agent_sk.md):** an overview of how AutoGen, Semantic Kernel, and Microsoft Agent Framework differ.

## Relocation map

Archived source trees retain their internal layout. The archive and ETF research guides live under [docs](../docs), with the root [repository overview](../README.md) as the single README entry point. Paths below are relative to the repository root.

| Previous location | Current location |
|---|---|
| `autogen/` | [.old/autogen](../.old/autogen) |
| `semantic_kernel/` | [.old/semantic_kernel](../.old/semantic_kernel) |
| `tools/` | [.old/tools](../.old/tools) |
| `.old/README.md` | [docs/archive.md](archive.md) |
| `.old/tools/README.md` | [docs/etf_research.md](etf_research.md) |
| `docs/autogen.md` | [.old/docs/autogen.md](../.old/docs/autogen.md) |
| `docs/semantic_kernel.md` | [.old/docs/semantic_kernel.md](../.old/docs/semantic_kernel.md) |
| `docs/autogen_agent_sk.md` | [.old/docs/autogen_agent_sk.md](../.old/docs/autogen_agent_sk.md) |
| `output/autogen/` | [.old/output/autogen](../.old/output/autogen) |
| `output/semantic_kernel/` | [.old/output/semantic_kernel](../.old/output/semantic_kernel) |
| Standalone `output/*.txt` research reports | Local generated artifacts only; not version controlled or included in a clean clone. |
| `tests/test_research_repl.py` (cross-framework checks) | [.old/tests/test_research_repl.py](../.old/tests/test_research_repl.py) |

The active [REPL tests](../tests/test_research_repl.py) retain Agent Framework coverage without importing Semantic Kernel. Agent Framework and TUI sources, guides, sample outputs, checkpoints, and shared development configuration remain outside this archive.

Text reports (`*.txt`) and pickle caches (`*.pkl`) are local generated artifacts, not version controlled. The archived output directory retains other sample formats; its presence does not imply that historical text reports are bundled.

## Legacy execution

- **Semantic Kernel:** from the repository root, run `uv run --group legacy --directory .old python -m semantic_kernel.main`. The optional `legacy` dependency group installs the archived SDK. Research outputs stay under [.old/output/semantic_kernel](../.old/output/semantic_kernel), regardless of the working directory. See the [guide](../.old/docs/semantic_kernel.md) for model configuration.
- **AutoGen:** use its separate Poetry project under [.old/autogen](../.old/autogen); it requires Python 3.11 or 3.12, unlike the main project's Python 3.13. See the [guide](../.old/docs/autogen.md). Outputs stay under [.old/output/autogen](../.old/output/autogen).
- **Cross-framework tests:** from the repository root, run `uv run --group legacy python -m pytest .old/tests -q`. The archive's test setup adds its packages to the import path only for this explicitly selected suite. Default tests and lint exclude the archive.
- **Standalone research tools:** from the repository root, run `uv run python .old/tools/run_research.py analyze_drawdown --benchmark SPY --start 2010-01-01 --end 2026-09-01`; `--benchmark QQQ` selects the alternative reference. SPY/QQQ controls the benchmark, fallback history, and regime where used, not every strategy's universe. Defaults are actual adjusted USD bars, 2005-01-01 through 2026-09-01 exclusive, 10 bp per side, 260 warmup sessions, and a disabled liquidity threshold. See the [ETF guide](etf_research.md) and [example configuration](../.old/tools/config.example.json) for local CSVs, asset-role overrides, and engine limitations. Network runs may require internet access; configuration-keyed caches live beside the tools by default. Private portfolio paths have been removed: supply `--history-csv`/`--compare-csv` or `--workbook` as applicable, without recreating a missing checkpoint directory. CLI paths resolve from the working directory; JSON paths resolve from the configuration file. `--output` applies only to workbook text extraction. Historical text reports may remain locally under the archived output directory, but are not bundled, regenerated, or comparable results.

The main [.env.example](../.env.example) retains the optional archived Semantic Kernel settings. Local credentials are not copied into this archive.