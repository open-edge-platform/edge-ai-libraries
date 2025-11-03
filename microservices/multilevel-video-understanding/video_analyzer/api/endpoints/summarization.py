# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import logging
import traceback
from typing import Annotated

from fastapi import APIRouter, HTTPException, status, Depends

from video_analyzer.schemas.summarization import (
    ErrorResponse,
    SummarizationResponse,
    SummarizationRequest,
    SummarizerMethodsManager,
)
from video_analyzer.schemas.state import SummarizationStatus
from video_analyzer.core.summarizer import ModelConfig, VideoSummarizer
from video_analyzer.utils.logger import logger

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
    try:
        # Parse request parameters
        video_path = request.video
        user_prompt = request.prompt
        method = request.method
        
        # Validate summarization method
        available_methods = SummarizerMethodsManager.list_supported_summarization_methods()
        if method not in available_methods:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse(
                    error_message=f"Summarization failed!",
                    details=f"Unsupported summarization method: {method}, choices: {available_methods}"
                ).model_dump()
            )

        processor_kwargs = request.processor_kwargs
        logger.debug(f"Summarization parameters: video={video_path}, method={method}, processor_kwargs:\n"
                     f"{processor_kwargs}")
        
        # Create a VideoSummarizer instance
        summarizer = VideoSummarizer(
            video_path=video_path,
            user_prompt=user_prompt,
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
        except Exception as e:
            raise RuntimeError(f"Failed to generate summary output: {str(e)}")
        
        if summary.startswith("Error:"):
            return SummarizationResponse(
                status=SummarizationStatus.FAILED,
                summary=summary,
                message="Summarization generated error ouputs.",
                job_id=job_id,
                video_name=video_path,
                video_duration=video_duration
            )
        
        return SummarizationResponse(
            status=SummarizationStatus.COMPLETED,
            summary=summary,
            message="Summarization completed successfully",
            job_id=job_id,
            video_name=video_path,
            video_duration=video_duration
        )
    except HTTPException as http_exc:
        raise http_exc
    
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Summarization failed: {str(e)}")
        logger.debug(f"Error details: {error_details}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error_message=f"Summarization failed!",
                details="An error occurred during Summarization. Please check logs for details."
            ).model_dump()
        )