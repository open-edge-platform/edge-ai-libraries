from pydantic_settings import BaseSettings
from os.path import dirname, abspath, join


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

    Config:
        env_file (str): The path to the environment file.
    """

    APP_DISPLAY_NAME: str = "Chatqna-Core"
    BASE_DIR: str = dirname(dirname(abspath(__file__)))
    SUPPORTED_FORMATS: set = {".pdf", ".txt", ".docx"}
    DEBUG: bool = False

    HF_ACCESS_TOKEN: str = ...
    EMBEDDING_MODEL_ID: str = ...
    RERANKER_MODEL_ID: str = ...
    LLM_MODEL_ID: str = ...
    EMBEDDING_DEVICE: str = ...
    RERANKER_DEVICE: str = ...
    LLM_DEVICE: str = ...
    CACHE_DIR: str = ...
    HF_DATASETS_CACHE: str = ...
    MAX_TOKENS: int = ...
    ENABLE_RERANK: bool = ...
    TMP_FILE_PATH: str = ...

    class Config:
        env_file = join(dirname(abspath(__file__)), ".env")
