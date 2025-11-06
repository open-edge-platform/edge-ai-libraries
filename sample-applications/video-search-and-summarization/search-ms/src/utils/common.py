# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import os
from pydantic_settings import BaseSettings
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

    APP_NAME: str = "Video-Search"
    APP_DISPLAY_NAME: str = "Video Search Microservice"
    APP_DESC: str = (
        "The Video Search Microservice is designed to handle video search queries and return relevant results."
    )
    VDMS_VDB_HOST: str = Field(default="vdms-vector-db", env="VDMS_VDB_HOST")
    VDMS_VDB_PORT: int = Field(default=55555, env="VDMS_VDB_PORT")
    EMBEDDINGS_ENDPOINT: str = Field(default="", env="EMBEDDINGS_ENDPOINT")
    EMBEDDINGS_MODEL_NAME: str = Field(
        default="", env="EMBEDDINGS_MODEL_NAME"
    )
    SEARCH_ENGINE: str = Field(default="FaissFlat", env="SEARCH_ENGINE")
    DISTANCE_STRATEGY: str = Field(default="IP", env="DISTANCE_STRATEGY")
    INDEX_NAME: str = Field(default="videoqna", env="INDEX_NAME")
    no_proxy_env: str = Field(default="", env="no_proxy_env")
    http_proxy: str = Field(default="", env="http_proxy")
    https_proxy: str = Field(default="", env="https_proxy")
    WATCH_DIRECTORY: str = Field(default="", env="WATCH_DIRECTORY")
    WATCH_DIRECTORY_CONTAINER_PATH: str = Field(
        default="/tmp/watcher-dir", env="WATCH_DIRECTORY_CONTAINER_PATH"
    )
    DEBOUNCE_TIME: int = Field(default=5, env="DEBOUNCE_TIME")
    VIDEO_UPLOAD_ENDPOINT: str = Field(default="", env="VIDEO_UPLOAD_ENDPOINT")
    VS_INITIAL_DUMP: bool = Field(default=False, env="VS_INITIAL_DUMP")
    DELETE_PROCESSED_FILES: bool = Field(default=False, env="DELETE_PROCESSED_FILES")
    WATCH_DIRECTORY_RECURSIVE: bool = Field(default=False, env="WATCH_DIRECTORY_RECURSIVE")
    EMBEDDING_LENGTH: int = 0

    # Frame-to-Video Aggregation Settings
    AGGREGATION_SEGMENT_DURATION: int = Field(default=8, env="AGGREGATION_SEGMENT_DURATION")
    AGGREGATION_MIN_GAP: int = Field(default=0, env="AGGREGATION_MIN_GAP")
    AGGREGATION_MAX_RESULTS: int = Field(default=20, env="AGGREGATION_MAX_RESULTS")
    AGGREGATION_INITIAL_K: int = Field(default=1000, env="AGGREGATION_INITIAL_K")
    AGGREGATION_ENABLED: bool = Field(default=True, env="AGGREGATION_ENABLED")
    AGGREGATION_CONTEXT_SEEK_OFFSET_SECONDS: float = Field(
        default=0.0, env="AGGREGATION_CONTEXT_SEEK_OFFSET_SECONDS"
    )
    AGGREGATION_QUAL_MAX_WEIGHT: float = Field(
        default=0.65, env="AGGREGATION_QUAL_MAX_WEIGHT"
    )
    AGGREGATION_QUAL_TOP_WEIGHT: float = Field(
        default=0.35, env="AGGREGATION_QUAL_TOP_WEIGHT"
    )
    AGGREGATION_QUAL_TOP_RATIO: float = Field(
        default=0.35, env="AGGREGATION_QUAL_TOP_RATIO"
    )
    AGGREGATION_QUAL_TOP_MIN_COUNT: int = Field(
        default=2, env="AGGREGATION_QUAL_TOP_MIN_COUNT"
    )
    AGGREGATION_QUAL_TOP_MAX_COUNT: int = Field(
        default=6, env="AGGREGATION_QUAL_TOP_MAX_COUNT"
    )
    AGGREGATION_CONTEXT_SIGMA_SECONDS: float = Field(
        default=40.0, env="AGGREGATION_CONTEXT_SIGMA_SECONDS"
    )
    AGGREGATION_CONTEXT_BOOST_STRENGTH: float = Field(
        default=0.5, env="AGGREGATION_CONTEXT_BOOST_STRENGTH"
    )


settings = Settings()
logger.debug(f"Settings: {settings.dict()}")


class ErrorMessages:
    """
    Error messages used throughout the application.
    """

    QUERY_VDMS_ERROR = "Error in querying VDMS"
    WATCHER_LAST_UPDATED_ERROR = "Error in getting watcher last updated timestamp"
