from pydantic_settings import BaseSettings
from os.path import dirname, abspath
from .prompt import get_prompt_template
import os
import yaml

class Settings(BaseSettings):
    """
    Settings for the Chatqna-Core application.

    Attributes:
        APP_DISPLAY_NAME (str): The display name of the application.
        BASE_DIR (str): The base directory of the application.
        SUPPORTED_FORMATS (set): A set of supported file formats.
        DEBUG (bool): Flag to enable or disable debug mode.
        TMP_FILE_PATH (str): The temporary file path for documents.
        HF_ACCESS_TOKEN (str): The Hugging Face access token.
        EMBEDDING_MODEL_ID (str): The ID of the embedding model.
        RERANKER_MODEL_ID (str): The ID of the reranker model.
        LLM_MODEL_ID (str): The ID of the large language model.
        EMBEDDING_DEVICE (str): The device used for embedding.
        RERANKER_DEVICE (str): The device used for reranker.
        LLM_DEVICE (str): The device used for LLM inferencing.
        CACHE_DIR (str): The directory used for caching.
        HF_DATASETS_CACHE (str): The cache directory for Hugging Face datasets.
        MAX_TOKENS (int): The maximum number of output tokens.
        ENABLE_RERANK (bool): Flag to enable or disable reranking.
        MODEL_CONFIG_PATH (str): The path to the model configuration file.

    Init:
        Initializes the settings and loads configuration from a YAML file if it exists.
        Raises a FileNotFoundError if the expected configuration file is not found.
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

        else:
            print(f"WARNING - Expected a file at {config_file}, but found a directory or nothing.")
            print("INFO - Proceeding with default settings or previously loaded configurations from env variables.")

        if not self.PROMPT_TEMPLATE:
            print("INFO - PROMPT_TEMPLATE is not set. Get prompt template based on LLM_MODEL_ID.")
            self.PROMPT_TEMPLATE = get_prompt_template(self.LLM_MODEL_ID)


config = Settings()