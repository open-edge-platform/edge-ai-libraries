# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from enum import Enum
from typing import Annotated, List, Optional, Tuple

from pydantic import BaseModel, Field


class StatusEnum(str, Enum):
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
            description="The video filename within the video_id directory (if omitted, first video found is used)"
        ),
    ] = None
    frame_interval: Annotated[
        Optional[int],
        Field(
            ge=1,
            le=60,
            description="Extract every Nth frame for processing (default: 15)",
        ),
    ] = None
    enable_object_detection: Annotated[
        Optional[bool],
        Field(
            description="Enable object detection and crop extraction (default: True)"
        ),
    ] = None
    detection_confidence: Annotated[
        Optional[float],
        Field(
            ge=0.1,
            le=1.0,
            description="Confidence threshold for object detection (default: 0.85)",
        ),
    ] = None
    tags: Annotated[
        Optional[List[str]],
        Field(
            default_factory=list,
            description="List of tags to be associated with the video. Useful for filtering the search.",
        ),
    ]
    object_detection: Optional[ObjectDetectionConfig] = Field(
        default=None,
        description="Object detection configuration for enhanced frame extraction"
    )


class EnhancedVideoRequest(VideoRequest):
    """Enhanced request model for video processing with object detection support"""

    object_detection: ObjectDetectionConfig = Field(
        default_factory=ObjectDetectionConfig,
        description="Object detection configuration for enhanced frame extraction"
    )


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
        str,
        Field(
            description="The video ID (directory in Minio bucket) containing the referenced video"
        ),
    ]
    video_summary: Annotated[
        str, Field(description="The summary text for the video to be embedded")
    ]
    video_start_time: Annotated[
        float,
        Field(
            ge=0,
            description="The start timestamp in seconds for the video or video chunk",
        ),
    ]
    video_end_time: Annotated[
        float,
        Field(description="The end timestamp in seconds for the video or video chunk"),
    ]
    tags: Annotated[
        Optional[List[str]],
        Field(
            default_factory=list,
            description="List of tags to be associated with the video. Useful for filtering the search.",
        ),
    ]
