# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter

from audio_intelligence.core.settings import settings
from audio_intelligence.schemas.transcription import AvailableModelsResponse, WhisperModelInfo
from audio_intelligence.utils.logger import logger

router = APIRouter()


@router.get(
    "/models",
    response_model=AvailableModelsResponse,
    tags=["Models API"],
    summary="Get list of models available for use with detailed information",
)
async def get_available_models() -> AvailableModelsResponse:
    """
    Get a list of available Whisper model variants that can be used for transcription.
    
    This endpoint returns all the whisper models that are configured in the service
    and available for transcription requests, along with detailed information including
    display names, descriptions, and the default model that is used when no specific 
    model is requested.
    
    Returns:
        A response with the list of available models with their details and the default model
    """
    logger.debug("Getting available models details")
    
    # Get the list of enabled models from settings with their detailed information
    model_info_list = [model.to_dict() for model in settings.ENABLED_WHISPER_MODELS]
    
    # Convert dictionaries to ModelInfo objects
    models = [WhisperModelInfo(**model_info) for model_info in model_info_list]
    default_model = settings.DEFAULT_WHISPER_MODEL.value
    
    logger.debug(f"Available models: {len(models)} models, default: {default_model}")
    
    return AvailableModelsResponse(
        models=models,
        default_model=default_model
    )