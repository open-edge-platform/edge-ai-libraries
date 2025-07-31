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

    FASTAPI_ENV: str = "development"  # Environment for FastAPI (development or production)
    LOG_LEVEL: str | None = None  # Optional log level override

    ALLOW_ORIGINS: str = "*"  # Comma separated values for allowed origins
    ALLOW_METHODS: str = "*"  # Comma separated values for allowed HTTP Methods
    ALLOW_HEADERS: str = "*"  # Comma separated values for allowed HTTP Headers

    DEFAULT_BUCKET_NAME: str = "vdms-bucket-test"  # Default bucket if none specified
    DB_COLLECTION: str = "video-rag-test"

    METADATA_FILENAME: str = "metadata.json"
    CONFIG_FILEPATH: Path = Path(__file__).resolve().parent.parent / "config.yaml"

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
    EMBEDDING_LENGTH: int = 0


settings = Settings()
