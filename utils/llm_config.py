import autogen
from typing import Dict
from .const import MODEL_NAMES 

def load_config(config_file_path: str) -> Dict:
    
    config_list = autogen.config_list_from_json(
        config_file_path,
        filter_dict={
            "model": MODEL_NAMES,
        },
    )

    assert len(config_list) > 0, "Config list is empty"
    print("models to use: ", [config["model"] for config in config_list])

    llm_config = {
        # https://microsoft.github.io/autogen/docs/Migration-Guide#migrating-to-02
        # https://microsoft.github.io/autogen/docs/FAQ/#handle-rate-limit-error-and-timeout-error
        # https://github.com/microsoft/autogen/issues/454
        "config_list": config_list,
        "cache_seed": 44,
        "temperature": 0.7,
        "timeout": 800,
        "max_retries": 8,
    }

    return llm_config


