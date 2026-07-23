# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Request/response schemas for the VSS-compatibility endpoints.

These mirror the API contract exposed by the previous Edge AI Libraries
release (``POST /transcriptions`` / ``GET /models``), which is what VSS's
pipeline-manager (sample-applications/video-search-and-summarization) calls.
"""
from enum import Enum
from typing import Annotated, List, Optional

from fastapi import File, Form, UploadFile
from pydantic import BaseModel, Field
from pydantic.json_schema import SkipJsonSchema


class TranscriptionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"


class VssTranscriptionForm:
    """Dependency class for the VSS ``POST /transcriptions`` multipart form.

    Supports two mutually-exclusive input modes, matching the previous
    release's contract:
      1. Direct file upload — provide ``file``.
      2. MinIO video source — provide ``minio_bucket``, ``video_id`` and
         ``video_name``.
    """

    def __init__(
        self,
        minio_bucket: Annotated[
            str,
            Form(description="MinIO bucket containing the video file. Required if not uploading a file directly."),
        ] = "",
        video_id: Annotated[
            str,
            Form(description="ID/prefix of the video in the MinIO bucket. Required if not uploading a file directly."),
        ] = "",
        video_name: Annotated[
            str,
            Form(description="Name of the video file in the MinIO bucket. Required if not uploading a file directly."),
        ] = "",
        device: Annotated[
            str,
            Form(description="_(Optional)_ Device hint (informational; this service uses its configured ASR device)."),
        ] = "",
        model_name: Annotated[
            str,
            Form(description="_(Optional)_ Model hint (informational; this service uses its single configured ASR model)."),
        ] = "",
        include_timestamps: Annotated[
            bool,
            Form(description="_(Optional)_ Included for API parity; this service always stores a timestamped transcript alongside the plain-text one."),
        ] = True,
        file: Annotated[
            UploadFile | SkipJsonSchema[None | str],
            File(description="Video/audio file to transcribe. Optional if using MinIO source."),
        ] = None,
    ):
        self.file = file
        self.device = device.strip() if isinstance(device, str) else device
        self.model_name = model_name.strip() if isinstance(model_name, str) else model_name
        self.include_timestamps = include_timestamps
        self.minio_bucket = minio_bucket.strip() if isinstance(minio_bucket, str) else minio_bucket
        self.video_id = video_id.strip() if isinstance(video_id, str) else video_id
        self.video_name = video_name.strip() if isinstance(video_name, str) else video_name

    def has_minio_source(self) -> bool:
        return bool(self.minio_bucket and self.video_id and self.video_name)


class VssTranscriptionResponse(BaseModel):
    """Response schema for POST /transcriptions."""

    status: Annotated[TranscriptionStatus, Field(description="Status of the transcription job")]
    message: Annotated[str, Field(description="Human-readable status message")]
    job_id: Annotated[Optional[str], Field(description="Session/job identifier")] = None
    transcript_path: Annotated[Optional[str], Field(description="Path (filesystem or minio://) to the transcript")] = None
    video_name: Annotated[Optional[str], Field(description="Name of the processed video/audio file")] = None
    video_duration: Annotated[Optional[float], Field(description="Duration of the media in seconds")] = None


class WhisperModelInfo(BaseModel):
    """Schema for an individual whisper model's detailed information."""

    model_id: str
    display_name: str
    description: str


class AvailableModelsResponse(BaseModel):
    """Response schema for GET /models."""

    models: Annotated[List[WhisperModelInfo], Field(description="Available ASR model variant(s)")]
    default_model: Annotated[str, Field(description="The default/only model used for transcription")]
