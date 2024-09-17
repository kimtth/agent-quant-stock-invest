import asyncio
import json
import os
import autogen
from textwrap import dedent
from typing import Dict
from dotenv import load_dotenv
from datetime import datetime
from autogen.coding import LocalCommandLineCodeExecutor
from autogen.code_utils import create_virtual_env
from agent.strategy_idea_agent import StrategyIdeaAgent
from agent.stock_report_agent import StockReportAgent
from agent_quant import register_tools, setup_agents
from utils.const import WORK_DIR
from utils.datamodels import WorkFlowTasks
from utils.llm_config import load_config


load_dotenv()
config_file_path = os.path.join(os.path.dirname(__file__), "OAI_CONFIG_LIST.json")
llm_config = load_config(config_file_path)

user_proxy_prompt = dedent(
    f"""
    You are responsible for executing the Python code provided by other agents.
    If the task is successful, reply TERMINATE. 
    If more steps are required, reply CONTINUE, or explain why the task has not been solved yet.
    """
)

user = autogen.UserProxyAgent(
    name="User",
    human_input_mode="NEVER",
    is_termination_msg=lambda x: x.get("content", "") is not None
    and x.get("content", "").find("TERMINATE") >= 0,
    code_execution_config={
        "last_n_messages": 1,
        "executor": LocalCommandLineCodeExecutor(
                    work_dir=WORK_DIR, timeout=600, execution_policies={"python": True}
                )
    },  # Please set use_docker=True if docker is available to run the generated code.
    system_message=user_proxy_prompt,
)

# Create a strategy idea agent
strategy_idea_agent_base = StrategyIdeaAgent(llm_config=llm_config)
strategy_idea_agent = strategy_idea_agent_base.create_agent()
strategy_idea_agent_base.register_tools(user, strategy_idea_agent)

# Create a stock performance agent
(
    agents_registry,
    group_chat,
    group_chat_manager,
) = setup_agents(llm_config)
register_tools(agents_registry)

# Create a stock report agent
stock_report_agent_base = StockReportAgent(llm_config=llm_config)
stock_report_agent = stock_report_agent_base.create_agent()


def genereate_strategy_analysis_request_message(
    investment_analysis_instructions: str, strategy_idea: Dict
) -> str:
    investment_analysis_instructions = investment_analysis_instructions.replace(
        "{indicator_str}", strategy_idea.get("strategy")
    )
    msg = dedent(
        f"""
        # Strategy Idea
        {strategy_idea}

        # Investment Analysis Instructions
        {investment_analysis_instructions}
        """
    )
    print(msg)
    return msg


def save_chat_summary(chat_summary: str):
    with open(os.path.join(WORK_DIR, "chat_summary.txt"), "a") as f:
        f.write("\n---------------------------------------\n")
        f.write(chat_summary)
        f.write("\n---------------------------------------\n")


# Define the agents that will be involved in the workflow
# https://microsoft.github.io/autogen/docs/notebooks/agentchat_multi_task_async_chats#scenario-1-solve-the-tasks-with-a-series-of-chats
async def run_workflow(workflow_tasks: WorkFlowTasks, recreate_strategy_ideas: bool = False):
    # Create a chat with the strategy idea agent
    # The agent will provide stock investing ideas using technical indicators
    if recreate_strategy_ideas:
        user.initiate_chat(
            recipient=strategy_idea_agent,
            message=workflow_tasks.stock_idea_task_description,
            summary_method="reflection_with_llm",
        )

    strategy_idea_json_path = os.path.join(
        os.path.dirname(__file__), WORK_DIR, "strategy_idea.json"
    )
    strategy_ideas = []
    with open(strategy_idea_json_path, "r") as file:
        strategy_ideas = json.load(file)

    # Create a chat with the stock performance agent and stock report agent.
    for strategy_idea in strategy_ideas:
        # Perform investment analysis and generate buy/sell signals
        # Perform backtesting and provide performance metrics
        # Create a chat with the stock report agent to generate a plot of stock prices and investment returns over time
        chat_res = await user.a_initiate_chats(
            [
                {
                    "chat_id": 1,
                    "recipient": group_chat_manager,
                    "message": genereate_strategy_analysis_request_message(
                        workflow_tasks.investment_analysis_instructions, strategy_idea
                    ),
                    "summary_method": "reflection_with_llm",
                },
                {
                    "chat_id": 2,
                    "prerequisites": [1],
                    "recipient": stock_report_agent,
                    "message": workflow_tasks.stock_report_task_instructions,
                    "summary_method": "reflection_with_llm",
                },
            ]
        )
        print("Completed analysis for strategy: ", strategy_idea)
        chat_summary = chat_res.get("summary", "")
        save_chat_summary(chat_summary)


if __name__ == "__main__":

    today = datetime.today().strftime("%Y-%m-%d")
    default_message_to_save_code = "save the code to disk."
    user_message = dedent(
        f"""
        {default_message_to_save_code}

        Run complete stock analysis for MSFT from 1995-01-01 to {today}. 
        Generate buy/sell signals using {{indicator_str}}.
        Based on the generated signals, backtest the strategy and provide performance metrics.
        """
    )

    workflow_tasks = WorkFlowTasks(
        stock_idea_task_description="create a strategy 20 ideas for stock investing using technical indicators. ",
        investment_analysis_instructions=user_message,
        stock_report_task_instructions="create a plot to display stock prices and investment returns over time",
    )

    autogen.runtime_logging.start()
    asyncio.run(run_workflow(workflow_tasks))
    autogen.runtime_logging.stop()
