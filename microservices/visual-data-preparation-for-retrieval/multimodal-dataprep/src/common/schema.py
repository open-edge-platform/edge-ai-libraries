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

    enabled: bool = Field(default=False, description="Enable object detection for frame extraction")
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
    vectordb_backend: Optional[str] = None
    vectordb_status: Optional[str] = None
    vectordb_error: Optional[str] = None
    storage_backend: Optional[str] = None
    default_bucket_name: Optional[str] = None
    live_streams_enabled: Optional[bool] = None
    live_streams: Annotated[
        Optional[Dict[str, int]],
        Field(
            default=None,
            description="Histogram of registered live streams by state, plus a 'total'.",
        ),
    ] = None


class VideoRequest(BaseModel):
    """Request model for processing media already held in the configured storage backend."""

    bucket_name: Annotated[
        Optional[str],
        Field(
            description="The bucket (object storage) or top-level directory (local "
            "storage) holding the media. Defaults to the configured bucket when omitted."
        ),
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
            description="Extract every Nth frame for processing (defaults to the service's configured frame_interval, 15 unless overridden)",
            json_schema_extra={"example": 15},
        ),
    ] = None
    enable_object_detection: Annotated[
        Optional[bool],
        Field(
            description="Enable object detection and crop extraction (defaults to the service's configured setting, enabled unless overridden)",
            json_schema_extra={"example": True},
        ),
    ] = None
    detection_confidence: Annotated[
        Optional[float],
        Field(
            ge=0.1,
            le=1.0,
            description="Confidence threshold for object detection (defaults to the service's configured threshold, 0.85 unless overridden)",
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
        Field(
            default=None,
            description="Base64-encoded image (bare or 'data:' URL) when type=image_base64.",
        ),
    ] = None
    image_url: Annotated[
        Optional[str],
        Field(default=None, description="Absolute http(s) image URL when type=image_url."),
    ] = None
    filename: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Optional filename hint; extension is derived from the real bytes.",
        ),
    ] = None
    tags: Annotated[
        Optional[List[str]],
        Field(
            default=None, description="Optional per-image tags (merged with request-level tags)."
        ),
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
        Field(
            default=None,
            description="Target bucket for the stored image (default bucket if unset).",
        ),
    ] = None
    enable_object_detection: Annotated[
        Optional[bool],
        Field(
            default=None,
            description="Enable object detection and crop extraction (defaults to the service's configured setting, enabled unless overridden).",
        ),
    ] = None
    detection_confidence: Annotated[
        Optional[float],
        Field(
            default=None,
            ge=0.1,
            le=1.0,
            description="Object detection confidence threshold (defaults to the service's configured threshold, 0.85 unless overridden).",
        ),
    ] = None


class ImageBatchIngestRequest(BaseModel):
    """Batch JSON ingestion request: many typed image sources -> one async job."""

    images: Annotated[
        List[ImageIngestItem],
        Field(description="List of typed image sources (base64 or URL)."),
    ]
    bucket_name: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Target bucket for all stored images (default bucket if unset).",
        ),
    ] = None
    enable_object_detection: Annotated[
        Optional[bool],
        Field(
            default=None, description="Enable object detection and crop extraction for every image."
        ),
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
        Field(
            default=None,
            ge=1,
            le=60,
            description="Extract every Nth frame (defaults to the service's configured frame_interval, 15 unless overridden).",
        ),
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
    host-directory ingest contract of the retired dataprep service.
    """

    dir_path: Annotated[
        str,
        Field(description="Directory to ingest, relative to the configured ingest data root."),
    ]
    bucket_name: Annotated[
        Optional[str],
        Field(
            default=None, description="Target bucket for stored videos (default bucket if unset)."
        ),
    ] = None
    recursive: Annotated[
        bool,
        Field(
            default=False, description="Recurse into subdirectories (the 'meta' dir is skipped)."
        ),
    ] = False
    frame_interval: Annotated[
        Optional[int],
        Field(
            default=None,
            ge=1,
            le=60,
            description="Extract every Nth frame (defaults to the service's configured frame_interval, 15 unless overridden).",
        ),
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
    store_copy: Annotated[
        bool,
        Field(
            default=True,
            description="Copy each file into the storage backend. Set to false to "
            "reference files in place on the mounted ingest root (no on-disk "
            "duplication); referenced media is still duplicate-checked, listed by "
            "GET /media and streamable via GET /media/download.",
        ),
    ] = True
    metadata: Annotated[
        Optional[Dict[str, Any]],
        Field(
            default_factory=dict,
            description="Caller-supplied metadata applied to every ingested file and "
            "persisted as filterable fields. A meta/<basename>.json sidecar may "
            "supply per-file metadata, which takes precedence on key collisions. "
            "Keys colliding with the canonical metadata contract are rejected with 400.",
        ),
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
    """Information about a media file known to the service"""

    video_id: str
    video_name: str
    video_path: str
    creation_ts: str
    stored: Annotated[
        bool,
        Field(
            default=True,
            description=(
                "False when the media was ingested by reference (store_copy=false) and "
                "is read from the ingest mount instead of the storage backend."
            ),
        ),
    ]
    source_path: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Host-visible path of referenced media; null for stored media.",
        ),
    ]


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
        str,
        Field(
            description="The bucket (object storage) or top-level directory (local "
            "storage) holding the referenced video."
        ),
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


class LiveStreamStateEnum(str, Enum):
    """Lifecycle states of a registered live (RTSP) stream."""

    pending = "pending"
    starting = "starting"
    running = "running"
    paused = "paused"
    reconnecting = "reconnecting"
    error = "error"
    stopped = "stopped"


#: States in which a worker thread is expected to be alive.
LIVE_ACTIVE_STATES = frozenset(
    {
        LiveStreamStateEnum.starting,
        LiveStreamStateEnum.running,
        LiveStreamStateEnum.reconnecting,
        LiveStreamStateEnum.paused,
    }
)


class LiveStreamCreateRequest(BaseModel):
    """Request model for registering and starting a live RTSP stream."""

    stream_url: Annotated[
        str,
        Field(
            description="RTSP source URL (rtsp:// or rtsps://). Embedded credentials "
            "are accepted for connection but are never returned by the API nor "
            "written to the vector database.",
        ),
    ]
    stream_name: Annotated[
        Optional[str],
        Field(
            default=None,
            max_length=256,
            description="Friendly label; defaults to the redacted URL.",
        ),
    ] = None
    description: Annotated[
        Optional[str],
        Field(default=None, max_length=1024, description="Free-text description of the stream."),
    ] = None
    sensor_id: Annotated[
        Optional[str],
        Field(
            default=None,
            max_length=128,
            pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
            description=(
                "Stable logical identity of the physical source (camera/sensor). "
                "Recorded on every embedding so externally stored media for the "
                "same source can be correlated back to it. Defaults to the "
                "generated stream_id."
            ),
        ),
    ] = None
    frame_interval: Annotated[
        Optional[int],
        Field(
            default=None,
            ge=1,
            le=60,
            description="Sample every Nth frame (defaults to the service's configured frame_interval).",
        ),
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
        Field(
            default_factory=list,
            description="Tags associated with every embedding from this stream.",
        ),
    ]
    start: Annotated[
        bool,
        Field(
            default=True,
            description="Start ingesting immediately. False registers the stream in the paused state.",
        ),
    ] = True


class LiveStreamBatchCreateRequest(BaseModel):
    """Request model for registering several live streams in one call."""

    items: Annotated[
        List[LiveStreamCreateRequest],
        Field(min_length=1, description="Live streams to register."),
    ]


class LiveStreamUpdateRequest(BaseModel):
    """Request model for updating a registered live stream.

    Every field is optional; only supplied fields are changed. Setting ``state``
    to ``paused`` or ``running`` pauses or resumes ingestion without
    deregistering the stream.
    """

    stream_name: Annotated[Optional[str], Field(default=None, max_length=256)] = None
    description: Annotated[Optional[str], Field(default=None, max_length=1024)] = None
    frame_interval: Annotated[Optional[int], Field(default=None, ge=1, le=60)] = None
    enable_object_detection: Annotated[Optional[bool], Field(default=None)] = None
    detection_confidence: Annotated[Optional[float], Field(default=None, ge=0.1, le=1.0)] = None
    tags: Annotated[
        Optional[List[str]],
        Field(default=None, description="Replaces the existing tag list when supplied."),
    ] = None
    state: Annotated[
        Optional[LiveStreamStateEnum],
        Field(
            default=None,
            description="Only 'running' (resume) and 'paused' (pause) are accepted. "
            "Use DELETE to stop and deregister a stream.",
        ),
    ] = None

    @model_validator(mode="after")
    def _validate_state(self):
        """Reject state transitions that are not caller-drivable."""
        if self.state is not None and self.state not in (
            LiveStreamStateEnum.running,
            LiveStreamStateEnum.paused,
        ):
            raise ValueError("state must be either 'running' or 'paused'")
        return self


class LiveStreamStats(BaseModel):
    """Runtime counters for a live stream."""

    frames_processed: int = 0
    embeddings_created: int = 0
    segments_stored: int = 0
    frames_stored: int = 0
    reconnect_count: int = 0
    last_frame_ts: Optional[float] = None
    started_ts: Optional[float] = None
    uptime_seconds: Optional[float] = None


class LiveStreamInfo(BaseModel):
    """A registered live stream as exposed by the API.

    ``stream_url`` is always the redacted form of the source URL: any embedded
    credentials are stripped before the value leaves the registry.
    """

    stream_id: str
    stream_url: Annotated[str, Field(description="Source URL with credentials redacted.")]
    stream_name: str
    description: Optional[str] = None
    state: LiveStreamStateEnum = LiveStreamStateEnum.pending
    bucket_name: Optional[str] = None
    video_id: Annotated[
        Optional[str],
        Field(
            default=None,
            description=(
                "Identity this stream's embeddings and media are stored under. "
                "Always equal to stream_id, so GET /media, GET /media/download "
                "and DELETE /media/{bucket_name}/{video_id} work on live data."
            ),
        ),
    ] = None
    sensor_id: Annotated[
        Optional[str],
        Field(
            default=None,
            description=(
                "Stable logical identity of the physical source, recorded on "
                "every embedding from this stream. Equal to stream_id unless the "
                "caller supplied one at registration."
            ),
        ),
    ] = None
    frame_interval: int
    enable_object_detection: bool
    detection_confidence: float
    tags: Annotated[List[str], Field(default_factory=list)]
    stats: Annotated[LiveStreamStats, Field(default_factory=LiveStreamStats)]
    last_error: Optional[str] = None
    created_ts: Optional[float] = None
    updated_ts: Optional[float] = None


class LiveStreamResponse(DataPrepResponse):
    """Response carrying a single live stream record."""

    stream: LiveStreamInfo


class LiveStreamListResponse(DataPrepResponse):
    """Response carrying all registered live streams."""

    count: int = 0
    streams: Annotated[List[LiveStreamInfo], Field(default_factory=list)]


class LiveStreamBatchItemResult(BaseModel):
    """Per-item outcome of a bulk live-stream create or delete."""

    identifier: Annotated[str, Field(description="Redacted stream URL or stream_id.")]
    stream_id: Optional[str] = None
    status: BatchItemStatusEnum = BatchItemStatusEnum.pending
    message: Optional[str] = None


class LiveStreamBatchResponse(DataPrepResponse):
    """Response for bulk live-stream create/delete operations."""

    accepted: int = 0
    rejected: int = 0
    items: Annotated[List[LiveStreamBatchItemResult], Field(default_factory=list)]


class LiveStreamDeleteRequest(BaseModel):
    """Request model for deleting several live streams in one call."""

    stream_ids: Annotated[
        List[str], Field(min_length=1, description="Streams to stop and deregister.")
    ]


class LiveStreamDeleteResponse(DataPrepResponse):
    """Response returned after stopping and deregistering a live stream."""

    stream_id: str
    embeddings_purged: Annotated[
        Optional[int],
        Field(
            default=None,
            description="Embeddings deleted; -1 when the backend does not report a count.",
        ),
    ] = None
    media_purged: Annotated[
        Optional[int],
        Field(default=None, description="Stored media objects deleted."),
    ] = None
