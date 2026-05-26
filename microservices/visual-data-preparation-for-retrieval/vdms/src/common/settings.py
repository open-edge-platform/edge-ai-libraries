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

    # SDK video pipeline settings
    SDK_VIDEO_SHM_MAX_BLOCKS: int = Field(
        default=512,
        ge=1,
        description="Shared memory pool block count for SDK video frame pipeline",
        env="SDK_VIDEO_SHM_MAX_BLOCKS",
    )
    SDK_VIDEO_SHM_BLOCK_SIZE: int = Field(
        default=1920 * 1080 * 3,
        ge=1,
        description="Shared memory block size in bytes for SDK video frame pipeline",
        env="SDK_VIDEO_SHM_BLOCK_SIZE",
    )
    SDK_VIDEO_EXTRACTION_BATCH_SIZE: int = Field(
        default=256,
        ge=1,
        description="Frame extraction batch size for SDK video decoding",
        env="SDK_VIDEO_EXTRACTION_BATCH_SIZE",
    )
    SDK_PIPELINE_QUEUE_MAXSIZE: int = Field(
        default=16,
        ge=1,
        description="Max queue size for SDK pipeline inter-stage queues",
        env="SDK_PIPELINE_QUEUE_MAXSIZE",
    )
    SDK_PIPELINE_COMPLETION_QUEUE_MAXSIZE: int = Field(
        default=1,
        ge=1,
        description="Max queue size for SDK pipeline completion queue",
        env="SDK_PIPELINE_COMPLETION_QUEUE_MAXSIZE",
    )
    SDK_DETECTION_WORKER_THREADS: int = Field(
        default=2,
        ge=1,
        description="Thread count for detection worker local pool",
        env="SDK_DETECTION_WORKER_THREADS",
    )
    SDK_EMBED_WORKER_THREADS: int = Field(
        default=2,
        ge=1,
        description="Thread count for embed worker local pool",
        env="SDK_EMBED_WORKER_THREADS",
    )
    SDK_PIPELINE_QUEUE_GET_TIMEOUT_S: float = Field(
        default=1.0,
        gt=0,
        description="Queue get timeout in seconds for SDK pipeline workers",
        env="SDK_PIPELINE_QUEUE_GET_TIMEOUT_S",
    )

    SAVE_RUNTIME_PIPELINE_STATS: bool = Field(
        default=False,
        description="Whether to save runtime pipeline statistics",
        env="SAVE_RUNTIME_PIPELINE_STATS",
    )

    SDK_ENABLE_TRACING: bool = Field(
        default=False,
        description="Whether to enable detailed tracing in SDK processing mode",
        env="SDK_ENABLE_TRACING",
    )

    VIDEO_FRAME_DECODER_WORKERS: int = Field(
        default=2,
        ge=1,
        description="Thread count for video frame decoder workers",
        env="VIDEO_FRAME_DECODER_WORKERS",
    )
    VIDEO_FRAME_LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level for video frame decoding components",
        env="VIDEO_FRAME_LOG_LEVEL",
    )

    # Frame-based processing settings
    FRAME_INTERVAL: int = 15
    ENABLE_OBJECT_DETECTION: bool = True
    DETECTION_CONFIDENCE: float = 0.85
    DETECTION_MODEL_DIR: str = "/app/models/yolox"  # Directory for object detection models
    FRAMES_TEMP_DIR: str = "/tmp/dataprep"  # Must match Docker volume mount for shared access
    ROI_CONSOLIDATION_ENABLED: bool | None = None
    ROI_CONSOLIDATION_IOU_THRESHOLD: float | None = None
    ROI_CONSOLIDATION_CLASS_AWARE: bool | None = None
    ROI_CONSOLIDATION_CONTEXT_SCALE: float | None = None

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
