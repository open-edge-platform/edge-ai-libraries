# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import traceback
from typing import Annotated

from fastapi import APIRouter, Query, HTTPException, status, Depends
from pydantic.json_schema import SkipJsonSchema

from audio_analyzer.schemas.transcription import (
    ErrorResponse,
    TranscriptionResponse,
    TranscriptionStatus,
    TranscriptionFormData
)
from audio_analyzer.core.audio_extractor import AudioExtractor
from audio_analyzer.core.transcriber import TranscriptionService
from audio_analyzer.utils.file_utils import get_file_duration
from audio_analyzer.utils.validation import RequestValidation
from audio_analyzer.utils.transcription_utils import get_video_path, store_transcript_output
from audio_analyzer.utils.logger import logger

router = APIRouter()


@router.post(
    "/transcriptions",
    response_model=TranscriptionResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "Invalid request body or parameter provided"},
    },
    tags=["Transcription API"],
    summary="Transcribe audio from uploaded video file or a video stored at Minio"
)
async def transcribe_video(
    request: Annotated[TranscriptionFormData, Depends()],
    language: Annotated[
        str | SkipJsonSchema[None], 
        Query(description="_(Optional)_ Language for transcription. If not provided, auto-detection will be used.")
    ] = None
) -> TranscriptionResponse:
    """
    Transcribe speech from a video file.
    
    Upload a video file directly or specify MinIO parameters to transcribe its audio content.
    
    Two ways to provide the video:
    - Upload a video file using form-data
    - Specify MinIO parameters (minio_bucket, video_id, video_name) to retrieve from storage
     
    Args:
        request: Form data containing the file or MinIO parameters and transcription settings
        language: Optional language code for transcription
    
    Returns:
        A response with the transcription status and details
    """
    
    try:
        # Validate the request parameters
        RequestValidation.validate_form_data(request)

        logger.info(f"Received transcription request for {'file upload' if request.file else 'MinIO video'}")
        logger.debug(f"Transcription parameters: model={request.model_name}, device={request.device}, language={language}")
    
        # Get video path either from direct upload or MinIO
        video_path, filename = await get_video_path(request)
        
        # Extract audio from video
        audio_path = await AudioExtractor.extract_audio(video_path)
        logger.debug(f"Audio extracted successfully to: {audio_path}")
        
        # Get file duration
        duration = get_file_duration(video_path)
        logger.debug(f"File duration: {duration} seconds")
        
        logger.info(f"Initializing transcription service with model: {request.model_name}, device: {request.device}")
        transcriber = TranscriptionService(
            model_name=request.model_name,
            device=request.device
        )
        
        # Perform transcription
        job_id, transcript_path = await transcriber.transcribe(
            audio_path,
            language=language,
            include_timestamps=request.include_timestamps,
            video_duration=duration  # Pass the video duration to optimize processing
        )
        
        # Store the transcript output using the configured backend
        output_location = store_transcript_output(
            transcript_path, 
            job_id, 
            filename,
            minio_bucket=request.minio_bucket,
            video_id=request.video_id
        )

        if not output_location:
            raise Exception("Failed to store transcript output.")
        
        logger.info(f"Transcription completed using {transcriber.backend.value} on {transcriber.device_type.value}")
        
        return TranscriptionResponse(
            status=TranscriptionStatus.COMPLETED,
            message="Transcription completed successfully",
            job_id=job_id,
            transcript_path=output_location,
            video_name=filename,
            video_duration=duration
        )
    
    except HTTPException as http_exc:
        raise http_exc
    
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Transcription failed: {str(e)}")
        logger.debug(f"Error details: {error_details}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error_message=f"Transcription failed!",
                details="An error occurred during transcription. Please check logs for details."
            ).model_dump()
        )