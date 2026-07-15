from textwrap import dedent
from autogen import ConversableAgent
from utils.const import DATASET_SIGNALS, WORK_DIR
from autogen.coding import LocalCommandLineCodeExecutor
import autogen


class BaseUserProxyAgent:
    def __init__(self):
        self.__user_proxy_prompt = self._user_proxy_prompt()

    def create_user_proxy(self) -> ConversableAgent:
        """Create the user proxy agent with common configurations."""
        return autogen.UserProxyAgent(
            name="user_proxy",
            is_termination_msg=lambda x: x.get("content", "") is not None
            and str(x.get("content", "")).rstrip().endswith("TERMINATE"),
            human_input_mode="NEVER",  # Literal['ALWAYS', 'TERMINATE', 'NEVER']
            max_consecutive_auto_reply=15,
            code_execution_config={
                "executor": LocalCommandLineCodeExecutor(
                    work_dir=WORK_DIR, timeout=600, execution_policies={"python": True}
                ),
            },
            system_message=self.__user_proxy_prompt,
        )

    @staticmethod
    def _user_proxy_prompt() -> str:
        """Each subclass should implement this method to provide a custom prompt."""
        raise NotImplementedError


class UserProxyReportAgent(BaseUserProxyAgent):
    @staticmethod
    def _user_proxy_prompt() -> str:
        return dedent(
            """
            You are responsible for executing Python code provided by other agents, or validating and storing JSON content.

            Tasks:

            If the provided code is not Python, do not execute it.
            If the provided content is JSON, check its validity and store the JSON in the 'WORK_DIR'.

            If you get TERMINATE included message from an agent, reply with TERMINATE.
            If the task is successful or the validity check is success, reply with TERMINATE.
            If further steps are required, reply with CONTINUE, or explain why the task has not yet been resolved.
            """
        )


class UserProxyAgent(BaseUserProxyAgent):
    @staticmethod
    def _user_proxy_prompt() -> str:
        return dedent(
            f"""
            You are responsible for executing the Python code provided by other agents and accessing the data in the 'WORK_DIR'.

            Tasks:
            1. Execute the Python code from `custom_signal_analysis_agent` to generate the "{DATASET_SIGNALS}" file.
            - The code will generate buy/sell signals and save them in the "{DATASET_SIGNALS}" file in the 'WORK_DIR'.
            - If the code execution fails, retry executing the code.

            If the task is successful, reply TERMINATE. 
            If more steps are required, reply CONTINUE, or explain why the task has not been solved yet.
            """
        )
