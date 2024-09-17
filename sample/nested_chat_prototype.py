import os
import autogen
from textwrap import dedent

# how to access library in parent directory of the current file
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
# add parent of paret directory
sys.path.append(str(Path(__file__).resolve().parents[2]))

from utils.llm_config import load_config
 

config_file_path = os.path.join(
    "OAI_CONFIG_LIST.json"
)
_llm_config = load_config(config_file_path=config_file_path)

inner_strategy_idea_prompt = dedent(
    f"""
    ## Role:
    You are responsible for creating a strategy idea for stock investing.
    
    ## Tasks:
    1. Create a strategy idea using technical indicators for stock investing that includes the following:
        - A brief description of the strategy.
        - The rationale behind the strategy.
        - The expected outcome or goal of the strategy.
    2. Provide a high-level overview of the strategy idea and its detailed conditions of investing.
    3. Reply TERMINATE when the task is done.

    ## Technical Indicators:

    ### Volume

    - Accumulation/Distribution Index (ADI)
    - On-Balance Volume (OBV)
    - On-Balance Volume mean (OBV mean)
    - Chaikin Money Flow (CMF)
    - Force Index (FI)
    - Ease of Movement (EoM, EMV)
    - Volume-price Trend (VPT)
    - Negative Volume Index (NVI)

    ### Volatility

    - Average True Range (ATR)
    - Bollinger Bands (BB)
    - Keltner Channel (KC)
    - Donchian Channel (DC)

    ### Trend
    - Moving Average Convergence Divergence (MACD)
    - Average Directional Movement Index (ADX)
    - Vortex Indicator (VI)
    - Trix (TRIX)
    - Mass Index (MI)
    - Commodity Channel Index (CCI)
    - Detrended Price Oscillator (DPO)
    - KST Oscillator (KST)
    - Ichimoku Kinkō Hyō (Ichimoku)

    ### Momentum
    - Money Flow Index (MFI)
    - Relative Strength Index (RSI)
    - True strength index (TSI)
    - Ultimate Oscillator (UO)
    - Stochastic Oscillator (SR)
    - Williams %R (WR)
    - Awesome Oscillator (AO)

    ### Others
    - Daily Return (DR)
    - Cumulative Return (CR)
    """
)

inner_strategy_idea_agent = autogen.AssistantAgent(
    name="strategy_idea_agent",
    system_message=inner_strategy_idea_prompt,
    llm_config=_llm_config,
)

inner_strategy_idea_executor = autogen.UserProxyAgent(
    name="User",
    human_input_mode="NEVER",
    is_termination_msg=lambda x: x.get("content", "").find("TERMINATE") >= 0,
    code_execution_config={
        "last_n_messages": 1,
        "work_dir": "_inner_output",
        "use_docker": False,
    },  # Set to True if using Docker
)

@inner_strategy_idea_executor.register_for_execution()
@inner_strategy_idea_agent.register_for_llm(
    description="Find ideas for stock investing strategy by external resources."
)
def strategy_idea_executor(input_message: str):
    return {"content": input_message}


outer_reflection_message = dedent(
    """
    I have created a strategy idea for stock investing. 
    Here is a high-level overview of the strategy idea and its potential impact.
    Ensure it does not contain harmful content. 
    """
)

outer_writer_agent_message = dedent(
    """
    You are responsible for rewriting the result for the desired outputs.

    ## Strategy Idea for Stock Investing
    - **Description:** A brief description of the strategy.
    - **Rationale:** The rationale behind the strategy.
    - **Investing conditions:** The detailed conditions of investing.
    - **Expected Outcome:** The expected outcome or goal of the strategy.
    """
)

outer_delegate_result_proxy = autogen.UserProxyAgent(
    name="strategy_idea_proxy_agent",
    human_input_mode="NEVER",
    is_termination_msg=lambda x: x.get("content", "").find("TERMINATE") >= 0,
    code_execution_config={
        "last_n_messages": 1,
        "work_dir": "_inner_output",
        "use_docker": False,
    }
)

outer_writer_agent = autogen.AssistantAgent(
    name="strategy_idea_writer_agent",
    system_message=outer_writer_agent_message,
    llm_config=_llm_config,
)

outer_delegate_result_proxy.register_nested_chats(
    [
        {
            "sender": inner_strategy_idea_executor,
            "recipient": inner_strategy_idea_agent,
            "message": outer_reflection_message,
            "max_turns": 2,
            "summary_method": "last_msg",
        }
    ],
    trigger=outer_writer_agent,  # condition=my_condition,
)

task = dedent(
    """
    create a strategy 10 ideas for stock investing using technical indicators. 
    """
)

res = outer_delegate_result_proxy.initiate_chat(recipient=outer_writer_agent, message=task, max_turns=2, summary_method="last_msg")

# https://microsoft.github.io/autogen/docs/notebooks/agentchat_multi_task_async_chats#scenario-3-solve-the-tasks-with-a-series-of-chats-involving-group-chat
# https://microsoft.github.io/autogen/docs/notebooks/agentchat_nestedchat#scenarios-2
print(res.summary)