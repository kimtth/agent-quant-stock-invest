# Microsoft Agent Framework Investment Workflow

[Repository overview](../README.md) &nbsp;|&nbsp; **[Agent Framework](agent_framework.md)** &nbsp;|&nbsp; [Semantic Kernel workflow](semantic_kernel.md) &nbsp;|&nbsp; [AutoGen reference](autogen.md) &nbsp;|&nbsp; [Agent Framework patterns](agent_framework_patterns.md) &nbsp;|&nbsp; [Framework comparison](autogen_agent_sk.md)

## Purpose

The [Agent Framework implementation](../agent_framework) is the repository's primary agent-oriented workflow. It uses Microsoft Agent Framework with Azure AI Foundry to coordinate research-only stock-data retrieval, signal generation, backtesting, and a final written summary.

Microsoft Agent Framework is the unified successor to AutoGen and Semantic Kernel. It supplies agents for open-ended, tool-using tasks and graph-based workflows for explicit multi-step orchestration. This implementation uses a workflow because the research pipeline has a defined execution order and a conditional backtesting branch.

> The workflow produces research artifacts only. It does not provide personalised financial advice, connect to a brokerage, or submit orders.

## Architecture

```mermaid
flowchart TD
	A[Research request] --> B[Stock-data agent]
	B --> C[Signal-generation agent]
	C --> D{Signal file created?}
	D -->|Yes| E[Backtest agent]
	D -->|No| F[Summary agent]
	E --> F
	F --> G[Research-only Markdown response]
	B -. checkpoint storage .-> H[(checkpoints)]
```

`QuantInvestWorkflow` constructs the graph with `WorkflowBuilder`:

| Stage | Responsibility | Implementation |
|---|---|---|
| Stock data | Retrieves requested OHLCV history. | `stock_data_fetcher` and `AgentTools.fetch_stock_data()` |
| Signals | Produces the `BuySignal`, `SellSignal`, and `Description` dataset. | `signal_generator` |
| Conditional route | Continues to backtesting only when the structured agent response indicates success and the signal file exists. | `QuantInvestWorkflow._has_signals()` |
| Backtest | Calculates portfolio metrics and writes result artifacts. | `backtester` and `AgentTools.backtest_strategy()` |
| Summary | Writes a bounded research summary with assumptions, limitations, and risks. | `summary_reporter` |

The workflow stores checkpoints under [checkpoints](../checkpoints), emits its Mermaid graph to `output/agent_framework/workflow_diagram.mmd` after a run, and writes research artifacts below [output/agent_framework](../output/agent_framework).

## Project modules

| Module | Role |
|---|---|
| [main.py](../agent_framework/main.py) | Loads configuration, creates the workflow, runs a default research request, and optionally launches Dev UI. |
| [workflow.py](../agent_framework/workflow.py) | Defines the Foundry-agent graph, checkpoint integration, and deterministic artifact pipeline. |
| [tools.py](../agent_framework/tools.py) | Implements market-data retrieval, signal support, backtesting, plots, and output paths. |
| [models.py](../agent_framework/models.py) | Defines Pydantic research contracts and the approved strategy catalog. |

## Configuration and run

The root project requires Python 3.13. Install dependencies, copy the template, set the Foundry endpoint and model deployment, then authenticate the Azure CLI:

```bash
uv sync
cp .env.example .env
az login
uv run python -m agent_framework.main
```

On PowerShell, use `Copy-Item .env.example .env` to create the configuration file.

| Variable | Default | Purpose |
|---|---|---|
| `AZURE_AI_PROJECT_ENDPOINT` | — | Azure AI Foundry project endpoint. Required. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | — | Azure AI Foundry chat-model deployment. Required. |
| `INVESTMENT_TICKER` | `MSFT` | Ticker symbol for the research request. |
| `INVESTMENT_START_DATE` | `2020-01-01` | Inclusive market-data start date. |
| `INVESTMENT_END_DATE` | `2026-07-01` | Market-data end date passed to the data provider. |
| `INVESTMENT_INITIAL_CAPITAL` | `10000` | Simulated starting capital. |
| `LAUNCH_DEV_UI` | `false` | Set to `true` to serve the workflow in Dev UI on port 8090. |

The application calls `load_dotenv()` itself. Microsoft Agent Framework does not automatically load `.env` files.

## Research calculations

The deterministic backtesting helpers support the `macd_rsi`, `moving_average`, and `trix_uo` strategy ideas in [models.py](../agent_framework/models.py). They apply the following simplified rules:

- A position opens on a buy signal only when no position is held, and closes on a sell signal only when a position is held.
- The return for a held position is the following session's Adjusted Close percentage change, avoiding look-ahead bias.
- Duplicate buy or sell signals leave the current position unchanged.
- Metrics include cumulative return, CAGR, maximum drawdown, Sharpe ratio, and final portfolio value.
- The model does not simulate intraday fills, spread, slippage, trading fees, taxes, or corporate-action validation.

## Deterministic artifact pipeline

`ArtifactPipeline` can generate the same artifact shape without an LLM summary. The Semantic Kernel variant intentionally creates this same structure. For each requested strategy, the pipeline creates:

- `stock_data.csv`
- `stock_signals.csv`
- `backtest_results.xlsx`
- `backtest_metrics.txt`
- `stock_plot.png`

## Human review, patterns, and observability

The primary workflow does not record approvals. For a focused human-review gate, see [workflow-checkpointing.py](../agent_framework_patterns/workflow-checkpointing.py). The standalone pattern library covers agent creation, MCP, RAG, streaming, persistence, retry middleware, structured output, evaluation, observability, and declarative definitions; see [Agent Framework patterns](agent_framework_patterns.md).

Console OpenTelemetry exporters are disabled by default in the observability samples. Set `ENABLE_CONSOLE_OTEL_EXPORTERS=true` only when console traces are needed.

## Operational considerations

- Azure AI Foundry requests use Azure CLI credentials in this implementation; run `az login` before execution.
- The workflow accepts model-produced code in its signal-generation tool. Treat this as a development-only demonstration and isolate or replace it with fixed operations before production use.
- Use licensed market data and validate data quality, execution assumptions, compliance controls, and human approval requirements before any production deployment.
- For framework concepts and current APIs, see the [Microsoft Agent Framework overview](https://learn.microsoft.com/agent-framework/overview/agent-framework-overview) and [Python samples](https://github.com/microsoft/agent-framework/tree/main/python/samples).
