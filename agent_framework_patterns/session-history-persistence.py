"""Persist an investment research conversation session safely to local JSON."""

import asyncio
import json
import os
from pathlib import Path

from agent_framework import AgentSession
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv


async def main() -> None:
    load_dotenv(override=False)
    path = Path("output/agent_framework/patterns/research_session.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    session = (
        AgentSession.from_dict(json.loads(path.read_text()))
        if path.exists()
        else AgentSession()
    )
    credential = AzureCliCredential()
    agent = FoundryChatClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    ).as_agent(
        name="session_equity_researcher",
        instructions="Remember only research context. State risks and limitations; never execute or advise a trade.",
    )
    try:
        async with agent:
            response = await agent.run(
                "I am researching a long-term US equity allocation.", session=session
            )
            print(response.text)
            path.write_text(json.dumps(session.to_dict(), indent=2), encoding="utf-8")
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
