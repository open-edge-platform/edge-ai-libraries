# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Application configuration settings loaded from environment/.env via Pydantic."""

from importlib.metadata import PackageNotFoundError, version as _pkg_version
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_app_version(fallback: str = "0.0.0") -> str:
    """Read the version declared in pyproject.toml via installed package metadata."""
    for dist in ("multimodal-dataprep", "multimodal_dataprep"):
        try:
            return _pkg_version(dist)
        except PackageNotFoundError:
            continue
    return fallback


class Settings(BaseSettings):
    """Configuration settings for the application
    Inherits from BaseSettings class from Pydantic
    """

    # All environment variables for this microservice are namespaced with the
    # MM_DATAPREP_ prefix, e.g. field DETECTION_DEVICE is read from
    # MM_DATAPREP_DETECTION_DEVICE and EMBEDDING_DEVICE from
    # MM_DATAPREP_EMBEDDING_DEVICE.
    model_config = SettingsConfigDict(env_prefix="MM_DATAPREP_")

    APP_NAME: str = "Multimodal-Dataprep"
    APP_DISPLAY_NAME: str = "Intel GenAI Multimodal DataPrep Microservice"
    APP_DESC: str = "A microservice for data preparation from text, video and image sources"
    APP_VERSION: str = Field(default_factory=lambda: _resolve_app_version("2.0.0"))
    APP_ROOT_PATH: str = "/v1/dataprep"

    @field_validator("APP_ROOT_PATH", mode="before")
    @classmethod
    def _normalize_root_path(cls, value):
        """Reject a root path that would silently produce unroutable URLs.

        The value is both the ASGI ``root_path`` and the ``servers`` entry in the
        OpenAPI document, so a malformed override must fail at startup rather
        than at request time.
        """
        if value in (None, ""):
            return "/"
        path = str(value).strip()
        if not path.startswith("/"):
            raise ValueError(f"APP_ROOT_PATH must start with '/', got: {path!r}")
        return path if path == "/" else path.rstrip("/")
    APP_PORT: int = 8000
    APP_HOST: str = ""

    FASTAPI_ENV: str = "development"  # Environment for FastAPI (development or production)
    LOG_LEVEL: str | None = None  # Optional log level override

    ALLOW_ORIGINS: str = "*"  # Comma separated values for allowed origins
    ALLOW_METHODS: str = "*"  # Comma separated values for allowed HTTP Methods
    ALLOW_HEADERS: str = "*"  # Comma separated values for allowed HTTP Headers

    DEFAULT_BUCKET_NAME: str = "video-summary"  # Reuse existing bucket from sample app
    DB_COLLECTION: str = "video-rag-test"

    # ------------------------------------------------------------------
    # Pluggable backend selection (vector DB + storage)
    # ------------------------------------------------------------------
    # Active vector database backend. Supported: "vdms", "milvus".
    # Default "vdms" preserves the historical behavior of this microservice.
    VECTORDB_BACKEND: str = Field(
        default="vdms",
        description="Active vector database backend: 'vdms' or 'milvus'",
    )
    # Active storage backend for media/artifacts. Supported: "minio", "local".
    STORAGE_BACKEND: str = Field(
        default="minio",
        description="Active storage backend: 'minio' or 'local'",
    )

    @field_validator("VECTORDB_BACKEND", "STORAGE_BACKEND", mode="before")
    @classmethod
    def _normalize_backend(cls, value):
        """Normalize backend selector strings to lower-case, trimmed values."""
        if value in (None, ""):
            return value
        return str(value).strip().lower()

    METADATA_FILENAME: str = "metadata.json"
    CONFIG_FILEPATH: Path = Path(__file__).resolve().parent.parent / "config.yaml"

    # When False, an upload whose byte content is identical to a previously
    # ingested video is rejected with 409 Conflict. When True (default), such
    # re-uploads are accepted (historical behavior). Read from env
    # MM_DATAPREP_ALLOW_DUPLICATE_UPLOADS.
    ALLOW_DUPLICATE_UPLOADS: bool = Field(
        default=True,
        description="Allow re-uploading a file whose content already exists. "
        "Set False to reject content-identical duplicate uploads with 409 Conflict.",
    )

    # Minio connection settings
    MINIO_ENDPOINT: str = ""  # Format: "host:port"
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MINIO_SECURE: bool = False  # Whether to use HTTPS

    # VDMS and embedding settings
    VDMS_VDB_HOST: str = ""
    VDMS_VDB_PORT: str = ""

    # Milvus settings (used when VECTORDB_BACKEND == "milvus")
    MILVUS_HOST: str = Field(default="", description="Milvus server host")
    MILVUS_PORT: str = Field(default="19530", description="Milvus server port")
    MILVUS_URI: str = Field(
        default="",
        description="Full Milvus URI (e.g. http://host:port). Overrides MILVUS_HOST/PORT when set.",
    )
    # Distance/similarity metric shared across backends. Inner-Product by default.
    VDB_METRIC_TYPE: str = Field(
        default="IP",
        description="Vector similarity metric (e.g. IP, L2). Applied to both VDMS and Milvus.",
    )
    VDB_INDEX_TYPE: str = Field(
        default="FLAT",
        description="Vector index type for backends that require it (e.g. Milvus FLAT).",
    )

    # Local filesystem storage settings (used when STORAGE_BACKEND == "local")
    LOCAL_STORAGE_PATH: str = Field(
        default="/tmp/dataprep/storage",
        description="Root directory for the local filesystem storage backend; "
        "each bucket maps to a subdirectory.",
    )

    # ------------------------------------------------------------------
    # Batch ingestion settings
    # ------------------------------------------------------------------
    # Root directory (mounted into the container) that directory-ingest requests
    # are resolved against. Requested paths are constrained to this root to
    # prevent path traversal. Parity with the EOL milvus-dataprep host-dir ingest.
    INGEST_DATA_ROOT: str = Field(
        default="/tmp/dataprep/ingest",
        description="Root directory for POST /media/ingest-dir; requested paths "
        "are constrained to this root (no traversal outside it).",
    )
    INGEST_DATA_ROOT_HOST: str = Field(
        default="",
        description="Host-side path bind-mounted at INGEST_DATA_ROOT. When set, "
        "the source_path metadata of directory-ingested media is recorded in "
        "host terms so consumers sharing the mount can locate the file. Empty "
        "records the container path as-is.",
    )
    BATCH_MAX_ITEMS: int = Field(
        default=100,
        ge=1,
        description="Maximum number of items (files/videos) accepted in a single batch job.",
    )
    BATCH_JOB_RETENTION: int = Field(
        default=200,
        ge=1,
        description="Maximum number of finished batch jobs retained in memory for status polling.",
    )

    EMBEDDING_MODEL_NAME: str = ""  # Model name - must be explicitly set

    # Embedding settings
    # Note: EMBEDDING_MODEL_NAME is used for model selection
    USE_OPENVINO: bool = True  # Whether to use OpenVINO optimization (default: True for better performance)
    MAX_PARALLEL_WORKERS: int | None = Field(
        default=None,
        description="Hard cap for parallel worker threads; auto-calculated when unset",
    )
    EMBEDDING_BATCH_SIZE: int = Field(
        default=32,
        ge=1,
        description="Items per embedding batch",
    )
    EMBEDDING_DEVICE: str = Field(
        default="CPU",
        description="Device for the in-process embedding pipeline (read from MM_DATAPREP_EMBEDDING_DEVICE)",
    )
    OV_PERFORMANCE_MODE: str = Field(
        default="THROUGHPUT",
        description="OpenVINO performance hint for the in-process embedding pipeline",
    )
    DETECTION_DEVICE: str | None = Field(
        default=None,
        description="Device for object detection; when unset, config/default value is used",
    )
    OV_MODELS_DIR: str = "/app/ov_models"  # Directory for OpenVINO models (used by the embedding pipeline)

    # Video pipeline settings
    VIDEO_SHM_MAX_BLOCKS: int = Field(
        default=512,
        ge=1,
        description="Shared memory pool block count for the video frame pipeline",
    )
    VIDEO_SHM_BLOCK_SIZE: int = Field(
        default=1920 * 1080 * 3,
        ge=1,
        description="Shared memory block size in bytes for the video frame pipeline",
    )
    VIDEO_CROP_SHM_ACQUIRE_TIMEOUT_S: float = Field(
        default=0.5,
        ge=0,
        description=(
            "Max seconds to wait for a free crop block before copying the crop to the "
            "heap. Short by design: the heap fallback is cheap, so waiting longer only "
            "stalls detection. 0 disables waiting entirely."
        ),
    )
    VIDEO_CROP_SHM_MAX_BLOCKS: int = Field(
        default=0,
        ge=0,
        description=(
            "Block count for the detected-crop pool. Crops are far smaller than full "
            "frames, so the pool is sized independently. 0 derives it from "
            "VIDEO_SHM_MAX_BLOCKS."
        ),
    )
    VIDEO_CROP_SHM_BLOCK_SIZE: int = Field(
        default=0,
        ge=0,
        description=(
            "Block size in bytes for the detected-crop pool. Crops larger than this "
            "fall back to heap allocation instead of being dropped. 0 derives it "
            "from VIDEO_SHM_BLOCK_SIZE."
        ),
    )
    VIDEO_EXTRACTION_BATCH_SIZE: int = Field(
        default=256,
        ge=1,
        description="Frame extraction batch size for video decoding",
    )
    PIPELINE_QUEUE_MAXSIZE: int = Field(
        default=16,
        ge=1,
        description="Max queue size for pipeline inter-stage queues",
    )
    PIPELINE_COMPLETION_QUEUE_MAXSIZE: int = Field(
        default=1,
        ge=1,
        description="Max queue size for pipeline completion queue",
    )
    DETECTION_WORKER_THREADS: int = Field(
        default=2,
        ge=1,
        description="Thread count for detection worker local pool",
    )
    EMBED_WORKER_THREADS: int = Field(
        default=2,
        ge=1,
        description="Thread count for embed worker local pool",
    )
    PIPELINE_QUEUE_GET_TIMEOUT_S: float = Field(
        default=1.0,
        gt=0,
        description="Queue get timeout in seconds for pipeline workers",
    )
    VIDEO_SHM_ACQUIRE_TIMEOUT_S: float = Field(
        default=30.0,
        gt=0,
        description=(
            "Max seconds to wait for a free shared memory block before giving up. "
            "Prevents the decode/detection stages from blocking forever when the pool is exhausted."
        ),
    )

    SAVE_RUNTIME_PIPELINE_STATS: bool = Field(
        default=False,
        description="Whether to save runtime pipeline statistics",
    )

    ENABLE_TRACING: bool = Field(
        default=False,
        description="Whether to enable detailed tracing in the processing pipeline",
    )

    VIDEO_FRAME_DECODER_WORKERS: int = Field(
        default=2,
        ge=1,
        description="Thread count for video frame decoder workers",
    )
    VIDEO_FRAME_LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level for video frame decoding components",
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
    METRICS_MANAGER_URL: str = Field(
        default="",
        description="Metrics Manager base URL. Empty disables live metric publishing.",
    )
    METRICS_MANAGER_TIMEOUT_SECONDS: float = Field(
        default=2.0,
        gt=0,
        description="Timeout for a single Metrics Manager publish attempt.",
    )

    # Allow environment override for bucket name (useful for different deployments)
    # If MM_DATAPREP_PM_MINIO_BUCKET is set (from sample app), use that; otherwise
    # fall back to the MM_DATAPREP_DEFAULT_BUCKET_NAME / DEFAULT_BUCKET_NAME setting.
    @property
    def effective_bucket_name(self) -> str:
        """Get the effective bucket name, checking environment variables first"""
        import os
        return os.getenv(
            "MM_DATAPREP_PM_MINIO_BUCKET",
            os.getenv("MM_DATAPREP_DEFAULT_BUCKET_NAME", self.DEFAULT_BUCKET_NAME),
        )

    @field_validator("MAX_PARALLEL_WORKERS", mode="before")
    @classmethod
    def normalize_max_parallel_workers(cls, value):
        """Treat unset/empty ``MAX_PARALLEL_WORKERS`` as ``None`` (auto)."""
        if value in (None, ""):
            return None
        return value

settings = Settings()
