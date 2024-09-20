import asyncio
import json
import os
import re
import autogen
import time
from textwrap import dedent
from typing import Dict, List
from dotenv import load_dotenv
from datetime import datetime
from autogen import ChatResult
from agent.strategy_idea_agent import StrategyIdeaAgent
from agent.stock_report_agent import StockReportAgent
from agent.user_proxy_agent import UserProxyReportAgent
from agent_quant import register_tools, setup_agents
from utils.const import (
    BACKTEST_METRICS_FILE,
    BACKTEST_RESULTS_FILE,
    CHAT_SUMMARY_FILE_NAME,
    DATASET_SIGNALS,
    DATASET_STOCK,
    PLOT_FILE_NAME,
    SUMMARY_PROMPT,
    WORK_DIR,
    STRATEGY_IDEAS,
    AgentName,
)
from utils.datamodels import WorkFlowTasks
from utils.functions import backtest_stock_strategy
from utils.llm_config import load_config


load_dotenv()
config_file_path = os.path.join(os.path.dirname(__file__), "OAI_CONFIG_LIST.json")
llm_config = load_config(config_file_path)

# 1. Create a user proxy agent
user_report_proxy = UserProxyReportAgent().create_user_proxy()

# 2. Create a strategy idea agent
strategy_idea_agent_base = StrategyIdeaAgent(llm_config=llm_config)
strategy_idea_agent = strategy_idea_agent_base.create_agent()
strategy_idea_agent_base.register_tools(user_report_proxy, strategy_idea_agent)

# 3. Create a stock performance group chat
(
    agents_registry,
    group_chat,
    group_chat_manager,
) = setup_agents(llm_config)
register_tools(agents_registry)

# 4. Create a stock report agent
stock_report_agent_base = StockReportAgent(llm_config=llm_config)
stock_report_agent = stock_report_agent_base.create_agent()
stock_report_agent_base.register_tools(user_report_proxy, stock_report_agent)


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


def save_stock_performance_data(
    strategy_idea: Dict, chat_res: ChatResult, custom_signal_agent_messages: List[Dict], verbose_output: bool = False
):
    stock_performance_dir_name: str = strategy_idea.get("strategy")
    # make dir for stock performance data
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized_stock_performance_dir_name = re.sub(
        invalid_chars, "_", stock_performance_dir_name
    )

    os.makedirs(
        os.path.join(WORK_DIR, sanitized_stock_performance_dir_name), exist_ok=True
    )
    time.sleep(0.1)

    # Generate the chat summary
    chat_history = f"{os.linesep}".join(
        [entry["content"] for entry in chat_res.chat_history]
    )
    chat_summary = chat_res.summary
    cost = json.dumps(chat_res.cost, indent=4)
    # If the chat summary is empty, use the last message from the custom_signal_analysis_agent
    if not chat_summary:
        # loop the list by reverse order
        for message in reversed(custom_signal_agent_messages):
            if "content" in message:
                tmp_chat_summary = message["content"]
                if 'import' in tmp_chat_summary: # To find last success python code block.
                    chat_summary = tmp_chat_summary
                    break

    # Format the output
    chat_summary_output = (
        f"{os.linesep}# Summary: {chat_summary}{os.linesep}"
        f"# Cost: {cost}{os.linesep}"
        f"# Chat History: {chat_history}{os.linesep}"
    )

    # Save the chat summary to the stock performance dir
    with open(
        os.path.join(WORK_DIR, stock_performance_dir_name, CHAT_SUMMARY_FILE_NAME), "w"
    ) as f:
        sep = "-" * 50
        f.write(chat_summary_output)
        f.write(f"{sep}{os.linesep}")

    # Save results to the stock performance dir
    if verbose_output:
        # copy the files to the stock performance dir
        file_names = [
            BACKTEST_RESULTS_FILE,
            BACKTEST_METRICS_FILE,
            DATASET_STOCK,
            DATASET_SIGNALS,
            PLOT_FILE_NAME,
        ]
        for file_name in file_names:
            src_file_path = os.path.join(WORK_DIR, file_name)
            dest_file_path = os.path.join(
                WORK_DIR, stock_performance_dir_name, file_name
            )
            if os.path.exists(dest_file_path):
                # Remove the existing file
                os.remove(dest_file_path)
            # Move the file to the stock performance dir
            os.rename(src_file_path, dest_file_path)


# Define the agents that will be involved in the workflow
# https://microsoft.github.io/autogen/docs/notebooks/agentchat_multi_task_async_chats#scenario-1-solve-the-tasks-with-a-series-of-chats
def run_workflow(workflow_tasks: WorkFlowTasks):
    # Create a chat with the strategy idea agent
    # The agent will provide stock investing ideas using technical indicators
    strategy_idea_json_path = os.path.join(
        os.path.dirname(__file__), WORK_DIR, STRATEGY_IDEAS
    )
    if not os.path.exists(strategy_idea_json_path):
        user_report_proxy.initiate_chat(
            recipient=strategy_idea_agent,
            message=workflow_tasks.stock_idea_task_description,
            summary_method="last_msg",
        )

    strategy_ideas = []
    with open(strategy_idea_json_path, "r") as file:
        strategy_ideas = json.load(file)

    # Create a chat with the stock performance agent and stock report agent.
    for strategy_idea in strategy_ideas:
        # Perform investment analysis and generate buy/sell signals
        # Perform backtesting and provide performance metrics
        # Create a chat with the stock report agent to generate a plot of stock prices and investment returns over time
        try:
            chat_res = user_report_proxy.initiate_chat(
                recipient=group_chat_manager,
                message=genereate_strategy_analysis_request_message(
                    workflow_tasks.investment_analysis_instructions, strategy_idea
                ),
                summary_method="reflection_with_llm",  # "last_msg" or "reflection_with_llm: not working"
                summary_args={"summary_prompt": SUMMARY_PROMPT},
            )
            print("Completed analysis for strategy: ", strategy_idea)
        except Exception as e:
            print(f"Error in chat for strategy: {strategy_idea}. {e}")
            continue

        # Workaround to handle the case when backtest_results.xlsx is not generated
        backtest_result_file_path = os.path.join(WORK_DIR, BACKTEST_RESULTS_FILE)
        if not os.path.exists(backtest_result_file_path):
            stock_price_file_path = os.path.join(WORK_DIR, DATASET_STOCK)
            stock_signals_file_path = os.path.join(WORK_DIR, DATASET_SIGNALS)
            # Execute the backtesting strategy manually calling the function again.
            backtest_stock_strategy(stock_price_file_path, stock_signals_file_path)

        if chat_res:
            if os.path.exists(backtest_result_file_path):
                user_report_proxy.initiate_chat(
                    recipient=stock_report_agent,
                    message=workflow_tasks.stock_report_task_instructions,
                    summary_method="last_msg",
                )

                # Get the chat messages for the custom signal analysis agent.
                # Sometimes the chat summary is empty, so we need to get the last message from the custom_signal_analysis_agent.
                custom_signal_agent = agents_registry.get(AgentName.CUSTOM_SIGNAL_ANALYSIS_AGENT)
                custom_signal_agent_messages = custom_signal_agent.chat_messages[group_chat_manager]
                # Get the chat messages for the stock report agent
                stock_report_agent_messages = user_report_proxy.chat_messages[stock_report_agent]

                last_message = stock_report_agent_messages[-1]
                print("Last message: ", last_message)

                # check error contains in the last message
                if last_message and "content" in last_message:
                    if not "ERROR" in last_message.get("content"):
                        save_stock_performance_data(
                            strategy_idea, chat_res, custom_signal_agent_messages, verbose_output=True
                        )
                        print(
                            "Saved stock performance data for strategy: ", strategy_idea
                        )
            else:
                print(
                    "Error: the stock performance data was not created for strategy: ",
                    strategy_idea,
                )
        else:
            print("No chat response for strategy: ", strategy_idea)
            continue


def remove_existing_files():
    # remove the existing files,stock_data.csv and strategy_idea.json , in the WORK_DIR
    for file_name in [DATASET_STOCK, STRATEGY_IDEAS]:
        file_path = os.path.join(WORK_DIR, file_name)
        if os.path.exists(file_path):
            os.remove(file_path)


if __name__ == "__main__":
    flag_for_delete_existing_files = False
    if flag_for_delete_existing_files:
        remove_existing_files()

    today = datetime.today().strftime("%Y-%m-%d")
    default_message_to_save_code = ""  # "Save the code to disk."
    user_message = dedent(
        f"""
        {default_message_to_save_code}

        Run complete stock analysis for MSFT from 1995-01-01 to {today}. 
        Generate buy/sell signals using {{indicator_str}}.
        Based on the generated signals, backtest the strategy and provide performance metrics.
        """
    )

    workflow_tasks = WorkFlowTasks(
        stock_idea_task_description="create a strategy 50 ideas for stock investing using provided technical indicators. ",
        investment_analysis_instructions=user_message,
        stock_report_task_instructions="create a plot to display stock investment returns over time",
    )

    logging_session_id = autogen.runtime_logging.start()
    print("Logging session ID: " + str(logging_session_id))
    run_workflow(workflow_tasks)
    autogen.runtime_logging.stop()
