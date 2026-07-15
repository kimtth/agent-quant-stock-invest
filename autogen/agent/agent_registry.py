from typing import Dict, List, Optional
from autogen import ConversableAgent
from utils.const import AgentName


class AgentRegistry:
    def __init__(self) -> None:
        self.agents: Dict[AgentName, ConversableAgent] = dict()

    def create_agent_registry(
        self,
        stock_analysis_agent: ConversableAgent,
        custom_signal_analysis_agent: ConversableAgent,
        user_proxy: ConversableAgent,
        strategy_idea_agent: Optional[ConversableAgent] = None,
        stock_report_agent: Optional[ConversableAgent] = None,
    ) -> Dict[AgentName, ConversableAgent]:
        agents = {
            AgentName.STOCK_ANALYSIS_AGENT: stock_analysis_agent,
            AgentName.CUSTOM_SIGNAL_ANALYSIS_AGENT: custom_signal_analysis_agent,
            AgentName.USER_PROXY: user_proxy,
        }

        if strategy_idea_agent:
            agents[AgentName.STRATEGY_IDEA_AGENT] = strategy_idea_agent
        if stock_report_agent:
            agents[AgentName.STOCK_REPORT_AGENT] = stock_report_agent

        return agents
    
    def add_agent_to_registry(
        self, agent_name: AgentName, agent: ConversableAgent
    ) -> None:
        self.agents[agent_name] = agent

    def get_agent_registry(self) -> Dict[AgentName, ConversableAgent]:
        return self.agents

    def filter_agent_registry(
        self,
        agent_registry: Dict[AgentName, ConversableAgent],
        agent_names: Optional[List[AgentName]] = [],
    ) -> List[Optional[ConversableAgent]]:

        if len(agent_names) == 0:
            return agent_registry
        filtered_agent_registry = {
            k: v for k, v in agent_registry.items() if k in agent_names
        }
        return filtered_agent_registry
