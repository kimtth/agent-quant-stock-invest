from textwrap import dedent
from utils.const import DATASET_STOCK, WORK_DIR, DATASET_SIGNALS
from agent.agent_dict import AgentDict, get_agents_from_dict
from autogen import GroupChat, GroupChatManager, ConversableAgent
from typing import Union, Literal, Dict
import os

class GroupChatManagerBase:
    def __init__(self, agents_dict: AgentDict, llm_config: Dict):
        self.__agents_dict = agents_dict
        self.__llm_config = llm_config
        self._group_chat = self.create_group_chat()
        self._group_chat_manager = self.create_group_chat_manager()

    @staticmethod
    def _custom_speaker_selection_func(
        last_speaker: ConversableAgent, groupchat: GroupChat
    ) -> Union[ConversableAgent, Literal["auto", "manual", "random", "round_robin"], None]:
        stock_data_path = os.path.join(WORK_DIR, DATASET_STOCK)
        stock_signals_path = os.path.join(WORK_DIR, DATASET_SIGNALS)
        messages = groupchat.messages

        if last_speaker.name == "custom_signal_analysis_agent" and not os.path.exists(stock_signals_path):
            return groupchat.agent_by_name("user_proxy")
        elif last_speaker.name == "user_proxy":
            if "exitcode: 1" in messages[-1]["content"]:
                return groupchat.agent_by_name("custom_signal_analysis_agent")
            elif not os.path.exists(stock_data_path):
                return groupchat.agent_by_name("stock_analysis_agent")
            else:
                return "auto"
        else:
            return "auto"
        
    @staticmethod
    def _speaker_select_msg_prompt() -> str:
        return dedent(
            f"""
            You are a manager responsible for coordinating a group chat between three agents: `stock_analysis_agent`, `custom_signal_analysis_agent`, and `user_proxy`.

            Your role is to oversee the stock analysis workflow, which consists of the following tasks:
            1. Creating stock data ("{DATASET_STOCK}") using the `stock_analysis_agent`.
            2. Generating buy/sell signals code by coordinating the `custom_signal_analysis_agent` 
            3. Ensuring the `user_proxy` executes the provided code.
            4. Analyzing stock investing performance using both the stock data and signals, with the `stock_analysis_agent` conducting backtests and providing performance metrics.

            Your job is to ensure smooth communication between agents, keep the workflow on track, and monitor task completion. 
            Coordinate the agents so that each step is completed in sequence and the group chat remains efficient.
            """
        )

    @staticmethod
    def _speaker_select_prompt() -> str:
        return dedent(
            """
            Read the above conversation.
            Select ONLY THE NAME of the next job role from agentlist to speak. Do not explain why.
            """
        )

    def create_group_chat(self) -> GroupChat:
        stock_analysis_agent, custom_signal_analysis_agent, user_proxy = get_agents_from_dict(self.__agents_dict)

        allowed_transitions = {
            custom_signal_analysis_agent: [user_proxy],
            user_proxy: [stock_analysis_agent, custom_signal_analysis_agent],
            stock_analysis_agent: [user_proxy, custom_signal_analysis_agent],
        }

        group_chat = GroupChat(
            agents=[stock_analysis_agent, custom_signal_analysis_agent, user_proxy],
            allowed_or_disallowed_speaker_transitions=allowed_transitions,
            speaker_transitions_type="allowed",
            messages=[],
            max_round=10,
            speaker_selection_method=self._custom_speaker_selection_func,
            select_speaker_message_template=self._speaker_select_msg_prompt(),
            select_speaker_prompt_template=self._speaker_select_prompt(),
            max_retries_for_selecting_speaker=5,
            select_speaker_auto_verbose=False,
        )

        return group_chat

    def create_group_chat_manager(self) -> GroupChatManager:
        group_chat_manager = GroupChatManager(
            groupchat=self._group_chat,
            llm_config=self.__llm_config,
            is_termination_msg=lambda x: x.get("content", "") is not None and "TERMINATE" in x.get("content", ""),
        )

        return group_chat_manager

