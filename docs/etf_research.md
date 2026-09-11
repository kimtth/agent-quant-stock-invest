# Archived ETF research tools: global USD inputs

These 24 research scripts have been globalized around shared configuration, actual USD-listed ETF histories, English console labels, and generic input paths. They **remain in the archive**, outside the active Agent Framework/TUI workflow. This is input and configuration generalization, not a unified backtest engine or validation of the historical strategy parameters.

[Repository overview](../README.md) · [Archive overview](archive.md) · [Example configuration](../.old/tools/config.example.json)

> Historical Korean-market text reports, when available locally under the [archived output directory](../.old/output), are **not results of the refactored scripts** and are not comparable to new USD runs. Text reports (`*.txt`) and pickle caches (`*.pkl`) are local generated artifacts, not version controlled or included in a clean clone. No trading profitability, out-of-sample validity, or broker-deployment equivalence is claimed.

## Run from the repository root

Use Python 3.13 and `uv` with the repository's [dependencies](../pyproject.toml). These tools do not require the archived Semantic Kernel dependency group or an agent model connection. Market-data runs can require internet access unless local adjusted bars are supplied.

The [launcher](../.old/tools/run_research.py) accepts a script name **without the extension**, prints the resolved research contract, and starts that script with the configuration in a child process.

```powershell
uv run python .old/tools/run_research.py analyze_drawdown --benchmark SPY --start 2010-01-01 --end 2026-09-01
uv run python .old/tools/run_research.py analyze_drawdown --benchmark QQQ --start 2010-01-01 --end 2026-09-01
uv run python .old/tools/run_research.py benchmark_compare --benchmark SPY --start 2010-01-01 --end 2026-09-01
uv run python .old/tools/run_research.py eval_unified --benchmark QQQ --start 2010-01-01 --end 2026-09-01
uv run python .old/tools/run_research.py analyze_drawdown --config .old/tools/config.example.json
```

Without a supplied portfolio history, the first two commands analyze a **gross adjusted-Close buy-and-hold reference**, not a reconstructed trading account. `benchmark_compare` matches SPY and QQQ to each strategy's native dates; `eval_unified` selects common post-warmup dates across its candidates. Neither makes the execution models equivalent.

The following paths are illustrative, user-supplied inputs; these datasets and workbook are not bundled:

```powershell
uv run python .old/tools/run_research.py analyze_drawdown --history-csv ./data/portfolio.csv --start 2010-01-01 --end 2026-09-01
uv run python .old/tools/run_research.py compare_v1_v2 --history-csv ./data/portfolio.csv --compare-csv ./data/comparison.csv
uv run python .old/tools/run_research.py analyze_drawdown --benchmark QQQ --data-dir ./data/adjusted-bars
uv run python .old/tools/run_research.py benchmark_compare --data-dir ./data/adjusted-bars --config .old/tools/config.example.json
uv run python .old/tools/run_research.py dump_genport_guide --workbook ./data/reference.xlsx --output ./output/workbook-text.txt
```

Direct script execution, for example `uv run python .old/tools/analyze_drawdown.py`, uses the default configuration unless `GLOBAL_RESEARCH_CONFIG` points to a JSON configuration. Individual scripts do not parse the launcher's CLI flags; use the launcher for overrides. With that environment variable unset, default imports perform no research file/network I/O, downloads, workbook reads, or report generation. An explicitly configured environment variable causes [market_config.py](../.old/tools/market_config.py) to read that JSON at import; configuration is not live-reloaded.

## Configuration contract

[config.example.json](../.old/tools/config.example.json) records all current defaults and asset roles. [ResearchConfig](../.old/tools/market_config.py) defines validation, and `load_config()` merges partial `symbols` overrides with the default roles.

| JSON field | Launcher option | Default and meaning |
|---|---|---|
| `benchmark` | `--benchmark` | `SPY`; accepts `SPY` or `QQQ`. Selects the comparison reference, fallback history, and benchmark-based calendar/regime where used. |
| `start`, `end` | `--start`, `--end` | `2005-01-01` inclusive to `2026-09-01` **exclusive**. Start must precede end. |
| `cost` | `--cost-bps` | `0.001` in JSON = 10 basis points = 0.1% per side. CLI `--cost-bps 10` gives this value. Valid decimal cost is at least zero and less than one. This is not a complete cost model. |
| `warmup` | `--warmup` | `260` sessions; must be at least 260. Used by price-based engines, not additionally removed from supplied portfolio histories. |
| `min_daily_value` | `--min-daily-value` | `0.0`, disabling the liquidity threshold by default. Finite, non-negative USD daily value, approximated by adjusted Close times Volume where the rule uses it. |
| `symbols` | JSON only | Asset-role-to-ticker map. A partial map overrides named roles; unknown roles and empty ticker strings are rejected. |
| `cache_dir` | `--cache-dir` | The global cache directory beside these tools, configured as `.cache/global` in the example. |
| `data_dir` | `--data-dir` | `null`: download adjusted bars with Yahoo Finance. Otherwise read local bars for every requested ticker. |
| `history_csv` | `--history-csv` | `null`: history-analysis tools use the selected benchmark fallback. Otherwise use the supplied daily portfolio history. |
| `compare_csv` | `--compare-csv` | `null`: must be supplied along with `history_csv` for `compare_v1_v2`. |
| `workbook`, `output` | `--workbook`, `--output` | Both `null`. **Workbook extraction tools only**: input workbook and optional text output. Without `output`, extracted text goes to stdout. This is not a general backtest report-output option. |

CLI values override `--config`; absent an explicit config, `GLOBAL_RESEARCH_CONFIG` is used if set, otherwise defaults apply. JSON paths resolve relative to the JSON file. CLI paths resolve relative to the current working directory, which is the repository root in these examples. The launcher validates the resulting configuration before executing the chosen script.

### Benchmark versus universe

**Selecting SPY or QQQ does not restrict every strategy to that ticker.** Multi-asset rotation, offensive/defensive baskets, and leveraged sleeves retain their role-based universes. Some reports show both SPY and QQQ regardless of the selected reference. Regime-enabled variants use the selected benchmark's 200-session moving average; variants without that gate remain ungated.

The full role map is visible in [config.example.json](../.old/tools/config.example.json). It includes broad equity (`SPY`/`SSO`), growth (`QQQ`/`QLD`), small caps (`IWM`/`UWM`), semiconductors (`SOXX`/`USD`), metals, Treasuries, international equity, sectors, inverse products, and defensive assets.

- **Ticker `USD` is the daily leveraged semiconductor ETF**, used by `semiconductor_2x`. It is not the dollar/currency holding.
- The `dollar` role is **`UUP`**. Some internal legacy variables named `USD` still mean this dollar role; use the role map rather than the variable name to identify the ticker.
- The `cash` role is the **`SHY` ETF**, not idle cash. Raw cash earns zero; a held cash ETF or defensive basket earns its observed market return and can lose value.
- Daily leveraged ETFs are not exact substitutes for Korean-listed products, nor do they deliver an exact multiple of multi-day index returns. Daily resets, tracking, fees, underlying exposure, market hours, and inception dates differ. Changing a role is a research assumption, not proof of product equivalence.

The liquidity threshold is a USD research input, **not a direct conversion of an old KRW cutoff**. The default zero avoids carrying a Korean notional threshold into a different market without justification.

## Market bars and coverage

[market_data.py](../.old/tools/market_data.py) uses `yfinance` with `auto_adjust=True` or local CSVs. The price-based experiments use **actual adjusted USD ETF bars only**: no pre-inception leveraged-history synthesis, fabricated volume, fitted proxy returns, or KRW FX conversion. [etf_proxy_history.py](../.old/tools/etf_proxy_history.py) retains its historical name and compatibility API but now audits actual coverage only.

For `--data-dir`, the filename pattern is `<ticker>.csv`. Provide columns `Date,Open,High,Low,Close,Volume`; OHLC prices must **already be adjusted consistently for splits and distributions**, and ETF prices must be in USD. Local input is validated, not adjusted or currency-converted by the loader. Adjustment provenance and currency are the supplier's responsibility.

- A benchmark-only fallback needs the selected benchmark's CSV. The shared multi-asset `load_all()` requests **every configured role ticker, both SPY and QQQ, and the VIX index**. Its VIX filename is `^VIX.csv`, with the same OHLCV columns (VIX levels are index points, not dollar prices). Even a report focused on one strategy can therefore need the full input set.
- Dates must be valid and unique; market bars are sorted by date and filtered to `[start, end)`. Values must be finite, OHLC prices positive, volume non-negative, and High/Low consistent with Open/Close. Missing files, columns, values, or empty requested windows fail explicitly.
- No data is invented before ETF inception. Price-engine warmup is taken from the requested history, not automatically downloaded before `start`. Later inceptions and warmup can push evaluation starts forward; several engines also require at least 250 evaluation sessions.
- The shared loader aligns observed ETF sessions to the selected benchmark calendar. Some engines forward-fill marks within observed coverage; this does not create pre-inception bars. Inspect the printed coverage and actual evaluation dates rather than assuming every run starts on the requested date.
- VIX uses the **same US session's close** when close-based signals are formed, with resulting orders intended for the next session. There is no extra Korean-market one-day VIX shift.

Network-loaded multi-asset bundles use a configuration-keyed pickle cache under `cache_dir`; only trusted locally generated caches should be used. Local CSV inputs are reread and bypass that cache. Legacy unkeyed caches are not reused. The Python API `load_all(refresh=True)` refreshes a network bundle; there is no launcher `--refresh` flag.

## Accepted daily portfolio-history CSV

[portfolio_history.py](../.old/tools/portfolio_history.py) accepts UTF-8 CSV, with or without a BOM. The required English header is `date,return,asset,cash,held`; optional `buys` adds actual daily buy counts. This schema is separate from market OHLCV input.

| English field | Accepted aliases | Units and validation |
|---|---|---|
| `date` | `날짜` | Exact ISO `YYYY-MM-DD`; rows must be unique and strictly increasing. |
| `return` | `일일수익률` | English values are **decimals**: `0.01` means +1%. Only the Korean alias is interpreted as percent and divided by 100: `1` means +1%. Return must be finite and greater than -1 after conversion. |
| `asset` | `assets`, `총자산` | Positive finite total portfolio value. Use consistent monetary units, or consistently normalized equity units. |
| `cash` | `남은 현금` | Finite cash value in the **same units as asset**, between zero and asset inclusive. It is an amount, not a percentage. |
| `held` | `남은 종목수` | Non-negative integer count of held instruments. |
| `buys` | `매수 종목수` | Non-negative integer count of bought instruments as recorded in the source export; optional except for comparison. Never inferred from returns or holdings. |

Supply only one alias per field; duplicate headers, ambiguous aliases, malformed row widths, invalid values, empty files, and empty selected windows are rejected. The **entire input is validated before date filtering**; rows are not silently sorted. Use consistent daily observations and reconcile supplied `return` and `asset` yourself: return-based metrics compound `return`, while some diagnostics use the supplied asset curve, and the reader does not reconcile the two.

Supplied histories retain their recorded returns and cost treatment. Neither the configured turnover cost nor an extra 260-session warmup is reapplied; individual overlay lookbacks remain. Values are not converted to USD: a legacy KRW history remains a KRW-history analysis and must not be relabeled as a USD result.

`compare_v1_v2` requires **both explicit histories, both with actual `buys`, and identical dates after filtering**. It does not substitute a benchmark or fabricate buy counts. For ordinary history analysis without `history_csv`, the SPY/QQQ fallback normalizes adjusted Close to initial asset 1, sets cash to 0 and held to 1, leaves buys unknown, and uses the first observation as a zero-return anchor. It is gross buy-and-hold, not an execution log.

## All 24 research scripts

Every filename below is a launcher target after removing its extension. Shared infrastructure is listed separately and is not counted among the 24 targets.

| Group | Scripts | Purpose and input |
|---|---|---|
| OHLC strategy experiments (2) | [backtest_etf_combos.py](../.old/tools/backtest_etf_combos.py), [backtest_mdd_overlay.py](../.old/tools/backtest_mdd_overlay.py) | S1–S5 multi-asset rotation; target/stop, trailing, regime and position-limit variants using market bars. |
| Return-based allocation experiments (5) | [backtest_momentum_v2.py](../.old/tools/backtest_momentum_v2.py), [backtest_sleeves.py](../.old/tools/backtest_sleeves.py), [backtest_voltarget.py](../.old/tools/backtest_voltarget.py), [backtest_final.py](../.old/tools/backtest_final.py), [backtest_genport_vol.py](../.old/tools/backtest_genport_vol.py) | Momentum ranking, independent trend sleeves, continuous/step volatility targets, combined sleeves, and historical GenPort-inspired volatility rules using market bars. |
| Drawdown overlays (6) | [analyze_drawdown.py](../.old/tools/analyze_drawdown.py), [analyze_drawdown_filters.py](../.old/tools/analyze_drawdown_filters.py), [analyze_drawdown_lockout.py](../.old/tools/analyze_drawdown_lockout.py), [analyze_drawdown_bounded.py](../.old/tools/analyze_drawdown_bounded.py), [analyze_drawdown_frozen.py](../.old/tools/analyze_drawdown_frozen.py), [analyze_drawdown_liquidate.py](../.old/tools/analyze_drawdown_liquidate.py) | Baseline diagnostics; hysteresis/graded exposure; level/edge/capped lockout; breach-count, frozen-equity and liquidation scenarios. Supplied history or benchmark fallback. |
| Overlay search and explanation (3) | [search_buy_block.py](../.old/tools/search_buy_block.py), [search_max_profit.py](../.old/tools/search_max_profit.py), [why_count_escape.py](../.old/tools/why_count_escape.py) | In-sample parameter searches and escape-rule diagnostics on supplied history or benchmark fallback; not trade reconstruction. |
| Risk-off episodes (1) | [list_out_of_market.py](../.old/tools/list_out_of_market.py) | Lists counterfactual blocked windows and return differences, not observed sell/buy events. Supplied history or benchmark fallback. |
| Recorded-history comparison (1) | [compare_v1_v2.py](../.old/tools/compare_v1_v2.py) | Two explicit, date-matched histories with buys; compares recorded activity and exploratory overlays. |
| Benchmark evaluation (2) | [benchmark_compare.py](../.old/tools/benchmark_compare.py), [eval_unified.py](../.old/tools/eval_unified.py) | Market-bar comparisons: native strategy dates versus a common-date candidate harness. Execution and exposure conventions still differ. |
| Stop diagnostics (1) | [diag_stoploss.py](../.old/tools/diag_stoploss.py) | Next-open/intraday fill logs and gap-stop diagnostics. Logged trade returns are unweighted gross price returns, not net portfolio contributions. |
| Coverage audit (1) | [etf_proxy_history.py](../.old/tools/etf_proxy_history.py) | Reports actual ETF history coverage through the shared multi-asset loader; no synthetic extension. |
| Workbook extraction (2) | [dump_genport_guide.py](../.old/tools/dump_genport_guide.py), [dump_factors.py](../.old/tools/dump_factors.py) | Extract all sheets from an explicitly supplied workbook to stdout or a text path. No market-history input required. |

Shared APIs: [run_research.py](../.old/tools/run_research.py) handles CLI configuration; [market_config.py](../.old/tools/market_config.py) defines `ResearchConfig` and `load_config()`; [market_data.py](../.old/tools/market_data.py) validates/loads OHLCV; [portfolio_history.py](../.old/tools/portfolio_history.py) supplies `Row`, `read_history()`, and `benchmark_history()`.

## Interpretation: engines and metrics are not unified

| Model | What is calculated | Important boundary |
|---|---|---|
| Next-open OHLC engine | Close-based orders are queued for the next open; intraday stops/targets use High/Low and gap-aware fill rules. A stop takes precedence if both thresholds are touched. | Daily bars do not reveal the full intraday path or guarantee executable prices. This is not equivalent to lagged close-to-close allocation. |
| Return-allocation engines | Lagged weights multiply daily close-to-close returns, with engine-specific offensive/defensive allocations and turnover deductions. | Several variants clip daily returns to ±50%. Defense-basket turnover costs are **not fully modeled**. A one-day signal lag is not a next-open fill simulation. |
| Counterfactual history overlays | Recorded daily returns are scaled by an assumed residual exposure, sometimes with path-dependent simulated equity. | A residual such as 0.35 is an assumption, not observed holdings. “Buy block,” “liquidation,” and “saved” labels do not establish actual orders, executable fills, or incremental costs/slippage. Window differences are not additive portfolio profit. |

- **CAGR** annualizes compounded growth, but history-analysis helpers use 252 sessions per year while price-engine reports commonly use elapsed calendar years. Initial equity anchors and treatment of the first return also differ.
- **MDD** is the most negative equity-to-running-peak drawdown; a less negative signed value is smaller drawdown. **MAR/Calmar** divide CAGR by absolute MDD and are undefined without drawdown. Return volatility and **Sharpe** summarize daily variability; Sharpe implementations generally divide daily mean return by sample standard deviation and scale by the square root of 252, without a risk-free-rate subtraction. The history helper instead reports population-standard-deviation volatility.
- **Worst12M** in the common-date evaluator is the worst 252-session equity change, not necessarily a calendar-year return. Printed percentages and internal decimal-return values must not be mixed.
- **Exposure** is not one shared measure: OHLC reports use invested capital; history `nonzero-return` is only the fraction of nonzero-return days; the common-date evaluator uses offensive capital for V1/CSV, clipped leverage for VT, and S1's full-run average rather than daily S1 exposure.
- The common-date evaluator retains a **legacy VT residual-cash formula** based on exposure rather than ETF capital weight, which can leave capital unallocated. Its defense-basket V1/V2 variants are not the cash-only CSV-rule variants. The GenPort-inspired `bandwidth()` function measures 20-session daily-return standard deviation in percent, **not Bollinger bandwidth**.
- Raw idle cash earns zero unless an explicit ETF/basket is held. Gross buy-and-hold references do not deduct trading costs. The configured cost is a simplified per-side input, not comprehensive treatment of defense rebalancing, spreads, market impact, taxes, or financing.
- Native basket starts, warmup and calendars can differ. `eval_unified` aligns candidate dates and applies warmup once, but its name does **not** mean all execution, cost, exposure or metric conventions are unified. Its CAGR/MDD screen and start-date sensitivity are descriptive comparisons, not deployment validation or out-of-sample tests.
- The retained **2026-05-31 split is descriptive historical context**, not a US crash boundary or a newly established train/test cutoff. Historical parameter grids, “best” labels and thresholds are not recommendations or evidence of trading profitability.

Before comparing new runs, fix the universe, observed evaluation dates, warmup, return units, benchmark, execution model, cost treatment and metric definitions. Do not combine unmatched outputs or compare new USD results to the archived Korean-market reports.

## Generic workbook utilities and historical formulas

Private portfolio paths have been removed. No missing private checkpoint directory needs to be recreated: histories use `history_csv`/`compare_csv`, and workbook tools require an explicit `workbook` path.

[dump_factors.py](../.old/tools/dump_factors.py) delegates to the same `main()` as [dump_genport_guide.py](../.old/tools/dump_genport_guide.py). Both extract all sheets, preserve original-language data text and formula strings, and do not translate or calculate workbook formulas. The Python API `workbook_text(path, only=None)` optionally selects one sheet; the launcher has no sheet-selection option. Missing/invalid workbooks, missing requested sheets, empty selections, and output equal to the input workbook are rejected. Output parent directories are created when needed; an existing text output is overwritten.

GenPort expressions and Korean formula text in source workbooks or historical reports are **historical references, not runnable broker configurations**. The globalization does not compile, validate or deploy those expressions for any broker, and the workbook tools do not modify the source workbook.