# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import traceback

from fastapi import APIRouter, HTTPException, status

from video_analyzer.schemas.summarization import (
    ErrorResponse,
    SummarizationResponse,
    SummarizationRequest,
    SummarizerParamsManager,
)
from video_analyzer.schemas.state import SummarizationStatus
from video_analyzer.core.summarizer import ModelConfig, VideoSummarizer
from video_analyzer.utils.logger import logger
from video_analyzer.utils.file_utils import validate_video_path, download_to_temp

router = APIRouter()
model_cfg = ModelConfig()

@router.post(
    "/summary",
    response_model=SummarizationResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    tags=["Summarization API"],
    summary="Summarize audio from uploaded video file or a video stored at Minio"
)
async def summarize_video(
    request: SummarizationRequest,
) -> SummarizationResponse:
    """
    Generate a summary text from a video file to describe its content.
    
    To provide the video:
    - support "file://", "http://", "https://" and local path.
     
    Args:
        request: Form video containing the file and summarization settings
    
    Returns:
        A response with the processing status and summary output
    """
    temp_video_path = None
    try:
        # Parse request parameters
        video_subtitles = request.video_subtitles
        user_prompt = request.prompt
        method = request.method
        task = request.task

        # Handle caption-only mode: allow video="none" when subtitles are provided
        if not request.video or str(request.video).lower() == "none":
            if not video_subtitles:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ErrorResponse(
                        error_message="Summarization failed!",
                        details="Either video or video_subtitles must be provided"
                    ).model_dump()
                )
            # Caption-only mode
            logger.info("Caption-only mode: no video file provided, using subtitles only")
            video_path = "none"
        else:
            # Normal video mode: validate and download video file
            video_path = validate_video_path(request.video)
            temp_video_path = download_to_temp(video_path)
            if temp_video_path:
                video_path = temp_video_path

        # Validate summarization method
        available_methods = SummarizerParamsManager.list_supported_summarization_methods()
        if method not in available_methods:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse(
                    error_message=f"Summarization failed!",
                    details=f"Unsupported summarization method: {method}, choices: {available_methods}"
                ).model_dump()
            )
        available_tasks = SummarizerParamsManager.list_supported_summarization_tasks()
        if task not in available_tasks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse(
                    error_message=f"Summarization failed!",
                    details=f"Unsupported summarization task: {task}, choices: {available_tasks}"
                ).model_dump()
            )

        processor_kwargs = request.processor_kwargs
        logger.debug(f"Summarization parameters: task={task}, video={video_path}, method={method}, processor_kwargs:\n"
                     f"{processor_kwargs}")

        # Create a VideoSummarizer instance
        summarizer = VideoSummarizer(
            task=task,
            video_path=video_path,
            user_prompt=user_prompt,
            video_subtitles=video_subtitles,
            method=method,
            vlm_model_name=model_cfg.VLM_MODEL_NAME,
            llm_model_name=model_cfg.LLM_MODEL_NAME,
            vlm_base_url=model_cfg.VLM_BASE_URL,
            llm_base_url=model_cfg.LLM_BASE_URL,
            vlm_api_key=model_cfg.VLM_API_KEY,
            llm_api_key=model_cfg.LLM_API_KEY,
            **(processor_kwargs),
        )

        # Perform summarization
        job_id, response = await summarizer.summarize()

        try:
            summary = response['summary']
            video_duration = response['video_duration']
            usage = response.get('usage')  # Extract token usage
        except Exception as e:
            raise RuntimeError(f"Failed to generate summary output: {str(e)}")

        if summary.startswith("Error:"):
            return SummarizationResponse(
                status=SummarizationStatus.FAILED,
                summary=summary,
                message="Summarization generated error ouputs.",
                job_id=job_id,
                video_name=video_path,
                video_duration=video_duration,
                usage=usage
            )

        return SummarizationResponse(
            status=SummarizationStatus.COMPLETED,
            summary=summary,
            message="Summarization completed successfully",
            job_id=job_id,
            video_name=video_path,
            video_duration=video_duration,
            usage=usage
        )
    except HTTPException as http_exc:
        raise http_exc

    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Summarization failed: {str(e)}")
        logger.error(f"Error details: {error_details}")

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error_message=f"Summarization failed!",
                details="An error occurred during Summarization. Please check logs for details."
            ).model_dump()
        )
    finally:
        if temp_video_path:
            import os
            try:
                os.unlink(temp_video_path)
            except OSError:
                pass