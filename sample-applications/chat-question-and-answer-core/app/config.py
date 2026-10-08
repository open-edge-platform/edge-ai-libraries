from pydantic import PrivateAttr
from pydantic_settings import BaseSettings
from typing import Union
from os.path import dirname, abspath
from .prompt import get_prompt_template
from .runtime_validators import OpenVINOValidator, OllamaValidator
import os
import yaml

class Settings(BaseSettings):
    """
    Settings class for configuring the Chatqna-Core application.
    This class manages application settings, including model backend runtime selection,
    model IDs, device configurations, prompt templates, and various internal paths.
    It loads configuration from a YAML file, validates backend-specific requirements,
    and ensures prompt templates contain required placeholders.

    Attributes:
        APP_DISPLAY_NAME (str): Display name of the application.
        BASE_DIR (str): Base directory of the application.
        SUPPORTED_FORMATS (set): Supported file formats for input documents.
        DEBUG (bool): Debug mode flag.
        HF_ACCESS_TOKEN (str): Hugging Face access token.
        MODEL_RUNTIME (str): Backend runtime to use for models ('openvino' or 'ollama').
        EMBEDDING_MODEL_ID (str): Identifier for the embedding model.
        RERANKER_MODEL_ID (str): Identifier for the reranker model.
        LLM_MODEL_ID (str): Identifier for the large language model.
        PROMPT_TEMPLATE (str): Prompt template string for the LLM.
        EMBEDDING_DEVICE (str): Device for embedding model ('CPU', etc.).
        RERANKER_DEVICE (str): Device for reranker model ('CPU', etc.).
        LLM_DEVICE (str): Device for LLM ('CPU', etc.).
        MAX_TOKENS (int): Maximum number of tokens for LLM responses.
        KEEP_ALIVE (Union[str, int, None]): Keep-alive setting for the application.
        RETURN_SOURCES (bool): When True, context chunks are labelled [S1..Sn] in the prompt and
            `/chat` returns them as `sources` (JSON field or a final `event: sources` SSE frame).
        SOURCE_SNIPPET_CHARS (int): Maximum length of the snippet returned per source.
        LLM_NPU_MODEL_DIR (str): OpenVINO GenAI model directory for the LLM on NPU
            (default: <model cache>/<LLM_MODEL_ID>/npu).
        NPU_MAX_PROMPT_LEN (int): Prompt token limit of the LLM on NPU.
        NPU_EMBEDDING_BATCH (int): Static batch size of the embedding model on NPU.
        NPU_RERANKER_BATCH (int): Static batch size of the reranker on NPU.
        NPU_ENCODER_SEQ_LEN (int): Static sequence length of the embedding and reranker on NPU.

    Private Attributes:
        _ENABLE_RERANK (bool): Whether reranking is enabled.
        _SEARCH_METHOD (str): Search method used for retrieval.
        _FETCH_K (int): Number of documents to fetch during retrieval.
        _CACHE_DIR (str): Directory for model cache.
        _HF_DATASETS_CACHE (str): Directory for Hugging Face datasets cache.
        _TMP_FILE_PATH (str): Temporary file path for documents.
        _DEFAULT_MODEL_CONFIG (str): Path to the default model configuration YAML.
        _MODEL_CONFIG_PATH (str): Path to the user-provided model configuration YAML.

    Methods:
        __init__(**kwargs): Initializes settings, loads configuration from YAML, and validates settings.
        _validate_backend_settings(): Validates backend-specific settings and required model IDs.
        _check_and_validate_prompt_template(): Ensures the prompt template is set and contains required placeholders.

    Raises:
        ValueError: If required settings are missing or invalid, or if unsupported backend is specified.
    """

    APP_DISPLAY_NAME: str = "Chatqna-Core"
    BASE_DIR: str = dirname(dirname(abspath(__file__)))
    SUPPORTED_FORMATS: set = {".pdf", ".txt", ".docx"}
    DEBUG: bool = False

    HF_ACCESS_TOKEN: str = ""
    MODEL_RUNTIME: str = ""
    EMBEDDING_MODEL_ID: str = ""
    RERANKER_MODEL_ID: str = ""
    LLM_MODEL_ID: str = ""
    PROMPT_TEMPLATE: str = ""
    EMBEDDING_DEVICE: str = "CPU"
    RERANKER_DEVICE: str = "CPU"
    LLM_DEVICE: str = "CPU"
    MAX_TOKENS: int = 1024
    KEEP_ALIVE: Union[str, int, None] = None
    # Opt-in: label context chunks [S1..Sn] in the prompt and return them as `sources`.
    RETURN_SOURCES: bool = False
    SOURCE_SNIPPET_CHARS: int = 300
    # Chunks fetched from FAISS and kept after reranking (stock: 3 and 2).
    RETRIEVAL_K: int = 3
    RERANK_TOP_N: int = 2
    # Optional LLM prompt with `{question}` that rewrites the question for retrieval.
    RETRIEVAL_TRANSLATE_PROMPT: str = ""
    # LLM on NPU runs through OpenVINO GenAI from an int4 channel-wise export
    # (default: <model cache>/<LLM_MODEL_ID>/npu), compiled for at most NPU_MAX_PROMPT_LEN
    # prompt tokens. Embedding and reranker on NPU are compiled with the static shapes
    # [NPU_EMBEDDING_BATCH, NPU_ENCODER_SEQ_LEN] and [NPU_RERANKER_BATCH, NPU_ENCODER_SEQ_LEN].
    # Embedding batch 4 matches the LangChain encode batch; granite-embedding-125m faults on
    # the NPU (MMU translation fault) at batch 1 and 2 under sustained ingestion.
    LLM_NPU_MODEL_DIR: str = ""
    NPU_MAX_PROMPT_LEN: int = 4096
    NPU_EMBEDDING_BATCH: int = 4
    NPU_RERANKER_BATCH: int = 2
    NPU_ENCODER_SEQ_LEN: int = 512

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

        self._validate_runtime_settings()
        self._check_and_validate_prompt_template()

    def _validate_runtime_settings(self):
        validators = {
            "openvino": OpenVINOValidator,
            "ollama": OllamaValidator,
        }

        runtime = self.MODEL_RUNTIME.lower()
        validator_cls = validators.get(runtime)

        if not validator_cls:
            raise ValueError(f"Unsupported model runtime: {self.MODEL_RUNTIME}. Supported runtimes are: {', '.join(validators.keys())}")

        validator = validator_cls(self)
        validator.validate()

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
