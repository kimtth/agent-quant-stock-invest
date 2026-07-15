"""Define an in-process, read-only investment-risk skill."""

import asyncio
import os

from agent_framework import AgentSession, InlineSkill, SkillFrontmatter, SkillsProvider
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv


risk_skill = InlineSkill(
    frontmatter=SkillFrontmatter(
        name="investment-risk-review", description="Read-only investment risk taxonomy."
    ),
    instructions="Use this skill for risk questions. Always distinguish market, liquidity, concentration, and model risks.",
)


@risk_skill.resource(description="Investment research guardrails")
def investment_guardrails() -> str:
    return "Research only. Verify sources, date observations, disclose uncertainty, and never execute or recommend a trade."


async def main() -> None:
    load_dotenv(override=False)
    credential = AzureCliCredential()
    agent = FoundryChatClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    ).as_agent(
        name="skill_enabled_researcher",
        instructions="Provide cautious investment research.",
        context_providers=[
            SkillsProvider(
                [risk_skill],
                disable_load_skill_approval=True,
                disable_read_skill_resource_approval=True,
                disable_run_skill_script_approval=True,
            )
        ],
    )
    try:
        async with agent:
            print(
                (
                    await agent.run(
                        "What risks should I review for a concentrated equity position?",
                        session=AgentSession(),
                    )
                ).text
            )
    finally:
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
