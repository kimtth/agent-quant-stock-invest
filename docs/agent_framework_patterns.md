# Agent Framework Investment Pattern Library

[Repository overview](../README.md) &nbsp;|&nbsp; [Agent Framework](agent_framework.md) &nbsp;|&nbsp; [Semantic Kernel workflow](semantic_kernel.md) &nbsp;|&nbsp; [AutoGen reference](autogen.md) &nbsp;|&nbsp; **[Agent Framework patterns](agent_framework_patterns.md)** &nbsp;|&nbsp; [Framework comparison](autogen_agent_sk.md)

This is the repository's only pattern library. Each Markdown reference in [agent_framework_patterns/patterns](../agent_framework_patterns/patterns) has a corresponding **standalone** Python implementation in [agent_framework_patterns](../agent_framework_patterns). The scripts use Microsoft Agent Framework directly; they do not import a shared pattern helper or another pattern script. Semantic Kernel and AutoGen do not have separate pattern implementations in this repository.

All examples are research-only demonstrations. They must describe assumptions, risks, and limitations where applicable. They do not provide personalised investment advice, connect to a brokerage, submit orders, or route transactions.

## Configuration

Most LLM-backed examples require the following variables in `.env` or the process environment:

| Variable | Purpose |
|---|---|
| `AZURE_AI_PROJECT_ENDPOINT` | Azure AI Foundry project endpoint. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Chat model deployment used by `FoundryChatClient`. |

The scripts use `AzureCliCredential`; authenticate locally with Azure CLI before running an LLM-backed example. Individual Azure integration examples require the additional variables shown below and fail with a clear setup message when their optional package is unavailable.

| Pattern | Additional configuration |
|---|---|
| Cosmos history | `AZURE_COSMOS_ENDPOINT`, optional `AZURE_COSMOS_DATABASE` and `AZURE_COSMOS_CONTAINER`; install `agent-framework-azure-cosmos`. |
| Azure AI Search RAG | `AZURE_AI_SEARCH_ENDPOINT`, `AZURE_AI_SEARCH_INDEX`; install `agent-framework-azure-ai-search`. |
| Foundry file search | `FOUNDRY_INVESTMENT_VECTOR_STORE_ID`. |
| Bing grounding | `FOUNDRY_BING_CONNECTION_ID`. |
| Local market-data MCP | `MARKET_DATA_MCP_COMMAND`, optional `MARKET_DATA_MCP_ARGS`. |
| Foundry toolbox MCP | `FOUNDRY_INVESTMENT_TOOLBOX_URL`. |
| Azure Monitor | `APPLICATIONINSIGHTS_CONNECTION_STRING` and Azure Monitor OpenTelemetry dependencies. |

## Pattern implementations

### Agent construction and composition

| Pattern | Investment scenario | Script |
|---|---|---|
| Canonical agent creation | Creates a valuation-research agent with a bounded, read-only tool. | [canonical-agent-creation.py](../agent_framework_patterns/canonical-agent-creation.py) |
| Agent as MCP server | Exposes volatility research as one stdio MCP tool. | [agent-as-mcp-server.py](../agent_framework_patterns/agent-as-mcp-server.py) |
| Agent as tool handoff | Delegates valuation and risk analysis to specialist agents. | [agent-as-tool-handoff.py](../agent_framework_patterns/agent-as-tool-handoff.py) |
| Multi-agent workflow | Chains market context, risk review, and research writing. | [multi-agent-workflow.py](../agent_framework_patterns/multi-agent-workflow.py) |
| Workflow as agent nesting | Exposes deterministic ticker scoping to a parent agent. | [workflow-as-agent-nesting.py](../agent_framework_patterns/workflow-as-agent-nesting.py) |
| Harness agent | Plans evidence-led equity research across a bounded context window. | [harness-agent.py](../agent_framework_patterns/harness-agent.py) |
| Background agents | Delegates fundamentals and risk questions concurrently. | [background-agents.py](../agent_framework_patterns/background-agents.py) |

### Output, context, and reliability

| Pattern | Investment scenario | Script |
|---|---|---|
| Structured output | Validates an investment thesis, catalysts, risks, limitations, and confidence with Pydantic. | [structured-output-pydantic.py](../agent_framework_patterns/structured-output-pydantic.py) |
| Streaming output | Streams a market-risk briefing. | [streaming-output.py](../agent_framework_patterns/streaming-output.py) |
| Session history | Saves a research conversation session to a local JSON file. | [session-history-persistence.py](../agent_framework_patterns/session-history-persistence.py) |
| Cosmos history | Persists research history using the official Cosmos provider. | [persistent-history-cosmos.py](../agent_framework_patterns/persistent-history-cosmos.py) |
| Middleware retry | Retries transient failures while retaining data-freshness controls. | [agent-middleware-retry.py](../agent_framework_patterns/agent-middleware-retry.py) |
| Error handling | Reports service and transport failures without inventing market facts. | [error-handling.py](../agent_framework_patterns/error-handling.py) |
| Workflow checkpointing | Validates research intake and emits a human-review gate. | [workflow-checkpointing.py](../agent_framework_patterns/workflow-checkpointing.py) |

### Grounding and external tools

| Pattern | Investment scenario | Script |
|---|---|---|
| Azure AI Search RAG | Grounds answers in indexed filings or research documents. | [rag-with-azure-ai-search.py](../agent_framework_patterns/rag-with-azure-ai-search.py) |
| Foundry file search | Searches an investment vector store for filing evidence. | [rag-with-file-search.py](../agent_framework_patterns/rag-with-file-search.py) |
| Hosted Bing search | Produces dated, cited market-news research. | [hosted-bing-search.py](../agent_framework_patterns/hosted-bing-search.py) |
| Local MCP stdio | Uses an allow-listed local market-data tool. | [local-mcp-stdio.py](../agent_framework_patterns/local-mcp-stdio.py) |
| Foundry toolbox MCP | Uses allow-listed remote filing and market-snapshot tools. | [foundry-toolbox-mcp-http.py](../agent_framework_patterns/foundry-toolbox-mcp-http.py) |
| Inline skill | Adds an in-process investment-risk taxonomy skill. | [inline-skill-definition.py](../agent_framework_patterns/inline-skill-definition.py) |

### Evaluation, observability, and deployment

| Pattern | Investment scenario | Script |
|---|---|---|
| Local evaluation | Checks research briefs for required risk and limitation language. | [agent-evaluation-local.py](../agent_framework_patterns/agent-evaluation-local.py) |
| Foundry evaluation | Applies Foundry groundedness and relevance evaluation. | [agent-evaluation-foundry.py](../agent_framework_patterns/agent-evaluation-foundry.py) |
| Workflow evaluation | Scores the analyst and reviewer stages of a workflow. | [workflow-evaluation.py](../agent_framework_patterns/workflow-evaluation.py) |
| OpenTelemetry | Configures traces for a research-only agent; set `ENABLE_CONSOLE_OTEL_EXPORTERS=true` to export them to the console. | [observability-otel.py](../agent_framework_patterns/observability-otel.py) |
| Azure Monitor | Sends non-sensitive telemetry to Application Insights. | [observability-azure-monitor.py](../agent_framework_patterns/observability-azure-monitor.py) |
| Workflow tracing | Traces deterministic data-freshness and disclosure stages. | [observability-workflow-tracing.py](../agent_framework_patterns/observability-workflow-tracing.py) |
| Dev UI | Serves an inspectable local research agent. | [devui-local-development.py](../agent_framework_patterns/devui-local-development.py) |
| Prompt-agent conversion | Converts a local research agent into a Foundry prompt-agent definition. | [foundry-prompt-agent.py](../agent_framework_patterns/foundry-prompt-agent.py) |
| Declarative agent | Loads a beta declarative investment research agent. | [declarative-agent.py](../agent_framework_patterns/declarative-agent.py) |
| Declarative workflow | Loads a beta declarative research-intake workflow. | [declarative-workflow.py](../agent_framework_patterns/declarative-workflow.py) |

## Verification

The pytest suite is intentionally offline: it never requires Foundry credentials or calls external market-data services. It contains one behavior-focused test module for each standalone pattern script, plus shared test doubles in [helpers.py](../tests/agent_framework_patterns/helpers.py).

Run the full checks from the repository root:

```powershell
uv run ruff check agent_framework_patterns tests/agent_framework_patterns
uv run pytest tests/agent_framework_patterns -q
```
