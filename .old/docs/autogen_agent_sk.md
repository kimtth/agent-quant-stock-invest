# AutoGen, Semantic Kernel, and Microsoft Agent Framework

[Repository overview](../../README.md) &nbsp;|&nbsp; [Agent Framework](../../docs/agent_framework.md) &nbsp;|&nbsp; [Agent Framework patterns](../../docs/agent_framework_patterns.md) &nbsp;|&nbsp; [TUI](../../docs/chart_cli.md) &nbsp;|&nbsp; [Archive guide](../../docs/archive.md)

Archive: [AutoGen reference](autogen.md) &nbsp;|&nbsp; [Semantic Kernel workflow](semantic_kernel.md) &nbsp;|&nbsp; **[Framework comparison](autogen_agent_sk.md)**

> **Archived comparison:** This guide is retained for historical reference and migration study. AutoGen and Semantic Kernel code, guides, outputs, and shared comparison tests are archived. Only Microsoft Agent Framework, its patterns, and the TUI remain active.

## Initial public releases

| Framework | Initial public release | Notes |
|---|---|---|
| **AutoGen** | **August 2023** | AutoGen was introduced with the research paper **“AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation”**, published on **August 16, 2023**. The open-source project was released around the same time. |
| **Semantic Kernel** | **April 2023** | Microsoft publicly announced and open-sourced Semantic Kernel in **April 2023** as an SDK for integrating LLMs into applications. |
| **Microsoft Agent Framework** | **October 2025** | Microsoft announced the merged framework as the common direction for AutoGen multi-agent orchestration and Semantic Kernel enterprise SDK capabilities. |

## Timeline

- **April 2023** – **Semantic Kernel** released by Microsoft.
- **August 2023** – **AutoGen** released by Microsoft Research.
- **November 18, 2024** – Microsoft announced that AutoGen and Semantic Kernel would collaborate more closely, aligning AutoGen’s multi-agent runtime with Semantic Kernel’s enterprise capabilities.
- **January 17, 2025** – Microsoft released **AutoGen 0.4**, a major redesign of the framework.
- **October 2025** – Microsoft announced that **AutoGen and Semantic Kernel would merge into the Microsoft Agent Framework**, combining AutoGen’s multi-agent orchestration with Semantic Kernel’s enterprise-ready SDK.

## Practical comparison

| Concern | AutoGen | Semantic Kernel | Microsoft Agent Framework |
|---|---|---|---|
| Primary model | Conversational multi-agent runtime | Application SDK with plugins and services | Unified agent and workflow platform |
| Coordination | Group chats, handoffs, and agent conversations | Tool-using `ChatCompletionAgent` instances and plugins | Directed workflows, agents, tools, and durable execution |
| Investment implementation in this repository | [.old/autogen](../autogen) | [.old/semantic_kernel](../semantic_kernel) | [agent_framework](../../agent_framework) |
| Recommended use here | Archived conversational reference | Archived plugin-based variant | Active primary multi-agent investment workflow and review patterns |

## Choosing an implementation

- Use [agent_framework](../../agent_framework) for the active primary workflow and explicit executor edges; see the [Agent Framework patterns](../../docs/agent_framework_patterns.md) for the human-review gate and the [TUI](../../docs/chart_cli.md) for the terminal dashboard.
- Consult the archived [.old/semantic_kernel](../semantic_kernel) implementation to study the agent-authored signal and REPL pattern expressed with Semantic Kernel `ChatCompletionAgent` instances and reusable plugins.
- Consult the archived [.old/autogen](../autogen) implementation to study the conversational reference and its group-chat model.

All three implementations create research artifacts only. They do not place trades or provide personalized investment advice.
