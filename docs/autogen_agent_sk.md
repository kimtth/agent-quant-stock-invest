# AutoGen, Semantic Kernel, and Microsoft Agent Framework

[Repository overview](../README.md) &nbsp;|&nbsp; [Agent Framework](agent_framework.md) &nbsp;|&nbsp; [Semantic Kernel workflow](semantic_kernel.md) &nbsp;|&nbsp; [AutoGen reference](autogen.md) &nbsp;|&nbsp; [Agent Framework patterns](agent_framework_patterns.md) &nbsp;|&nbsp; **[Framework comparison](autogen_agent_sk.md)**

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
| Investment implementation in this repository | [autogen](../autogen) | [semantic_kernel](../semantic_kernel) | [agent_framework](../agent_framework) |
| Recommended use here | Reference implementation | Plugin-based variant of the Agent Framework research workflow | Primary multi-agent investment workflow and review patterns |

## Choosing an implementation

- Use [agent_framework](../agent_framework) for the primary workflow, explicit executor edges, and the current approval pattern.
- Use [semantic_kernel](../semantic_kernel) to see the same agent-authored signal and REPL pattern expressed with Semantic Kernel `ChatCompletionAgent` instances and reusable plugins.
- Use [autogen](../autogen) to study the reference conversational implementation and its group-chat model.

All three implementations create research artifacts only. They do not place trades or provide personalized investment advice.
