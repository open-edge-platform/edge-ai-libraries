from pydantic import PrivateAttr
from pydantic_settings import BaseSettings
from typing import Union
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
        MODEL_BACKEND (str): Backend for model serving, e.g., "ollama" or "openvino".
        EMBEDDING_MODEL_ID (str): Model ID for embeddings.
        RERANKER_MODEL_ID (str): Model ID for reranker.
        LLM_MODEL_ID (str): Model ID for large language model.
        PROMPT_TEMPLATE (str): Prompt template for the LLM.
        EMBEDDING_DEVICE (str): Device to run embedding model on.
        RERANKER_DEVICE (str): Device to run reranker model on.
        LLM_DEVICE (str): Device to run LLM on.
        MAX_TOKENS (int): Maximum number of tokens for LLM responses.
        _ENABLE_RERANK (bool): Flag to enable or disable reranking.
        _SEARCH_METHOD (str): Search method for retriever (e.g., "mmr").
        _FETCH_K (int): Number of documents to fetch for retriever.
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
    MODEL_BACKEND: str = ""
    EMBEDDING_MODEL_ID: str = ""
    RERANKER_MODEL_ID: str = ""
    LLM_MODEL_ID: str = ""
    PROMPT_TEMPLATE: str = ""
    EMBEDDING_DEVICE: str = "CPU"
    RERANKER_DEVICE: str = "CPU"
    LLM_DEVICE: str = "CPU"
    MAX_TOKENS: int = 1024
    KEEP_ALIVE: Union[str, int, None] = None

    # These fields will not be affected by environment variables
    _ENABLE_RERANK: bool = PrivateAttr(True)
    _SEARCH_METHOD: str = PrivateAttr("mmr")
    _FETCH_K: int = PrivateAttr(10)
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

        self._validate_backend_settings()
        self._check_and_validate_prompt_template()


    def _validate_backend_settings(self):
        if self.MODEL_BACKEND:
            self.MODEL_BACKEND = self.MODEL_BACKEND.lower()
        else:
            raise ValueError("MODEL_BACKEND must not be an empty string.")

        if self.MODEL_BACKEND == "openvino":
            self._ENABLE_RERANK = True

            # Validate required model IDs
            for model_name in ["EMBEDDING_MODEL_ID", "RERANKER_MODEL_ID", "LLM_MODEL_ID"]:
                model_id = getattr(self, model_name)
                if not model_id:
                    raise ValueError(f"{model_name} must not be an empty string for 'openvino' backend.")

        elif self.MODEL_BACKEND == "ollama":
            self._ENABLE_RERANK = False

            # Validate that all devices are set to "CPU" as ollama currently only enabled for CPU
            invalid_devices = [
                attr for attr in ["EMBEDDING_DEVICE", "RERANKER_DEVICE", "LLM_DEVICE"]
                if getattr(self, attr, "") != "CPU"
            ]

            if invalid_devices:
                raise ValueError(
                    f"When MODEL_BACKEND is 'ollama', the following devices must be set to 'CPU': {', '.join(invalid_devices)}"
                )

            # Handle RERANKER_MODEL_ID
            if self.RERANKER_MODEL_ID:
                print("WARNING - RERANKER_MODEL_ID is ignored when MODEL_BACKEND is 'ollama'. Setting it to empty.")
                self.RERANKER_MODEL_ID = ""
            else:
                print("INFO - MODEL_BACKEND is 'ollama'. Reranker model is not supported.")

            # Validate required model IDs (excluding reranker)
            for model_name in ["EMBEDDING_MODEL_ID", "LLM_MODEL_ID"]:
                model_id = getattr(self, model_name)
                if not model_id:
                    raise ValueError(f"{model_name} must not be an empty string for 'ollama' backend.")

        else:
            raise ValueError(f"Unsupported MODEL_BACKEND '{self.MODEL_BACKEND}'. Only 'openvino' and 'ollama' are supported.")

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
