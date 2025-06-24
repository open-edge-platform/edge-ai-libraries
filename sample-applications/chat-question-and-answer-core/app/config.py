from pydantic_settings import BaseSettings
from os.path import dirname, abspath
from .prompt import default_rag_prompt_template
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
    EMBEDDING_DEVICE: str = "CPU"
    RERANKER_DEVICE: str = "CPU"
    LLM_DEVICE: str = "CPU"
    CACHE_DIR: str = "/tmp/model_cache"
    HF_DATASETS_CACHE: str = "/tmp/model_cache"
    MAX_TOKENS: int = 1024
    ENABLE_RERANK: bool = True
    TMP_FILE_PATH: str = "/tmp/chatqna/documents"
    PROMPT_TEMPLATE: str = default_rag_prompt_template
    MODEL_CONFIG_PATH: str = "/tmp/model_config/config.yaml"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        config_file = self.MODEL_CONFIG_PATH

        if os.path.isfile(config_file):
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)

            for key, value in config.get("model_settings", {}).items():
                if hasattr(self, key):
                    setattr(self, key, value)
        else:
            raise FileNotFoundError(f"Expected a file at {config_file}, but found a directory or nothing.")

config = Settings()