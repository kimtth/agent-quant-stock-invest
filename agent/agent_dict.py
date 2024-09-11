from typing import Tuple
from autogen import ConversableAgent
from pydantic import BaseModel

class AgentDict(BaseModel):
    stock_analysis_agent: ConversableAgent
    custom_signal_analysis_agent: ConversableAgent
    user_proxy: ConversableAgent

    class Config:
        arbitrary_types_allowed = True


# Example usage of AgentDict
def create_agents_dict(stock_analysis_agent: ConversableAgent, custom_signal_analysis_agent: ConversableAgent, user_proxy: ConversableAgent) -> AgentDict:
    return AgentDict(
        stock_analysis_agent=stock_analysis_agent,
        custom_signal_analysis_agent=custom_signal_analysis_agent,
        user_proxy=user_proxy,
    )

def get_agents_from_dict(agents_dict: AgentDict) -> Tuple:
    return (
        agents_dict.stock_analysis_agent,
        agents_dict.custom_signal_analysis_agent,
        agents_dict.user_proxy,
    )


