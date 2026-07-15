"""Serve a locally inspectable investment research agent in Agent Framework Dev UI."""

import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv


def main() -> None:
    load_dotenv(override=False)
    from agent_framework.devui import serve

    agent: Agent = FoundryChatClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    ).as_agent(
        name="devui_investment_researcher",
        instructions="Provide research-only investment analysis with risks and limitations; never make trades.",
    )
    serve(entities=[agent], port=int(os.getenv("DEV_UI_PORT", "8091")), auto_open=False)


if __name__ == "__main__":
    main()
