# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from pydantic import BaseModel, Field
from typing import Annotated, Optional, List, Union, Dict
from fastapi import Form
from enum import Enum

from video_analyzer.schemas.state import SummarizationStatus
from video_analyzer.core.settings import settings


class TASKNAME(Enum):
    """Registered built-in task names. Everything else is a dynamic task
    registered at runtime through the /v1/tasks endpoint."""
    SUMMARY = "summary"
    SUMMARY_ZH = "summary_zh"

class SUMMARIZATION_METHOD_TYPE(Enum):
    """
    Summarization method types
    """
    SIMPLE = "SIMPLE"                   # Simple summarization, do not incorporate time dependency between consecutive chunks
    USE_VLM_T_1 = "USE_VLM_T-1"         # Incorporate time dependency between consecutive chunks for VLM inference
    USE_LLM_T_1 = "USE_LLM_T-1"         # Incorporate time dependency between consecutive chunks for LLM inference
    USE_ALL_T_1 = "USE_ALL_T-1"         # Incorporate time dependency between consecutive chunks for both VLM and LLM inference


class SummarizerParamsManager:
    
    @staticmethod
    def list_supported_summarization_methods():
        """
        Return all supported summarization methods in class `SUMMARIZATION_METHOD_TYPE`
        
        Returns:
            list: a list of SUMMARIZATION_METHOD_TYPE members
        """
        available_list = [str(_.value) for _ in SUMMARIZATION_METHOD_TYPE]
        return available_list
    
    @staticmethod
    def list_supported_summarization_tasks():
        """
        Return all supported summarization tasks (built-in + runtime-registered).

        Returns:
            list: a list of task name strings
        """
        available_list = [str(_.value) for _ in TASKNAME]
        # Include dynamic tasks registered at runtime. Lazy import to avoid
        # circular dependency at module-load time.
        try:
            from video_analyzer.prompts.prompt_registry import get_registry
            available_list.extend(get_registry().names())
        except Exception:
            # Registry unavailable (e.g. during tests) — fall back to built-ins only.
            pass
        return available_list


class SummarizationRequest(BaseModel):
    """Request schema for the summarization endpoint"""
    video: Annotated[str, Field(description="Path to the video file, support 'file://', 'http://', 'https://' and local path.")]
    video_subtitles: Annotated[Optional[Dict[str, str]], Field(description=(
        "Video subtitles in SubRip (.srt) format. Supported inputs:\n"
        "- {\"url\": \"https://.../subs.srt\"}: Preferred in container environments. The service will download and parse via HTTP(S).\n"
        "- {\"text\": \"1\\n00:00:00,000 --> 00:00:02,000\\n...\"}: Inline SRT text. Best for short videos/small subtitles.\n"
        "- {\"b64gzip\": \"<base64>\"}: Base64 of gzip-compressed SRT. Recommended for long videos to reduce request size.\n"
        "Notes:\n"
        "- URL must be http/https; the service streams the download with a size cap.\n"
        "- Inline text and b64gzip are checked against size limits (see settings.MAX_SUBTITLE_BYTES).\n"
        "- For object storage, use pre-signed URLs (e.g., S3/MinIO).\n"
        "Examples:\n"
        "  {\"url\": \"https://bucket/video/subs.srt\"}\n"
        "  {\"text\": \"1\\n00:00:00,000 --> 00:00:02,000\\nHello\\n...\"}\n"
        "  {\"b64gzip\": \"H4sIAAAAA...\"}\n"
    ))] = None
    prompt: Annotated[Optional[str], Field(description="User prompt to guide summarization details")] = None
    method: Annotated[
        Optional[str],
        Field(description=(
            "Summarization method selecting how consecutive chunks interact.\n"
            "Supported values:\n"
            "- 'SIMPLE': No temporal dependency between chunks.\n"
            "- 'USE_VLM_T-1': Only the VLM stage consumes the previous chunk context.\n"
            "- 'USE_LLM_T-1': Only the LLM stage consumes the previous chunk context.\n"
            "- 'USE_ALL_T-1': Both stages rely on previous chunk context for maximum coherence.\n"
            "Notes: Prefer the default unless you explicitly tune temporal dependencies."
        )),
    ] = SUMMARIZATION_METHOD_TYPE.USE_ALL_T_1.value
    task: Annotated[
        Optional[str],
        Field(description=(
            "Task name selecting the prompt/pipeline flavor.\n"
            "Built-in values:\n"
            "- 'summary': Default multi-level video summarization, English prompts (global/macro/local).\n"
            "- 'summary_zh': Same multi-level summarization with Chinese prompts.\n"
            "Any other value must be a dynamic task registered via POST /v1/tasks;\n"
            "unknown task names are rejected by the prompt factory."
        )),
    ] = TASKNAME.SUMMARY.value
    processor_kwargs: Annotated[Optional[Dict[str, Union[float, str, int, list[int]]]], 
                                Field(description="Summarization processing parameters: "
                                      "process_fps, chunking_method, levels, level_sizes, etc.")] = {}


class SummarizationResponse(BaseModel):
    """Response schema for the summarization endpoint"""
    status: Annotated[SummarizationStatus, Field(description="Current status of the summarization job")]
    summary: Annotated[Optional[str], Field(description="Summary of the video")]
    message: Annotated[str, Field(description="Human-readable status message")] = None
    job_id: Annotated[Optional[str], Field(description="Unique identifier for the summarization job")] = None
    video_name: Annotated[Optional[str], Field(description="Name of the processed video file")] = None
    video_duration: Annotated[Optional[float], Field(description="Duration of the video in seconds")] = None
    # Token usage statistics (unified VLM+LLM)
    usage: Annotated[Optional[Dict[str, int]], Field(description=(
        "Token usage statistics (unified VLM+LLM). "
        "Includes prompt_tokens (text only), image_tokens, completion_tokens, and total_tokens."
    ))] = None


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


class ModelInfo(BaseModel):
    """Schema for an individual whisper model's detailed information"""
    model_id: str
    display_name: str
    base_url: str
    description: str


class AvailableModelsResponse(BaseModel):
    """Response schema for listing available models endpoint"""
    llms: Annotated[List[ModelInfo], Field(description="List of available models variants with detailed information")]
    vlms: Annotated[List[ModelInfo], Field(description="List of available models variants with detailed information")]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "llms": [
                        {
                            "model_id": "Qwen/Qwen3-32B-AWQ",
                            "display_name": "Qwen/Qwen3-32B-AWQ",
                            "base_url": "http://localhost:41090/v1",
                            "description": "Large Language Models for summarization"
                        }
                    ],
                    "vlms": [
                        {
                            "model_id": "Qwen/Qwen2.5-VL-7B-Instruct",
                            "display_name": "Qwen/Qwen2.5-VL-7B-Instruct",
                            "base_url": "http://localhost:41091/v1",
                            "description": "Vision and Language Models for summarization"
                        }
                    ]
                }
            ]
        }
    }
