# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import Optional

from fastapi import UploadFile, HTTPException, status
import re

from audio_analyzer.core.settings import settings
from audio_analyzer.schemas.transcription import ErrorResponse, TranscriptionFormData
from audio_analyzer.schemas.types import DeviceType, StorageBackend
from audio_analyzer.utils.file_utils import is_video_file
from audio_analyzer.utils.logger import logger
from audio_analyzer.utils.minio_handler import MinioHandler


class RequestValidation:

    @staticmethod
    def validate_form_data(request: TranscriptionFormData) -> None:
        """
        Validate the transcription request.
        
        Args:
            request: The transcription request parameters
            
        Raises:
            HTTPException: 400 Bad Request - If any validation check fails

        Returns:
            Validated transcription request
        """
        # Validate source based on storage backend setting
        if error := RequestValidation._validate_source_by_backend(request):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error.model_dump()
            )
        
        # Validate file size and format
        if request.file:
            if error := RequestValidation._validate_file_size(request.file):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error.model_dump()
                )
            
            if error := RequestValidation._validate_file_format(request.file):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error.model_dump()
                )
        
        # If MinIO parameters are provided, validate them
        if request.minio_bucket and request.video_name:
            if error := RequestValidation._validate_minio_params(
                request.minio_bucket, request.video_id, request.video_name):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error.model_dump()
                )
        
        if error := RequestValidation._validate_device(request.device):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error.model_dump()
            )
        
        if error := RequestValidation._validate_model(request.model_name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error.model_dump()
            )
        
        return None

    @staticmethod
    def _validate_source_by_backend(request: TranscriptionFormData) -> ErrorResponse | None:
        """
        Validate the source based on the configured storage backend.
        
        Args:
            request: The transcription request parameters
            
        Returns:
            ErrorResponse if validation fails, None if valid
        """
        has_file = request.file is not None
        has_minio = (request.minio_bucket and request.video_id and request.video_name)

        logger.debug(f"Storage Backend: {settings.STORAGE_BACKEND}")
        
        # Check validation based on configured storage backend
        if settings.STORAGE_BACKEND == StorageBackend.FILESYSTEM:
            # When using FILESYSTEM backend, a file must be provided as video source
            if not has_file:
                error_msg = "File upload is required when using filesystem storage backend"
                logger.error(f"Validation failed: {error_msg}")
                return ErrorResponse(
                    error_message="Missing file upload",
                    details="A video file must be uploaded when using filesystem storage backend"
                )
            
            # Warn if MinIO parameters are provided with filesystem backend
            if has_minio:
                logger.warning(f"MinIO parameters will be ignored when using filesystem storage backend")
                
        elif settings.STORAGE_BACKEND == StorageBackend.MINIO:
            # When using MINIO backend, video source must be a Minio Bucket
            if not has_minio:
                error_msg = "MinIO parameters must be provided when using Minio backend"
                logger.error(f"Validation failed: {error_msg}")
                return ErrorResponse(
                    error_message="Missing source parameters",
                    details="Specify MinIO parameters (minio_bucket, video_id, video_name) for fetching the source video"
                )
            
            if has_file:
                logger.warning(f"Ignoring file upload when using MinIO storage backend. Only MinIO parameters will be used.")
        
        return None

    @staticmethod
    def _validate_file_size(file: UploadFile) -> ErrorResponse | None:
        """
        Validate that the uploaded file size is within allowed limits.
        
        Args:
            file: The uploaded file to validate
            
        Returns:
            ErrorResponse if validation fails, None if valid
        """
        if file and file.size > settings.MAX_FILE_SIZE:
            error_msg = f"File too large. Maximum allowed size is {settings.MAX_FILE_SIZE / (1024 * 1024)} MB"
            logger.warning(f"Validation failed: {error_msg}")
            return ErrorResponse(
                error_message="File too large",
                details=f"Maximum allowed size is {settings.MAX_FILE_SIZE / (1024 * 1024)} MB"
            )
        return None

    @staticmethod
    def _validate_file_format(video_file: UploadFile) -> ErrorResponse | None:
        """
        Validate that the uploaded file is a supported video format.
        
        Args:
            video_file: The uploaded video file to validate
            
        Returns:
            ErrorResponse if validation fails, None if valid
        """
        if video_file and not is_video_file(video_file.filename):
            error_msg = f"Invalid file format: {video_file.filename}. Only video files are supported."
            logger.warning(f"Validation failed: {error_msg}")
            return ErrorResponse(
                error_message="Invalid file format",
                details="Only video files are supported"
            )
        return None

    @staticmethod
    def _validate_minio_params(bucket: str, video_id: Optional[str], video_name: str) -> ErrorResponse | None:
        """
        Validate MinIO parameters.
        
        Args:
            bucket: The MinIO bucket name
            video_id: The video ID/prefix in the bucket
            video_name: The video file name
            
        Returns:
            ErrorResponse if validation fails, None if valid
        """
        # Verify bucket name based on bucket naming rules
        if not re.match(r'^[a-z0-9][a-z0-9\-]{1,61}[a-z0-9]$', bucket):
            error_msg = f"Invalid bucket name: {bucket}"
            logger.warning(f"Validation failed: {error_msg}")
            return ErrorResponse(
                error_message="Invalid bucket name",
                details="Bucket name must be 3-63 characters, start and end with a letter or number, "
                        "and contain only lowercase letters, numbers, and hyphens"
            )
        
        # Check if the bucket exists in MinIO
        try:
            if not MinioHandler.ensure_bucket_exists(bucket):
                error_msg = f"Failed to validate bucket: {bucket}"
                logger.warning(f"Validation failed: {error_msg}")
                return ErrorResponse(
                    error_message="Bucket verification failed",
                    details=f"Unable to verify existence of bucket '{bucket}'. Please check with Minio Server."
                )
            logger.debug(f"Bucket '{bucket}' validated successfully")
        except Exception as e:
            error_msg = f"Failed to check bucket existence: {e}"
            logger.warning(f"Validation failed: {error_msg}")
            return ErrorResponse(
                error_message="MinIO connection error",
                details="Failed to validate the bucket existence. Check MinIO connection settings."
            )
        
        # Verify video_id and video_name

        if video_id and not re.match(r'^[a-zA-Z0-9\.\-\_\/]{1,1024}$', video_id):
            error_msg = f"Invalid video_id format: {video_id}"
            logger.warning(f"Validation failed: {error_msg}")
            return ErrorResponse(
                error_message="Invalid video_id format",
                details="video_id can only contain alphanumeric characters, periods, hyphens, underscores, and slashes"
            )
        
        if not is_video_file(video_name):
            error_msg = f"Invalid video file format: {video_name}"
            logger.warning(f"Validation failed: {error_msg}")
            return ErrorResponse(
                error_message="Invalid video file format",
                details="Only video files are supported in MinIO"
            )
        
        return None

    @staticmethod
    def _validate_device(device: Optional[str]) -> ErrorResponse | None:
        """
        Validate that the specified device is supported.
        
        Args:
            device: The device to use for transcription
            
        Returns:
            ErrorResponse if validation fails, None if valid
        """
        if device and device.strip():
            available_devices = [e.value for e in DeviceType]
            if device.lower() not in available_devices:
                error_msg = f"Invalid device: {device}. Must be one of: {', '.join(available_devices)}"
                logger.warning(f"Validation failed: {error_msg}")
                return ErrorResponse(
                    error_message="Invalid device",
                    details=f"Device must be one of: {', '.join(available_devices)}"
                )
        return None


    @staticmethod
    def _validate_model(model: Optional[str]) -> ErrorResponse | None:
        """
        Validate that the specified model is enabled in the configuration.
        
        Args:
            model: The model name to validate
            
        Returns:
            ErrorResponse if validation fails, None if valid
        """

        if model and model.strip():
            # Check if the model is in the list of enabled models
            available_models = [m.value for m in settings.ENABLED_WHISPER_MODELS]
            if model.lower() not in available_models:
                error_msg = f"Invalid model: {model}. Must be one of: {', '.join(available_models)}"
                logger.warning(f"Validation failed: {error_msg}")
                return ErrorResponse(
                    error_message="Invalid model",
                    details=f"Model must be one of: {', '.join(available_models)}"
                )
            
        return None