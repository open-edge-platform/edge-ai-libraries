from pydantic_settings import BaseSettings
from os.path import dirname, abspath
from .prompt import get_prompt_template
import os
import yaml

class Settings(BaseSettings):
    """
    Settings for the Chatqna-Core application.
    This class manages configuration settings for the application, supporting loading from a YAML file,
    environment variables, or default values. It includes model identifiers, device settings, cache paths,
    and other application-specific options.

    Attributes:
        APP_DISPLAY_NAME (str): The display name of the application.
        BASE_DIR (str): The base directory of the application.
        SUPPORTED_FORMATS (set): Supported file formats for input documents.
        DEBUG (bool): Flag to enable or disable debug mode.
        HF_ACCESS_TOKEN (str): Hugging Face access token for model downloads.
        EMBEDDING_MODEL_ID (str): Identifier for the embedding model.
        RERANKER_MODEL_ID (str): Identifier for the reranker model.
        LLM_MODEL_ID (str): Identifier for the large language model.
        PROMPT_TEMPLATE (str): Template for prompts used by the LLM.
        EMBEDDING_DEVICE (str): Device to run the embedding model on (e.g., "CPU", "GPU").
        RERANKER_DEVICE (str): Device to run the reranker model on.
        LLM_DEVICE (str): Device to run the LLM on.
        CACHE_DIR (str): Directory for caching models.
        HF_DATASETS_CACHE (str): Directory for caching Hugging Face datasets.
        MAX_TOKENS (int): Maximum number of tokens for LLM input/output.
        ENABLE_RERANK (bool): Flag to enable or disable reranking.
        TMP_FILE_PATH (str): Temporary file path for storing documents.
        MODEL_CONFIG_PATH (str): Path to the YAML configuration file.

    Methods:
        __init__(**kwargs):
            Initializes the Settings instance, loading configuration from a YAML file if it exists,
            and overriding attributes with values from the file. If PROMPT_TEMPLATE is not set,
            it is determined based on the LLM_MODEL_ID.
    """

    APP_DISPLAY_NAME: str = "Chatqna-Core"
    BASE_DIR: str = dirname(dirname(abspath(__file__)))
    SUPPORTED_FORMATS: set = {".pdf", ".txt", ".docx"}
    DEBUG: bool = False

    HF_ACCESS_TOKEN: str = ""
    EMBEDDING_MODEL_ID: str = ""
    RERANKER_MODEL_ID: str = ""
    LLM_MODEL_ID: str = ""
    PROMPT_TEMPLATE: str = ""
    EMBEDDING_DEVICE: str = "CPU"
    RERANKER_DEVICE: str = "CPU"
    LLM_DEVICE: str = "CPU"
    CACHE_DIR: str = "/tmp/model_cache"
    HF_DATASETS_CACHE: str = "/tmp/model_cache"
    MAX_TOKENS: int = 1024
    ENABLE_RERANK: bool = True
    TMP_FILE_PATH: str = "/tmp/chatqna/documents"
    MODEL_CONFIG_PATH: str = "/tmp/model_config/config.yaml"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        config_file = self.MODEL_CONFIG_PATH

        if os.path.isfile(config_file):
            print(f"INFO - {config_file} exists. Loading configuration from {config_file}")
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)

            for key, value in config.get("model_settings", {}).items():
                if hasattr(self, key):
                    setattr(self, key, value)

            for key, value in config.get("device_settings", {}).items():
                if hasattr(self, key):
                    setattr(self, key, value)

        else:
            print(f"WARNING - Expected a file at {config_file}, but found a directory or nothing.")
            print("INFO - Proceeding with default settings or previously loaded configurations from env variables.")

        if not self.PROMPT_TEMPLATE:
            print("INFO - PROMPT_TEMPLATE is not set. Get prompt template based on LLM_MODEL_ID.")
            self.PROMPT_TEMPLATE = get_prompt_template(self.LLM_MODEL_ID)


config = Settings()