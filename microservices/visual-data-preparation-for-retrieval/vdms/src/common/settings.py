# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
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

    DEFAULT_BUCKET_NAME: str = "video-summary"  # Reuse existing bucket from sample app
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
    MULTIMODAL_EMBEDDING_MODEL_NAME: str = ""  # Model name for both SDK and API modes - must be explicitly set
    MULTIMODAL_EMBEDDING_ENDPOINT: str = ""  # 0 means auto-detect from API
    
    # Embedding processing mode: "api" or "sdk"
    # api: Use HTTP API calls to multimodal embedding service (current default)
    # sdk: Use multimodal embedding service directly as SDK (new optimized approach)
    EMBEDDING_PROCESSING_MODE: str = "sdk"
    
    # SDK-specific settings (only used when EMBEDDING_PROCESSING_MODE = "sdk")
    # Note: MULTIMODAL_EMBEDDING_MODEL_NAME is used for model selection in SDK mode
    SDK_USE_OPENVINO: bool = True  # Whether to use OpenVINO optimization in SDK mode (default: True for better performance)
    MAX_PARALLEL_WORKERS: int | None = Field(
        default=None,
        description="Hard cap for SDK parallel worker threads; auto-calculated when unset",
    )
    EMBEDDING_BATCH_SIZE: int = Field(
        default=32,
        ge=1,
        description="Items per embedding batch for SDK mode",
    )
    DEVICE: str = Field(
        default="CPU",
        validation_alias=AliasChoices("VDMS_DATAPREP_DEVICE"),
        description="Device for all processing components (embedding model, object detection)",
    )
    OV_MODELS_DIR: str = "/app/ov_models"  # Directory for OpenVINO models (used by both SDK and embedding service)

    # Frame-based processing settings
    FRAME_INTERVAL: int = 15
    ENABLE_OBJECT_DETECTION: bool = True
    DETECTION_CONFIDENCE: float = 0.85
    DETECTION_MODEL_DIR: str = "/app/models/yolox"  # Directory for object detection models
    FRAMES_TEMP_DIR: str = "/tmp/dataprep"  # Must match Docker volume mount for shared access

    # Telemetry persistence settings
    TELEMETRY_FILE_PATH: Path = Path("/tmp/dataprep/telemetry/telemetry.jsonl")
    TELEMETRY_MAX_RECORDS: int = 100

    # Allow environment override for bucket name (useful for different deployments)
    # If PM_MINIO_BUCKET is set (from sample app), use that; otherwise use DEFAULT_BUCKET_NAME
    @property
    def effective_bucket_name(self) -> str:
        """Get the effective bucket name, checking environment variables first"""
        import os
        return os.getenv("PM_MINIO_BUCKET", os.getenv("DEFAULT_BUCKET_NAME", self.DEFAULT_BUCKET_NAME))

    @field_validator("MAX_PARALLEL_WORKERS", mode="before")
    @classmethod
    def normalize_max_parallel_workers(cls, value):
        if value in (None, ""):
            return None
        return value

settings = Settings()
