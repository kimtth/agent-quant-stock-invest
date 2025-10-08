import os
from pathlib import Path
from typing import Dict, Any, Optional
from typing_extensions import Never

from agent_framework import (
    WorkflowBuilder,
    executor,
    WorkflowContext,
    Workflow,
    AgentRunUpdateEvent,
    WorkflowOutputEvent,
    WorkflowViz,
    FileCheckpointStorage,
    RequestInfoExecutor,
    ExecutorCompletedEvent
    # handler,  # Decorator to expose an Executor method as a step
)
from agent_framework.azure import AzureOpenAIChatClient

from agent_quant import AgentCompletedResult, CreateQuantAgent
from agent_tools import AgentQuantTools
from constant import WORK_DIR, DATASET_SIGNALS


# ============================================================================
# Executor-based Workflow (Correct Agent Framework Pattern)
# ============================================================================


class QuantInvestWorkflow:
    """
    Orchestrates quantitative investment analysis using Microsoft Agent Framework.

    This uses the CORRECT pattern from the official documentation:
    - Agents are created using ChatAgent
    - Agents are wrapped as executors using @executor decorator
    - Workflows use WorkflowBuilder with add_edge() for data flow
    - Tools are defined using @ai_function
    """

    def __init__(self) -> None:
        """Initialize the workflow orchestrator."""
        self.work_dir = Path(WORK_DIR)
        self.work_dir.mkdir(exist_ok=True)

        # These will be initialized in create_workflow()
        self.client: Optional[AzureOpenAIChatClient] = None
        self.agents: Dict[str, Any] = {}
        self.tools: Optional[AgentQuantTools] = None
        self.storage: Optional[FileCheckpointStorage] = None

    async def create_workflow(self) -> Workflow:
        """
        Create the complete workflow with agents and executors.

        This is the CORRECT pattern from Microsoft Agent Framework:
        1. Create ChatClient (OpenAI or Azure)
        2. Create ChatAgents with tools
        3. Wrap agents as executors
        4. Build workflow with WorkflowBuilder

        Returns:
            Workflow: The built workflow ready for execution
        """
        # 1. Create chat client
        self.client = AzureOpenAIChatClient(
            endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
            api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
        )

        # 2. Create function tools
        self.tools = AgentQuantTools()

        # 3. Create agents with tools
        agent_creator = CreateQuantAgent(self.client, self.tools)
        self.agents = await agent_creator.create_agents()

        # 4. Create executors that wrap agents
        @executor(id="fetch_data")
        async def fetch_executor(task: str, ctx: WorkflowContext[str]) -> None:
            """Executor that fetches stock data."""
            result = await self.agents["data_agent"].run(task)  
            await ctx.send_message(result.text)

        @executor(id="generate_signals")
        async def signal_executor(msg: str, ctx: WorkflowContext[str]) -> None:
            """Executor that generates signals."""
            result = await self.agents["signal_agent"].run(msg)
            await ctx.send_message(result.text)

        @executor(id="backtest")
        async def backtest_executor(msg: str, ctx: WorkflowContext[str]) -> None:
            """Executor that backtests and yields final output."""
            # - WorkflowContext[Never, str] indicates this is a terminal executor
            result = await self.agents["backtest_agent"].run(msg)
            # - Can send messages to downstream executors via ctx.send_message()
            # - Can yield workflow-level outputs via ctx.yield_output()
            # - Can emit custom events via ctx.add_event()
            await ctx.send_message(result.text)

        @executor(id="summary_report")
        async def summary_report_executor(msg: str, ctx: WorkflowContext[Never, str]) -> None:
            """Executor that generates a summary report."""
            result = await self.agents["summary_agent"].run(msg)
            await ctx.yield_output(result.text)  # Final output

        # a. Setup checkpoint storage (optional)
        checkpoint_dir = Path("./checkpoints")
        checkpoint_dir.mkdir(exist_ok=True)
        self.storage = FileCheckpointStorage(checkpoint_dir)

        # 5. Build workflow with data-flow edges
        # In this sample, a workflow can be defined without using executors. 
        # agent-framework/python/packages/devui/samples/workflow_agents/workflow.py
        workflow = (
            WorkflowBuilder()
            .add_edge(
                fetch_executor,
                signal_executor
            )
            # Branch 1:
            .add_edge(
                signal_executor,
                backtest_executor,
                # When condition is True, the edge is taken
                condition=lambda msg: self.get_file_created_condition(msg, file_name=DATASET_SIGNALS)
            )
            .add_edge(
                backtest_executor,
                summary_report_executor
            )
            # Branch 2:
            .add_edge(
                signal_executor,
                summary_report_executor,
                # When condition is False, the edge is taken
                condition=lambda msg: self.get_file_created_condition(msg, file_name=DATASET_SIGNALS, expected_condition=False)
            )
            .set_start_executor(fetch_executor)
            .with_checkpointing(self.storage)  # Optional: Enable checkpointing
            .build()
        )

        # b. Create workflow visualization (optional)
        viz = WorkflowViz(workflow)
        # Generate Mermaid flowchart
        mermaid_content = viz.to_mermaid()
        with open(self.work_dir / "workflow_diagram.mmd", "w", encoding="utf-8") as f:
            f.write(mermaid_content)

        print("Workflow created successfully")
        return workflow

    async def run_task(
        self, workflow: Workflow, task: str, start_from_checkpoint: bool = False
    ) -> str:
        """
        Execute the complete quantitative investment workflow.

        Args:
            workflow: The built workflow to execute
            task: Investment analysis task (e.g., "Analyze AAPL using momentum strategy")

        Returns:
            str: Final analysis report with backtest results
        """
        if start_from_checkpoint:
            # List and inspect checkpoints
            checkpoints = await self.storage.list_checkpoints()
            for cp in sorted(checkpoints, key=lambda c: c.timestamp):
                summary = RequestInfoExecutor.checkpoint_summary(cp)
                print(
                    f"Checkpoint: {summary.checkpoint_id[:8]}... iter={summary.iteration_count}"
                )

            # Resume from a checkpoint
            if checkpoints:
                latest = max(checkpoints, key=lambda cp: cp.timestamp)
                print(f"Resuming from: {latest.checkpoint_id}")

                async for event in workflow.run_stream_from_checkpoint(
                    latest.checkpoint_id
                ):
                    print(f"Resumed: {event}")
        else:
            # Stream events from the workflow. We aggregate partial token updates per executor for readable output.
            last_executor_id: Optional[str] = None
            final_output = ""

            events = workflow.run_stream(task)
            async for event in events:
                if isinstance(event, AgentRunUpdateEvent):
                    # AgentRunUpdateEvent contains incremental text deltas from the underlying agent.
                    # Print a prefix when the executor changes, then append updates on the same line.
                    eid = event.executor_id
                    if eid != last_executor_id:
                        if last_executor_id is not None:
                            print()  # output a blank line
                        print(f"{eid}:", end=" ", flush=True)
                        last_executor_id = eid
                    # print(event.data, end="", flush=True)
                elif isinstance(event, WorkflowOutputEvent):
                    print("\n===== Final Output =====")
                    print(event.data)
                    final_output = event.data
                    print(final_output)
                elif isinstance(event, ExecutorCompletedEvent):
                    print(f">> Executor {event.executor_id} completed.")
                    # For Debug: print the result of each executor
                    # if event.data:
                    #    print(f"Result: {event.data}")

    def get_file_created_condition(self, message: Any, file_name: str, expected_condition: bool = True) -> bool:
        # The returned function will be used as an edge predicate.
        try:
            if not expected_condition:
                return False
            rtn = AgentCompletedResult.model_validate_json(message)
            if rtn.success and os.path.exists(os.path.join(WORK_DIR, file_name)):
                print(f"File {file_name} exists. Taking this edge.")
                return True
            else:
                return False
        except Exception:
            return False
