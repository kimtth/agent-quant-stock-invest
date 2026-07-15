"""Send investment research telemetry to Azure Monitor without sensitive prompts."""

import asyncio
import os

from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv


async def main() -> None:
    load_dotenv(override=False)
    try:
        from agent_framework.observability import configure_azure_monitor
    except ImportError as error:
        raise SystemExit(
            "Install Azure Monitor OpenTelemetry dependencies to use this pattern."
        ) from error
    configure_azure_monitor(
        connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"],
        enable_sensitive_telemetry=False,
    )
    credential = AzureCliCredential()
    agent = FoundryChatClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    ).as_agent(
        name="azure_monitored_researcher",
        instructions="Produce research-only investment analysis; do not collect account data or place trades.",
    )
    try:
        async with agent:
            print(
                (
                    await agent.run(
                        "List the risks to validate before comparing equity ETFs."
                    )
                ).text
            )
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
