from textwrap import dedent
from typing import Dict
from autogen import ConversableAgent, AssistantAgent
from utils.const import STRATEGY_IDEAS, WORK_DIR, AgentName
from utils.llm_tool_use import JsonToolRegistry


class StrategyIdeaAgent(ConversableAgent):
    def __init__(self, llm_config: Dict):
        self.__llm_config = llm_config
        self.__strategy_idea_agent_prompt = self._strategy_idea_agent_prompt()

    @staticmethod
    def _strategy_idea_agent_prompt() -> str:
        return dedent(
            f"""
            ## Role:
            You are responsible for creating a strategy idea for stock investing.
            
            ## Tasks:
            1. Create a strategy idea using technical indicators for stock investing that includes the following:
                - A brief description of the strategy.
                - The rationale behind the strategy.
                - The expected outcome or goal of the strategy.
            2. Provide a high-level overview of the strategy idea and its detailed conditions of investing.
            3. Store the output named "{STRATEGY_IDEAS}" in "{WORK_DIR}" with the Desired Output format.
            4. Do not include any messages or descriptions in the output, except for the JSON data.
            5. If generated JSON data is not valid, recreate the JSON file.

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


            ## Desired Output:
            [
                {{
                    "strategy": "Moving Average Crossover",
                    "description": "Utilize short-term and long-term moving averages to identify buy and sell signals.",
                    "rationale": "When a short-term moving average crosses above a long-term moving average, it signals a potential upward trend (bullish). Conversely, a cross below indicates a potential downward trend (bearish).",
                    "investing_conditions": "Buy when the short-term average crosses above the long-term average; sell when it crosses below.",
                    "expected_outcome": "Capture trends early and maximize returns during upward movements while limiting losses during downturns."
                }},
                {{
                    "strategy": "RSI Reversal",
                    "description": "Use the RSI to identify overbought and oversold conditions for potential reversals.",
                    "rationale": "An RSI above 70 indicates overbought conditions, while below 30 indicates oversold conditions, suggesting potential reversals.",
                    "investing_conditions": "Buy when RSI is below 30; sell when RSI is above 70.",
                    "expected_outcome": "Enter positions at favorable prices, benefiting from market corrections."
                }}
            ]
            """
        )

    # https://microsoft.github.io/autogen/docs/notebooks/agentchat_nested_sequential_chats/#step-2-orchestrate-nested-chats-to-solve-tasks
    def create_agent(self) -> ConversableAgent:
        return AssistantAgent(
            name="strategy_idea_agent",
            system_message=self.__strategy_idea_agent_prompt,
            llm_config=self.__llm_config,
        )

    def register_tools(self, user_proxy: ConversableAgent, stock_analysis_agent: ConversableAgent):
        tool_registry = JsonToolRegistry(user_proxy, stock_analysis_agent)
        tool_registry.register_tools()