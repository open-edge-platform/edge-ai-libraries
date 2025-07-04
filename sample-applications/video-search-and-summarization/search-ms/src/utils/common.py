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
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    APP_NAME: str = "Video-Search"
    APP_DISPLAY_NAME: str = "Video Search Microservice"
    APP_DESC: str = (
        "The Video Search Microservice is designed to handle video search queries and return relevant results."
    )
    VDMS_VDB_HOST: str = Field(default="vdms-vector-db", validation_alias="VDMS_VDB_HOST")
    VDMS_VDB_PORT: int = Field(default=55555, validation_alias="VDMS_VDB_PORT")
    VCLIP_EMBEDDINGS_ENDPOINT: str = Field(default="", validation_alias="VCLIP_EMBEDDINGS_ENDPOINT")
    VCLIP_EMBEDDINGS_MODEL_NAME: str = Field(
        default="", validation_alias="VCLIP_EMBEDDINGS_MODEL_NAME"
    )
    VCLIP_EMBEDDINGS_NUM_FRAMES: int = Field(
        default=16, validation_alias="VCLIP_EMBEDDINGS_NUM_FRAMES"
    )
    SEARCH_ENGINE: str = Field(default="FaissFlat", validation_alias="SEARCH_ENGINE")
    DISTANCE_STRATEGY: str = Field(default="IP", validation_alias="DISTANCE_STRATEGY")
    INDEX_NAME: str = Field(default="videoqna", validation_alias="INDEX_NAME")
    no_proxy_env: str = Field(default="", validation_alias="no_proxy_env")
    http_proxy: str = Field(default="", validation_alias="http_proxy")
    https_proxy: str = Field(default="", validation_alias="https_proxy")
    WATCH_DIRECTORY: str = Field(default="", validation_alias="WATCH_DIRECTORY")
    WATCH_DIRECTORY_CONTAINER_PATH: str = Field(
        default="/tmp/watcher-dir", validation_alias="WATCH_DIRECTORY_CONTAINER_PATH"
    )
    DEBOUNCE_TIME: int = Field(default=5, validation_alias="DEBOUNCE_TIME")
    DATAPREP_UPLOAD_URL: str = Field(default="", validation_alias="DATAPREP_UPLOAD_URL")
    VS_INITIAL_DUMP: bool = Field(default=False, validation_alias="VS_INITIAL_DUMP")
    DELETE_PROCESSED_FILES: bool = Field(default=False, validation_alias="DELETE_PROCESSED_FILES")
    MINIO_API_PORT: str = Field(default="", validation_alias="MINIO_API_PORT")
    MINIO_HOST: str = Field(default="", validation_alias="MINIO_HOST")
    MINIO_ROOT_USER: str = Field(default="", validation_alias="MINIO_ROOT_USER")
    MINIO_ROOT_PASSWORD: str = Field(default="", validation_alias="MINIO_ROOT_PASSWORD")
    VDMS_BUCKET: str = Field(default="", validation_alias="VDMS_BUCKET")
    CHUNK_DURATION: int = Field(default=10, validation_alias="CHUNK_DURATION")


settings = Settings()
logger.debug(f"Settings: {settings.model_dump()}")


class ErrorMessages:
    """
    Error messages used throughout the application.
    """

    QUERY_VDMS_ERROR = "Error in querying VDMS"
    WATCHER_LAST_UPDATED_ERROR = "Error in getting watcher last updated timestamp"
