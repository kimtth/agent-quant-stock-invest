import os
import autogen
from autogen import ConversableAgent, GroupChatManager, GroupChat, ChatResult
from datetime import datetime
from textwrap import dedent
from typing import Dict, Tuple
from dotenv import load_dotenv
from utils.llm_config import load_config
from utils.const import SUMMARY_PROMPT, WORK_DIR, AgentName
from utils.llm_tool_use import ToolRegistry
from agent.signal_analysis_agent import SignalAnalysisAgent
from agent.stock_analysis_agent import StockAnalysisAgent
from agent.user_proxy_agent import UserProxyAgent
from agent.group_chat_manager import GroupChatManagerBase
from agent.agent_registry import AgentRegistry


def setup_agents(llm_config: Dict) -> Tuple:
    sa = StockAnalysisAgent(llm_config=llm_config)
    stock_analysis_agent = sa.create_agent()
    ca = SignalAnalysisAgent(llm_config=llm_config)
    custom_signal_analysis_agent = ca.create_agent()
    up = UserProxyAgent()
    user_proxy = up.create_user_proxy()

    agents_registry_base = AgentRegistry()
    agents_registry = agents_registry_base.create_agent_registry(
        stock_analysis_agent=stock_analysis_agent,
        custom_signal_analysis_agent=custom_signal_analysis_agent,
        user_proxy=user_proxy,
    )

    gcm = GroupChatManagerBase(agents_registry=agents_registry, llm_config=llm_config)
    group_chat = gcm.create_group_chat()
    group_chat_manager = gcm.create_group_chat_manager()

    return (
        agents_registry,
        group_chat,
        group_chat_manager,
    )


def register_tools(agents_registry: Dict[AgentName, ConversableAgent]):
    tool_registry = ToolRegistry(agents_registry)
    tool_registry.register_tools()


def initiate_stock_analysis(
    user_proxy: ConversableAgent,
    group_chat_manager: GroupChatManager,
    indicator_str: str = "Buy and Hold",
) -> ChatResult:
    today = datetime.today().strftime("%Y-%m-%d")
    user_message = dedent(
        f"""
        save the code to disk.

        Run complete stock analysis for MSFT from 1995-01-01 to {today}. 
        Generate buy/sell signals using {indicator_str}.
        Based on the generated signals, backtest the strategy and provide performance metrics.
        """
    )

    try:
        chat_res = user_proxy.initiate_chat(
            recipient=group_chat_manager,
            message=user_message,
            summary_method="reflection_with_llm",  # "last_msg" or "reflection_with_llm"
            summary_args={"summary_prompt": SUMMARY_PROMPT},
        )
        return chat_res
    except Exception as e:
        print(e)
        return None


def print_logging_info(group_chat: GroupChat, chat_res: ChatResult):
    if chat_res:
        with open(os.path.join(WORK_DIR, "chat_summary.txt"), "w") as f:
            f.write(chat_res.summary)
            f.write("---------------------------------------\n")
            f.write(os.linesep.join(group_chat.messages))


def main():
    load_dotenv()
    config_file_path = os.path.join(os.path.dirname(__file__), "OAI_CONFIG_LIST.json")
    llm_config = load_config(config_file_path)

    (
        agents_registry,
        group_chat,
        group_chat_manager,
    ) = setup_agents(llm_config)
    register_tools(agents_registry)

    autogen.runtime_logging.start()

    if not os.path.exists(WORK_DIR):
        os.mkdir(WORK_DIR)

    # indicator_str = "20-day Moving Average, TRIX, UO" # Example 1
    indicator_str = "Buy and Hold"  # Example 2
    user_proxy = agents_registry[AgentName.USER_PROXY]
    chat_res = initiate_stock_analysis(user_proxy, group_chat_manager, indicator_str)
    print_logging_info(group_chat, chat_res)

    autogen.runtime_logging.stop()


if __name__ == "__main__":
    main()
