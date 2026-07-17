"""Semantic Kernel agents orchestrating a REPL-driven research workflow."""

import os
from pathlib import Path
from urllib.parse import urlparse

from azure.ai.inference.aio import ChatCompletionsClient
from azure.identity import AzureCliCredential
from azure.identity.aio import AzureCliCredential as AsyncAzureCliCredential
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.azure_ai_inference import (
    AzureAIInferenceChatCompletion,
)
from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

from .tools import (
    BacktestingPlugin,
    MarketResearchPlugin,
    PythonReplPlugin,
    ReportingPlugin,
    StockDataPlugin,
)

WORK_DIR = Path("output") / "semantic_kernel"


class InvestmentWorkflow:
    """Coordinate tool-using Semantic Kernel agents for one research request."""

    def __init__(self, output_dir: Path = WORK_DIR) -> None:
        self.output_dir = output_dir
        self.repl = PythonReplPlugin(output_dir)
        self.data = StockDataPlugin(output_dir)
        self.backtest = BacktestingPlugin(output_dir)
        self.reporting = ReportingPlugin(output_dir)
        self.market_research = MarketResearchPlugin()
        self._inference_client: ChatCompletionsClient | None = None
        self._inference_credential: AsyncAzureCliCredential | None = None
        self.service = self._create_chat_service()
        tool_choice = FunctionChoiceBehavior.Auto(auto_invoke=True)
        self.agents = {
            "data": ChatCompletionAgent(
                service=self.service,
                name="stock_data_fetcher",
                instructions=(
                    "Fetch the requested historical OHLCV data with fetch_stock_data. "
                    "Use the ticker and dates in the user request, call the tool exactly once, "
                    "and report the result. This is research, not investment advice."
                ),
                plugins=[self.data],
                function_choice_behavior=tool_choice,
            ),
            "signal": ChatCompletionAgent(
                service=self.service,
                name="signal_generator",
                instructions=(
                    "Develop one transparent technical-analysis hypothesis for the request, author "
                    "Python code, and execute it with run_python_repl. The code must read INPUT_PATH "
                    "and write OUTPUT_PATH with exactly BuySignal, SellSignal, and Description columns. "
                    "Use only pandas as pd, numpy as np, and ta. Do not access the network, shell, "
                    "environment variables, or any other files. Call the REPL rather than returning "
                    "code in prose. Correct errors and retry up to three times. Research only."
                ),
                plugins=[self.repl],
                function_choice_behavior=tool_choice,
            ),
            "backtest": ChatCompletionAgent(
                service=self.service,
                name="backtester",
                instructions=(
                    "Call backtest_strategy once for the generated signal file. Use the requested "
                    "initial capital if stated, otherwise 10000. Report tool metrics as historical "
                    "research and not investment advice."
                ),
                plugins=[self.backtest],
                function_choice_behavior=tool_choice,
            ),
            "plot": ChatCompletionAgent(
                service=self.service,
                name="performance_plotter",
                instructions="Call plot_performance once after a successful backtest and report the result.",
                plugins=[self.reporting],
                function_choice_behavior=tool_choice,
            ),
            "summary": ChatCompletionAgent(
                service=self.service,
                name="summary_reporter",
                instructions=(
                    "Write a concise Markdown research report from workflow results. Include the "
                    "generated-strategy outcome, metrics when available, assumptions, limitations, "
                    "and risks. Never recommend, advise, or execute trades."
                ),
            ),
        }

    async def run(self, task: str) -> str:
        """Run the data → REPL → backtest → plot → summary agent sequence."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.repl.clear_run_artifacts()
        for name in ("backtest_results.xlsx", "backtest_metrics.txt", "stock_plot.png"):
            (self.output_dir / name).unlink(missing_ok=True)

        data = str(await self.agents["data"].get_response(task))
        signal = str(
            await self.agents["signal"].get_response(
                f"Original request:\n{task}\n\nData-agent result:\n{data}"
            )
        )
        if not (self.output_dir / "stock_signals.csv").is_file():
            return await self._summarize(task, data=data, signal=signal)

        backtest = str(
            await self.agents["backtest"].get_response(
                f"Original request:\n{task}\n\nSignal-agent result:\n{signal}"
            )
        )
        plot = str(await self.agents["plot"].get_response(backtest))
        return await self._summarize(
            task, data=data, signal=signal, backtest=backtest, plot=plot
        )

    async def _summarize(self, task: str, **results: str) -> str:
        context = "\n\n".join(
            [f"Original request:\n{task}"]
            + [f"{name.title()} agent result:\n{result}" for name, result in results.items()]
        )
        return str(await self.agents["summary"].get_response(context))

    def _create_chat_service(
        self,
    ) -> AzureAIInferenceChatCompletion | AzureChatCompletion:
        azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        azure_openai_deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
        if azure_openai_endpoint and azure_openai_deployment:
            return AzureChatCompletion(
                deployment_name=azure_openai_deployment,
                endpoint=azure_openai_endpoint,
                credential=AzureCliCredential(),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            )

        project_endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
        parsed = urlparse(project_endpoint)
        if not parsed.scheme or not parsed.netloc or "/api/projects/" not in parsed.path:
            raise ValueError(
                "AZURE_AI_PROJECT_ENDPOINT must be a Foundry project endpoint, or set "
                "AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME."
            )
        self._inference_credential = AsyncAzureCliCredential()
        self._inference_client = ChatCompletionsClient(
            endpoint=f"{parsed.scheme}://{parsed.netloc}/models",
            credential=self._inference_credential,
            credential_scopes=["https://cognitiveservices.azure.com/.default"],
        )
        return AzureAIInferenceChatCompletion(
            ai_model_id=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            client=self._inference_client,
        )

    async def close(self) -> None:
        """Release the Azure AI Inference resources when the workflow is finished."""
        if self._inference_client is not None:
            await self._inference_client.close()
        if self._inference_credential is not None:
            await self._inference_credential.close()
