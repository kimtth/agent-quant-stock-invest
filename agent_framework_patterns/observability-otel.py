"""Emit OpenTelemetry traces for a research-only investment agent."""

import asyncio
import os

from agent_framework.foundry import FoundryChatClient
from agent_framework.observability import configure_otel_providers
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv


async def main() -> None:
    load_dotenv(override=False)
    configure_otel_providers(
        enable_console_exporters=os.getenv("ENABLE_CONSOLE_OTEL_EXPORTERS", "").lower()
        in {"1", "true", "yes"}
    )
    credential = AzureCliCredential()
    agent = FoundryChatClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    ).as_agent(
        name="traced_investment_researcher",
        instructions="Provide research-only investment analysis with risks and limitations.",
    )
    try:
        async with agent:
            print(
                (await agent.run("Outline risks in a balanced equity allocation.")).text
            )
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
