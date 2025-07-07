# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from enum import Enum
from typing import Annotated, List, Optional

from pydantic import BaseModel, Field


class StatusEnum(str, Enum):
    success = "success"
    error = "error"


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
    chunk_duration: Annotated[
        Optional[int],
        Field(
            ge=3,
            description="Interval of time in seconds to create different chunks of video. Helps in frame sampling.",
        ),
    ] = None
    clip_duration: Annotated[
        Optional[int],
        Field(
            ge=3,
            description="Length of clip in seconds, inside each of the video chunks. Frames for embedding are selected from this interval.",
        ),
    ] = None
    tags: Annotated[
        Optional[List[str]],
        Field(
            default_factory=list,
            description="List of tags to be associated with the video. Useful for filtering the search.",
        ),
    ] = None


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
    ] = None
