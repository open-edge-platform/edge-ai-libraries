from enum import Enum
from typing import Annotated, Optional, List, Literal, Tuple, get_type_hints, Type

from fastapi import Body, UploadFile, File, Form, Query, Depends
from fastapi.datastructures import FormData
from pydantic import BaseModel, Field, field_validator, BeforeValidator
from pydantic.json_schema import SkipJsonSchema

from audio_intelligence.core.settings import settings
from audio_intelligence.schemas.types import TranscriptionStatus, DeviceType


EnabledWhisperModels = settings.EnabledWhisperModelsEnum
class HealthResponse(BaseModel):
    """Response schema for the health check endpoint"""
    status: Annotated[str, Field(description="Current health status of the API")] = settings.API_STATUS
    version: Annotated[str, Field(description="API version")] = settings.API_VER
    message: Annotated[str, Field(description="Detailed status message")] = settings.API_STATUS_MSG

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "healthy",
                    "version": "1.0.0",
                    "message": "Service is running smoothly."
                }
            ]
        }
    }


class TranscriptionFormData:
    """
    Dependency class for transcription form data validation.
    This class uses FastAPI's Form parameters to handle multipart form data.
    
    Supports two modes:
    1. Direct file upload: Provide 'file' parameter
    2. MinIO video source: Provide 'minio_bucket', 'video_id', and 'video_name' parameters
    """
    def __init__(
        self,
        minio_bucket: Annotated[
            str,
            Form(description="MinIO bucket containing the video file. Required if not using filsystem for video source.")
        ] = "",
        video_id: Annotated[
            str,
            Form(description="ID/prefix of the video in the MinIO bucket. Required if not using filsystem for video source.")
        ] = "",
        video_name: Annotated[
            str,
            Form(description="Name of the video file in the MinIO bucket. Required if not using filsystem for video source.")
        ] = "",
        device: Annotated[
            DeviceType | SkipJsonSchema[str], 
            Form(description="_(Optional)_ Device to use for transcription - 'cpu' or 'auto'. **Default value : cpu**")
        ] = settings.DEFAULT_DEVICE,
        model_name: Annotated[
            EnabledWhisperModels | SkipJsonSchema[str],
            Form(description="_(Optional)_ Variant of the whisper model to use. **Default value : 'small.en' or first available model**")
        ] = "",
        include_timestamps: Annotated[
            bool, 
            Form(description="_(Optional)_ A flag to include timestamps in the transcription output. **Default value : True**")
        ] = True,
        file: Annotated[UploadFile | SkipJsonSchema[None | str], File(description="Select video file to be transcribed. Optional if using MinIO source.")] = None,
    ):
        self.file = file
        self.device = device.strip().lower() if isinstance(device, str) else device
        self.model_name = model_name.strip().lower() if isinstance(model_name, str) else model_name
        self.include_timestamps = include_timestamps
        self.minio_bucket = minio_bucket.strip() if isinstance(minio_bucket, str) else minio_bucket
        self.video_id = video_id.strip() if isinstance(video_id, str) else video_id
        self.video_name = video_name.strip() if isinstance(video_name, str) else video_name



class TranscriptionResponse(BaseModel):
    """Response schema for the transcription endpoint"""
    status: Annotated[TranscriptionStatus, Field(description="Current status of the transcription job")]
    message: Annotated[str, Field(description="Human-readable status message")]
    job_id: Annotated[Optional[str], Field(description="Unique identifier for the transcription job")] = None
    transcript_path: Annotated[Optional[str], Field(description="Path to the transcript file")] = None
    video_name: Annotated[Optional[str], Field(description="Name of the processed video file")] = None
    video_duration: Annotated[Optional[float], Field(description="Duration of the video in seconds")] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "completed",
                    "message": "Transcription completed successfully",
                    "job_id": "1234-5678-90ab-cdef",
                    "transcript_path": "/transcripts/meeting_recording.txt",
                    "video_name": "meeting_recording.mp4",
                    "video_duration": 120.5
                }
            ]
        }
    }


class ErrorResponse(BaseModel):
    """Response schema for errors"""
    error_message: Annotated[str, Field(description="Human-readable error message")]
    details: Annotated[Optional[str], Field(description="Additional error details")] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "error_message": "Failed to process video file",
                    "details": "Invalid file format"
                }
            ]
        }
    }


class WhisperModelInfo(BaseModel):
    """Schema for an individual whisper model's detailed information"""
    model_id: str
    display_name: str
    description: str


class AvailableModelsResponse(BaseModel):
    """Response schema for listing available models endpoint"""
    models: Annotated[List[WhisperModelInfo], Field(description="List of available whisper model variants with detailed information")]
    default_model: Annotated[str, Field(description="The default model used for transcription")]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "models": [
                        {
                            "model_id": "tiny.en",
                            "display_name": "Tiny (English)",
                            "description": "English only version of tiny whisper model. Significantly less accuracy, extremely fast inference."
                        },
                        {
                            "model_id": "base.en",
                            "display_name": "Base Model (English)",
                            "description": "English only version of base whisper model."
                        }
                    ],
                    "default_model": "tiny.en"
                }
            ]
        }
    }