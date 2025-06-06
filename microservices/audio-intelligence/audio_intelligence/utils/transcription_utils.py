import os
import traceback
from pathlib import Path
from typing import Optional, Tuple

from fastapi import HTTPException, status

from audio_intelligence.core.settings import settings
from audio_intelligence.schemas.transcription import ErrorResponse, TranscriptionFormData
from audio_intelligence.utils.file_utils import save_upload_file
from audio_intelligence.utils.minio_handler import MinioHandler
from audio_intelligence.utils.logger import logger
from audio_intelligence.schemas.types import StorageBackend

async def get_video_path(request: TranscriptionFormData) -> Tuple[Path, str]:
    """
    Get the video path from either direct upload or MinIO storage.
    
    Args:
        request: The transcription request containing either file upload or MinIO parameters
        
    Returns:
        Tuple[Path, str]: Path to the video file and the filename
    """
    if settings.STORAGE_BACKEND == StorageBackend.FILESYSTEM and request.file:
        logger.debug(f"Handling direct file upload: {request.file.filename}")
        video_path = await save_upload_file(request.file)
        filename = request.file.filename
        logger.debug(f"File {filename} saved successfully at: {video_path}")
        return video_path, filename
    
    elif settings.STORAGE_BACKEND == StorageBackend.MINIO:
        logger.debug(f"Retrieving video from MinIO - bucket: {request.minio_bucket}, "
                     f"video_id: {request.video_id}, name: {request.video_name}")
        
        video_path, error = await MinioHandler.get_video_from_minio(
            request.minio_bucket,
            request.video_id,
            request.video_name
        )
        
        if error or not video_path:
            logger.error(f"Failed to retrieve video from MinIO: {error}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponse(
                    error_message="Source video not found.",
                    details=f"Video with ID '{request.video_id}' and name '{request.video_name}' not found in bucket '{request.minio_bucket}'",
                ).model_dump()
            )
        
        logger.debug(f"Video retrieved successfully from MinIO: {video_path}")
        return video_path, request.video_name
    
    else:
        logger.error("Unsupported storage backend configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error_message="Unsupported storage backend",
                details="The configured storage backend is not supported for video retrieval"
            ).model_dump()
        )


def store_transcript_output(
    transcript_path: Path, 
    job_id: str, 
    original_filename: str,
    minio_bucket: Optional[str] = None,
    video_id: Optional[str] = None
) -> str | None:
    """
    Store the transcript output using the configured storage backend (filesystem or MinIO).
    
    Args:
        transcript_path: Path to the local transcript file
        job_id: Unique job identifier
        original_filename: Original video filename
        minio_bucket: MinIO bucket to store the transcript in (if using MinIO backend)
        video_id: Video ID/prefix to use in the object name
        
    Returns:
        str | None: Path or location where the transcript is stored or None if failed
    """
    
    if settings.STORAGE_BACKEND == StorageBackend.MINIO:
        logger.debug("Using MinIO storage backend for transcript output")
        
        if not minio_bucket or not video_id:
            logger.error("MinIO bucket or video ID not provided for transcript storage")
            raise ValueError("MinIO bucket and video ID must be provided for MinIO storage")

        # Get the original filename's primary name and extension
        file_stem = Path(original_filename).stem
        extension = transcript_path.suffix
        
        # Create the object name for MinIO
        object_name = f"{video_id}/{file_stem}{extension}"
        
        success, error = MinioHandler.save_transcript_to_minio(
            transcript_path,
            minio_bucket,
            object_name
        )
        
        if not success:
            logger.error(f"Failed to store transcript in MinIO: {error}")
            return None
        
        # MinIO object location
        location = f"minio://{minio_bucket}/{object_name}"
        logger.debug(f"Transcript stored in MinIO at: {location}")
        return location
    else:
        # Using filesystem backend
        logger.debug(f"Using filesystem storage backend, transcript at: {transcript_path}")
        return str(transcript_path)