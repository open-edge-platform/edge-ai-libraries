# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pydantic request/response schemas and enums for the DataPrep REST API."""

from enum import Enum
from typing import Annotated, Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class StatusEnum(str, Enum):
    """Generic success/error status returned in API responses."""

    success = "success"
    error = "error"


class FrameExtractionModeEnum(str, Enum):
    """Frame extraction modes for video processing"""

    time_based = "time_based"  # Traditional time-based frame extraction
    object_detection = "object_detection"  # Object detection + time-based extraction
    hybrid = "hybrid"  # Both object detection crops and full frames


class ObjectDetectionConfig(BaseModel):
    """Configuration for object detection in frame extraction"""

    enabled: bool = Field(
        default=False, description="Enable object detection for frame extraction"
    )
    confidence_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Confidence threshold for object detection (0.0-1.0)",
    )
    max_detections_per_frame: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of object detections to extract per frame",
    )
    extraction_mode: FrameExtractionModeEnum = Field(
        default=FrameExtractionModeEnum.time_based,
        description="Frame extraction mode: time_based, object_detection, or hybrid",
    )
    crop_padding: int = Field(
        default=10,
        ge=0,
        le=100,
        description="Padding pixels around detected objects when creating crops",
    )


class DataPrepResponse(BaseModel):
    """Response model for API Responses from DataStore service"""

    status: StatusEnum = StatusEnum.success
    message: Optional[str] = None


class DataPrepErrorResponse(DataPrepResponse):
    """Response model for API Error Responses from DataStore service"""

    status: StatusEnum = StatusEnum.error


class HealthResponse(BaseModel):
    """Response model for service health checks."""

    status: str
    embedding_client_status: Optional[str] = None
    model_name: Optional[str] = None
    embedding_device: Optional[str] = None
    use_openvino: Optional[bool] = None
    embedding_client_error: Optional[str] = None
    detection_model: Optional[str] = None
    detection_device: Optional[str] = None


class VideoRequest(BaseModel):
    """Request model for video processing from Minio storage"""

    bucket_name: Annotated[
        Optional[str], Field(description="The bucket name where the video is stored")
    ] = None
    video_id: Annotated[
        Optional[str], Field(description="The video ID (directory) containing the video")
    ] = None
    video_name: Annotated[
        Optional[str],
        Field(
            description="Original media name to persist as searchable metadata. "
            "Falls back to the stored filename when omitted.",
        ),
    ] = None
    frame_interval: Annotated[
        Optional[int],
        Field(
            ge=1,
            le=60,
            description="Extract every Nth frame for processing (default: 15)",
            json_schema_extra={"example": 15},
        ),
    ] = None
    enable_object_detection: Annotated[
        Optional[bool],
        Field(
            description="Enable object detection and crop extraction (default: True)",
            json_schema_extra={"example": True},
        ),
    ] = None
    detection_confidence: Annotated[
        Optional[float],
        Field(
            ge=0.1,
            le=1.0,
            description="Confidence threshold for object detection (default: 0.85)",
            json_schema_extra={"example": 0.85},
        ),
    ] = None
    tags: Annotated[
        Optional[List[str]],
        Field(
            default_factory=list,
            description="List of tags to be associated with the video. Useful for filtering the search.",
        ),
    ]


class ImageSourceTypeEnum(str, Enum):
    """Discriminator for a JSON image source (mirrors MME's typed input)."""

    image_base64 = "image_base64"
    image_url = "image_url"


class ImageIngestItem(BaseModel):
    """A single typed image source for JSON ingestion.

    Exactly one payload field must be set, matching ``type``:
    ``image_base64`` (inline base64 / data URL) or ``image_url`` (remote http(s)
    URL). The stored filename/extension is derived from the sniffed bytes, so
    ``filename`` is an optional hint only.
    """

    type: Annotated[
        ImageSourceTypeEnum,
        Field(description="Source discriminator: 'image_base64' or 'image_url'."),
    ]
    image_base64: Annotated[
        Optional[str],
        Field(default=None, description="Base64-encoded image (bare or 'data:' URL) when type=image_base64."),
    ] = None
    image_url: Annotated[
        Optional[str],
        Field(default=None, description="Absolute http(s) image URL when type=image_url."),
    ] = None
    filename: Annotated[
        Optional[str],
        Field(default=None, description="Optional filename hint; extension is derived from the real bytes."),
    ] = None
    tags: Annotated[
        Optional[List[str]],
        Field(default=None, description="Optional per-image tags (merged with request-level tags)."),
    ] = None

    @model_validator(mode="after")
    def _check_payload(self) -> "ImageIngestItem":
        """Ensure the payload field matching ``type`` is present and non-empty."""
        if self.type == ImageSourceTypeEnum.image_base64 and not self.image_base64:
            raise ValueError("image_base64 is required when type='image_base64'.")
        if self.type == ImageSourceTypeEnum.image_url and not self.image_url:
            raise ValueError("image_url is required when type='image_url'.")
        return self


class ImageIngestRequest(ImageIngestItem):
    """Single-image JSON ingestion request (one typed source + storage params)."""

    bucket_name: Annotated[
        Optional[str],
        Field(default=None, description="Target bucket for the stored image (default bucket if unset)."),
    ] = None
    enable_object_detection: Annotated[
        Optional[bool],
        Field(default=None, description="Enable object detection and crop extraction (default: True)."),
    ] = None
    detection_confidence: Annotated[
        Optional[float],
        Field(default=None, ge=0.1, le=1.0, description="Object detection confidence threshold (default: 0.85)."),
    ] = None


class ImageBatchIngestRequest(BaseModel):
    """Batch JSON ingestion request: many typed image sources -> one async job."""

    images: Annotated[
        List[ImageIngestItem],
        Field(description="List of typed image sources (base64 or URL)."),
    ]
    bucket_name: Annotated[
        Optional[str],
        Field(default=None, description="Target bucket for all stored images (default bucket if unset)."),
    ] = None
    enable_object_detection: Annotated[
        Optional[bool],
        Field(default=None, description="Enable object detection and crop extraction for every image."),
    ] = None
    detection_confidence: Annotated[
        Optional[float],
        Field(default=None, ge=0.1, le=1.0, description="Object detection confidence threshold."),
    ] = None
    tags: Annotated[
        Optional[List[str]],
        Field(default_factory=list, description="Tags applied to every image in the batch."),
    ]


class BatchJobStateEnum(str, Enum):
    """Lifecycle states for an asynchronous batch ingestion job."""

    pending = "pending"
    running = "running"
    completed = "completed"
    completed_with_errors = "completed_with_errors"
    failed = "failed"
    cancelled = "cancelled"


class BatchItemStatusEnum(str, Enum):
    """Per-item processing status within a batch job."""

    pending = "pending"
    running = "running"
    success = "success"
    error = "error"
    skipped = "skipped"


class BatchProcessExistingRequest(BaseModel):
    """Request model for batch-processing videos that already exist in storage.

    Either provide an explicit list of ``items`` (per-video overrides), or a
    ``bucket_name`` selector (optionally narrowed by ``prefix``) to process every
    video found in that bucket. Selector-level ``frame_interval`` /
    ``enable_object_detection`` / ``detection_confidence`` / ``tags`` apply to all
    videos matched by the selector.
    """

    items: Annotated[
        Optional[List[VideoRequest]],
        Field(default=None, description="Explicit list of videos to process."),
    ] = None
    bucket_name: Annotated[
        Optional[str],
        Field(default=None, description="Selector: process all videos in this bucket."),
    ] = None
    prefix: Annotated[
        Optional[str],
        Field(default=None, description="Selector: only video_ids starting with this prefix."),
    ] = None
    frame_interval: Annotated[
        Optional[int],
        Field(default=None, ge=1, le=60, description="Extract every Nth frame (default: 15)."),
    ] = None
    enable_object_detection: Annotated[
        Optional[bool],
        Field(default=None, description="Enable object detection and crop extraction."),
    ] = None
    detection_confidence: Annotated[
        Optional[float],
        Field(default=None, ge=0.1, le=1.0, description="Object detection confidence threshold."),
    ] = None
    tags: Annotated[
        Optional[List[str]],
        Field(default_factory=list, description="Tags associated with every video in the batch."),
    ]


class DirectoryIngestRequest(BaseModel):
    """Request model for backward-compatible directory ingestion.

    Walks ``dir_path`` (resolved against the configured ingest data root) and
    submits every supported media file as a batch job. Mirrors the EOL
    milvus-dataprep host-directory ingest contract.
    """

    dir_path: Annotated[
        str,
        Field(description="Directory to ingest, relative to the configured ingest data root."),
    ]
    bucket_name: Annotated[
        Optional[str],
        Field(default=None, description="Target bucket for stored videos (default bucket if unset)."),
    ] = None
    recursive: Annotated[
        bool,
        Field(default=False, description="Recurse into subdirectories (the 'meta' dir is skipped)."),
    ] = False
    frame_interval: Annotated[
        Optional[int],
        Field(default=None, ge=1, le=60, description="Extract every Nth frame (default: 15)."),
    ] = None
    enable_object_detection: Annotated[
        Optional[bool],
        Field(default=None, description="Enable object detection and crop extraction."),
    ] = None
    detection_confidence: Annotated[
        Optional[float],
        Field(default=None, ge=0.1, le=1.0, description="Object detection confidence threshold."),
    ] = None
    tags: Annotated[
        Optional[List[str]],
        Field(default_factory=list, description="Tags associated with every ingested file."),
    ]


class BatchItemResult(BaseModel):
    """Result of processing a single item within a batch job."""

    identifier: Annotated[str, Field(description="Human-readable item identifier (e.g. filename).")]
    bucket_name: Optional[str] = None
    video_id: Optional[str] = None
    status: BatchItemStatusEnum = BatchItemStatusEnum.pending
    message: Optional[str] = None
    embeddings_count: Optional[int] = None


class BatchSubmitResponse(DataPrepResponse):
    """Response returned when a batch job is accepted (HTTP 202)."""

    job_id: Annotated[str, Field(description="Identifier used to poll job status.")]
    accepted: Annotated[int, Field(description="Number of items accepted into the job.")]


class BatchJobStatus(DataPrepResponse):
    """Status and per-item results for an asynchronous batch job."""

    job_id: str
    state: BatchJobStateEnum
    source: Optional[str] = None
    total: int = 0
    completed: int = 0
    failed: int = 0
    items: Annotated[List[BatchItemResult], Field(default_factory=list)]
    created_ts: Optional[float] = None
    updated_ts: Optional[float] = None


class VideoInfo(BaseModel):
    """Information about a video file in Minio storage"""

    video_id: str
    video_name: str
    video_path: str
    creation_ts: str


class BucketVideoListResponse(DataPrepResponse):
    """Response model for list of videos in a bucket"""

    bucket_name: str
    videos: Annotated[
        List[VideoInfo],
        Field(
            default_factory=list,
            description="List of video information objects containing video details",
        ),
    ]


class FileListResponse(DataPrepResponse):
    """Response model for list of video files present in storage server"""

    bucket_name: str
    files: Optional[List[str]]


class VideoSummaryRequest(BaseModel):
    """Request model for text summary processing with video timestamp references"""

    bucket_name: Annotated[
        str, Field(description="The Minio bucket name where the referenced video is stored")
    ]
    video_id: Annotated[
        str, Field(description="The video ID (directory) containing the referenced video")
    ]
    video_summary: Annotated[
        str, Field(description="The text summary for the video to be embedded")
    ]
    video_start_time: Annotated[
        float, Field(description="Start timestamp in seconds for the video or video chunk")
    ]
    video_end_time: Annotated[
        float, Field(description="End timestamp in seconds for the video or video chunk")
    ]
    tags: Annotated[
        Optional[List[str]],
        Field(
            default_factory=list,
            description="List of tags to be associated with the video. Useful for filtering the search.",
        ),
    ]


class TelemetryStageTiming(BaseModel):
    """Represents the percentage contribution of a processing stage."""

    name: str = Field(description="Stage label (extraction, detection, embedding, storage)")
    seconds: float = Field(ge=0.0, description="Summed duration for the stage")
    percent_of_total: float = Field(
        ge=0.0,
        le=100.0,
        description="Percentage of overall pipeline wall time",
    )


class TelemetryBatchDetail(BaseModel):
    """Timing details for a single batch."""
    stream_id: int = Field(ge=0)
    batch_index: int = Field(ge=0)
    input_frames: int = Field(ge=0)
    items_after_detection: int = Field(ge=0)
    detection_seconds: float = Field(ge=0.0)
    embedding_seconds: float = Field(ge=0.0)
    embedding_infer_seconds: float = Field(ge=0.0)
    storage_seconds: float = Field(ge=0.0)
    total_seconds: float = Field(ge=0.0)
    embeddings_stored: int = Field(ge=0)


class TelemetryCounts(BaseModel):
    """Aggregate frame and embedding counts."""
    stream_id: int = Field(ge=0)
    frames_extracted: int = Field(ge=0)
    items_after_detection: int = Field(ge=0)
    embeddings_stored: int = Field(ge=0)


class TelemetryThroughput(BaseModel):
    """Derived throughput metrics."""

    decode_throughput: float = Field(ge=0.0)
    detect_throughput: float = Field(ge=0.0)
    embeddings_throughput: float = Field(ge=0.0)
    store_throughput: float = Field(ge=0.0)
    embedding_infer_throughput: float = Field(ge=0.0)
    pipeline_throughput: float = Field(ge=0.0)
    pipeline_throughput_with_od: float = Field(ge=0.0)



class TelemetryVideoMetadata(BaseModel):
    """Snapshot of the processed video's metadata."""

    bucket_name: str
    video_id: str
    filename: str
    frame_interval: int
    fps: Optional[float] = None
    total_frames: Optional[int] = None
    video_duration_seconds: Optional[float] = None
    tags: List[str] = Field(default_factory=list)
    video_url: Optional[str] = None
    video_rel_url: Optional[str] = None


class TelemetryProcessingConfig(BaseModel):
    """Processing configuration persisted with telemetry."""

    object_detection_enabled: bool
    detection_confidence: Optional[float] = None
    parallel_workers: Optional[int] = None
    batch_size: Optional[int] = None


class TelemetryTimestamps(BaseModel):
    """Request lifecycle timestamps."""

    requested_at: str = Field(description="UTC timestamp when processing started")
    completed_at: str = Field(description="UTC timestamp when processing finished")
    wall_time_seconds: float = Field(ge=0.0)


class TelemetryRecord(BaseModel):
    """Stored telemetry entry served via /telemetry endpoint."""

    request_id: str
    source: str
    timestamps: TelemetryTimestamps
    video: TelemetryVideoMetadata
    config: TelemetryProcessingConfig
    counts: TelemetryCounts
    pipeline_stats: Dict[str, Any] = Field(default_factory=dict)
    stage_duration: Dict[str, Any] = Field(default_factory=dict)
    stage_throughput: Dict[str, Any] = Field(default_factory=dict)
    batches: List[TelemetryBatchDetail] = Field(default_factory=list)


class TelemetryResponse(BaseModel):
    """Response payload for /telemetry endpoint."""

    count: int
    items: List[TelemetryRecord]
