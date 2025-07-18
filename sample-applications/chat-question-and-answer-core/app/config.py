from pydantic import PrivateAttr
from pydantic_settings import BaseSettings
from os.path import dirname, abspath
from .prompt import get_prompt_template
import os
import yaml

class Settings(BaseSettings):
    """
    Settings class for configuring the Chatqna-Core application.
    This class manages application-wide configuration, including model settings, device preferences,
    supported file formats, and paths for caching and configuration files. It loads additional
    configuration from a YAML file if provided, and updates its attributes accordingly.

    Attributes:
        APP_DISPLAY_NAME (str): Display name of the application.
        BASE_DIR (str): Base directory of the application.
        SUPPORTED_FORMATS (set): Supported document file formats.
        DEBUG (bool): Flag to enable or disable debug mode.
        HF_ACCESS_TOKEN (str): Hugging Face access token for model downloads.
        EMBEDDING_MODEL_ID (str): Model ID for embeddings.
        RERANKER_MODEL_ID (str): Model ID for reranker.
        LLM_MODEL_ID (str): Model ID for large language model.
        PROMPT_TEMPLATE (str): Prompt template for the LLM.
        EMBEDDING_DEVICE (str): Device to run embedding model on.
        RERANKER_DEVICE (str): Device to run reranker model on.
        LLM_DEVICE (str): Device to run LLM on.
        MAX_TOKENS (int): Maximum number of tokens for LLM responses.
        ENABLE_RERANK (bool): Flag to enable or disable reranking.
        _CACHE_DIR (str): Directory for model cache (private).
        _HF_DATASETS_CACHE (str): Directory for Hugging Face datasets cache (private).
        _TMP_FILE_PATH (str): Temporary file path for documents (private).
        _DEFAULT_MODEL_CONFIG (str): Path to default model configuration YAML (private).
        _MODEL_CONFIG_PATH (str): Path to user-provided model configuration YAML (private).

    Methods:
        __init__(**kwargs): Initializes the Settings object, loads configuration from YAML file,
            and updates attributes accordingly.
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
    MAX_TOKENS: int = 1024
    ENABLE_RERANK: bool = True

    # These fields will not be affected by environment variables
    _CACHE_DIR: str = PrivateAttr("/tmp/model_cache")
    _HF_DATASETS_CACHE: str = PrivateAttr("/tmp/model_cache")
    _TMP_FILE_PATH: str = PrivateAttr("/tmp/chatqna/documents")
    _DEFAULT_MODEL_CONFIG: str = PrivateAttr("/tmp/model_config/default_model.yaml")
    _MODEL_CONFIG_PATH: str = PrivateAttr("/tmp/model_config/config.yaml")


    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # The RUN_TEST flag is used to bypass the model config loading during pytest unit testing.
        # If RUN_TEST is set to "True", the model config loading is skipped.
        # This flag is set in the conftest.py file before running the tests.
        if os.getenv("RUN_TEST", "").lower() == "true":
            print("INFO - Skipping model config loading in test mode.")
            return

        config_file = self._MODEL_CONFIG_PATH if os.path.isfile(self._MODEL_CONFIG_PATH) else self._DEFAULT_MODEL_CONFIG

        if config_file == self._MODEL_CONFIG_PATH:
            print(f"INFO - Model configuration yaml from user found in {config_file}. Loading configuration from {config_file}")

        else:
            print("WARNING - User did not provide model configuration yaml file via MODEL_CONFIG_PATH.")
            print(f"INFO - Proceeding with default settings from {config_file}")

        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)

        for section in ("model_settings", "device_settings"):
            for key, value in config.get(section, {}).items():
                if hasattr(self, key):
                    setattr(self, key, value)

        self._validate_model_ids()

        self._check_and_validate_prompt_template()

    def _validate_model_ids(self):
        for model_name in ["EMBEDDING_MODEL_ID", "RERANKER_MODEL_ID", "LLM_MODEL_ID"]:
            model_id = getattr(self, model_name)
            if not model_id:
                raise ValueError(f"{model_name} must not be an empty string.")

    def _check_and_validate_prompt_template(self):
        if not self.PROMPT_TEMPLATE:
            print("INFO - PROMPT_TEMPLATE is not set. Getting default prompt_template.")
            self.PROMPT_TEMPLATE = get_prompt_template(self.LLM_MODEL_ID)

        # Validate PROMPT_TEMPLATE
        required_placeholders = ["{context}", "{question}"]
        for placeholder in required_placeholders:
            if placeholder not in self.PROMPT_TEMPLATE:
                raise ValueError(f"PROMPT_TEMPLATE must include the placeholder {placeholder}.")


config = Settings()