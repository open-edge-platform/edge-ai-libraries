# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from dotenv import load_dotenv

# Configure logger
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("video_search")

env_path = os.path.join(os.path.dirname(__file__), "../../", ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
    logger.info(f"Loaded environment variables from {env_path}")
else:
    logger.info(
        f".env file not found at {env_path}. Using environment variables from docker-compose."
    )


class Settings(BaseSettings):
    """
    Configuration settings for the application.

    Attributes:
        APP_NAME (str): Name of the application.
        APP_DISPLAY_NAME (str): Display name of the application.
        APP_DESC (str): Description of the application.

    """
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    APP_NAME: str = "Video-Search"
    APP_DISPLAY_NAME: str = "Video Search Microservice"
    APP_DESC: str = (
        "The Video Search Microservice is designed to handle video search queries and return relevant results."
    )
    VDMS_VDB_HOST: str = "vdms-vector-db"
    VDMS_VDB_PORT: int = 55555
    VCLIP_EMBEDDINGS_ENDPOINT: str = ""
    VCLIP_EMBEDDINGS_MODEL_NAME: str = ""
    VCLIP_EMBEDDINGS_NUM_FRAMES: int = 16
    SEARCH_ENGINE: str = "FaissFlat"
    DISTANCE_STRATEGY: str = "IP"
    INDEX_NAME: str = "videoqna"
    no_proxy_env: str = ""
    http_proxy: str = ""
    https_proxy: str = ""
    WATCH_DIRECTORY: str = ""
    WATCH_DIRECTORY_CONTAINER_PATH: str = "/tmp/watcher-dir"
    DEBOUNCE_TIME: int = 5
    DATAPREP_UPLOAD_URL: str = ""
    VS_INITIAL_DUMP: bool = False
    DELETE_PROCESSED_FILES: bool = False
    MINIO_API_PORT: str = ""
    MINIO_HOST: str = ""
    MINIO_ROOT_USER: str = ""
    MINIO_ROOT_PASSWORD: str = ""
    VDMS_BUCKET: str = ""
    CHUNK_DURATION: int = 10


settings = Settings()
logger.debug(f"Settings: {settings.model_dump()}")


class ErrorMessages:
    """
    Error messages used throughout the application.
    """

    QUERY_VDMS_ERROR = "Error in querying VDMS"
    WATCHER_LAST_UPDATED_ERROR = "Error in getting watcher last updated timestamp"
