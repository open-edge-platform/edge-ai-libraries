# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration settings for the application
    Inherits from BaseSettings class from Pydantic
    """

    APP_NAME: str = "VDMS-Dataprep"
    APP_DISPLAY_NAME: str = "Intel GenAI Multimodal DataPrep Microservice (VDMS Based)"
    APP_DESC: str = "A microservice for data preparation from text, video and image sources"
    APP_PORT: int = 8000
    APP_HOST: str = ""

    FASTAPI_ENV: str = ...
    LOG_LEVEL: str | None = None  # Optional log level override

    ALLOW_ORIGINS: str = "*"  # Comma separated values for allowed origins
    ALLOW_METHODS: str = "*"  # Comma separated values for allowed HTTP Methods
    ALLOW_HEADERS: str = "*"  # Comma separated values for allowed HTTP Headers

    DEFAULT_BUCKET_NAME: str = "vdms-bucket-test"  # Default bucket if none specified
    DB_COLLECTION: str = "video-rag-test"

    METADATA_FILENAME: str = "metadata.json"
    CONFIG_FILEPATH: Path = Path(__file__).resolve().parent / "config.yaml"

    # Minio connection settings
    MINIO_ENDPOINT: str = ""  # Format: "host:port"
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MINIO_SECURE: bool = False  # Whether to use HTTPS

    # VDMS and embedding settings
    VDMS_VDB_HOST: str = ""
    VDMS_VDB_PORT: str = ""
    MULTIMODAL_EMBEDDING_MODEL_NAME: str = "openai/clip-vit-base-patch32"
    MULTIMODAL_EMBEDDING_NUM_FRAMES: int = 64
    MULTIMODAL_EMBEDDING_ENDPOINT: str = ""


class Strings:
    server_error: str = "Some error ocurred at API server. Please try later!"
    format_error: str = "Only .mp4 file is supported."
    video_open_error: str = "Error: Could not open video file."
    datastore_error: str = "Some error ocurred at DataStore Service. Please try later!"
    minio_error: str = "Some error ocurred while accessing the Minio storage. Please try later!"
    minio_conn_error: str = "Error connecting to Minio object storage."
    minio_file_not_found: str = "Video file not found in Minio storage."
    video_id_not_found: str = "No video found for the specified video ID."
    embedding_success: str = "Embeddings for the video file(s) were created successfully."
    config_error: str = "Some error ocurred while reading the config file."
    metadata_read_error: str = "Error ocurred while reading metadata file."
    db_conn_error: str = "Error ocurred while initializing connection with VDMS vector DB."
    embedding_error: str = "Error occurred while trying to create video embeddings."


class DataPrepException(Exception):
    """Custom exception for VDMS-DataPrep application."""

    def __init__(self, msg: str, status_code: int):
        self.message = msg
        self.status_code = status_code
        super().__init__(self.message)


settings = Settings()
