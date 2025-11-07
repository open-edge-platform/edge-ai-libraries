# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
import os
from fastapi import APIRouter

from video_analyzer.schemas.summarization import AvailableModelsResponse
from video_analyzer.utils.logger import logger

router = APIRouter()


@router.get(
    "/models",
    response_model=AvailableModelsResponse,
    tags=["Models API"],
    summary="Get list of models available for use with detailed information",
)
async def get_available_models() -> AvailableModelsResponse:
    """
    Get a list of available model variants that are configured for summarization.
    
    This endpoint returns all the llm & vlm models that are configured in the service
    and available for summarization requests, along with detailed information including
    display names, descriptions, and the default model that is used when no specific 
    model is requested.
    
    Returns:
        A response with the list of available models with their details and the default model
    """
    logger.debug("Getting available models details")
    
    # Convert dictionaries to ModelInfo objects
    llms =  [
                {
                    "model_id": os.getenv("LLM_MODEL_NAME"),
                    "display_name": os.getenv("LLM_MODEL_NAME"),
                    "base_url": os.getenv("LLM_BASE_URL"),
                    "description": "Large Language Models for summarization"
                }
            ]
    vlms = [
                {
                    "model_id": os.getenv("VLM_MODEL_NAME"),
                    "display_name": os.getenv("VLM_MODEL_NAME"),
                    "base_url": os.getenv("VLM_BASE_URL"),
                    "description": "Vision and Language Models for summarization"
                }
            ]
    
    return AvailableModelsResponse(
        llms=llms,
        vlms=vlms
    )