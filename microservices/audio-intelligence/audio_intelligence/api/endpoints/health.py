# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter

from audio_intelligence.schemas.transcription import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["Health API"], summary="Health status of API")
async def health_check() -> HealthResponse:
    """
    Health check endpoint.
    
    Returns:
        A response indicating the service status, version and a descriptive message.
    """
    return HealthResponse()