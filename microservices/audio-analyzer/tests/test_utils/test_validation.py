# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from audio_analyzer.schemas.transcription import TranscriptionFormData, ErrorResponse
from audio_analyzer.schemas.types import StorageBackend
from audio_analyzer.utils.validation import RequestValidation


@pytest.mark.unit
def test_validate_form_data_with_file_and_filesystem(mock_upload_file, mock_settings):
    """Test validating form data with file upload and filesystem storage"""
    
    # Create a valid request with file upload
    request = TranscriptionFormData()
    request.file = mock_upload_file
    request.model_name = "tiny.en"
    request.device = "cpu"
    
    with patch("audio_analyzer.utils.validation.settings", mock_settings):    
        # Should not raise an exception
        result = RequestValidation.validate_form_data(request)
    
    assert result is None



@pytest.mark.unit
def test_validate_form_data_with_minio_and_minio_backend(mock_settings, mocker):
    """Test validating form data with MinIO parameters and MinIO storage"""
    
    # Set storage backend to MinIO
    mocker.patch("audio_analyzer.utils.validation.settings.STORAGE_BACKEND", StorageBackend.MINIO)

    # Create a valid request with MinIO parameters
    request = TranscriptionFormData()

    request.file = None
    request.minio_bucket = "videos"
    request.video_id = "test-id"
    request.video_name = "test_video.mp4"
    request.model_name = "tiny.en"
    request.device = "cpu"
    
    # Mock MinIO handler to validate bucket existence
    with patch("audio_analyzer.utils.validation.MinioHandler") as mock_minio_handler:
        mock_minio_handler.ensure_bucket_exists.return_value = True
        
        # Should not raise an exception
        result = RequestValidation.validate_form_data(request)
        assert result is None


@pytest.mark.unit
def test_validate_form_data_without_file_and_filesystem(mock_settings):
    """Test validating form data without file upload using filesystem storage"""

    # Create an invalid request without file upload
    request = TranscriptionFormData()
    request.file = None
    request.model_name = "tiny.en"
    request.device = "cpu"
    
    with patch("audio_analyzer.utils.validation.settings", mock_settings):   
        # Should raise an exception
        with pytest.raises(HTTPException) as ex:
            RequestValidation.validate_form_data(request)
    
    # Check the exception details
    assert ex.value.status_code == 400
    assert "Missing file upload" in ex.value.detail["error_message"]


@pytest.mark.unit
def test_validate_form_data_without_minio_params_and_minio_backend(mock_settings, mocker):
    """Test validating form data without MinIO parameters using MinIO storage"""

    # Set storage backend to MinIO
    mocker.patch("audio_analyzer.utils.validation.settings.STORAGE_BACKEND", StorageBackend.MINIO)
    
    # Create an invalid request without MinIO parameters
    request = TranscriptionFormData()
    request.file = None
    request.minio_bucket = ""
    request.video_id = ""
    request.video_name = ""
    request.model_name = "tiny.en"
    request.device = "cpu"
    
    # Should raise an exception
    with pytest.raises(HTTPException) as ex:
        RequestValidation.validate_form_data(request)
    
    # Check the exception details
    assert ex.value.status_code == 400
    assert "Missing source parameters" in ex.value.detail["error_message"]


@pytest.mark.unit
@patch("audio_analyzer.utils.validation.settings")
def test_validate_file_size(validation_settings, mock_settings):
    """Test validating file size"""
    
    # Set settings object in validation to use mock settings
    validation_settings.MAX_FILE_SIZE = mock_settings.MAX_FILE_SIZE
    
    # Create a mock file that's too large
    mock_file = MagicMock()
    mock_file.size = 20 * 1024 * 1024   # 20MB
     
    # Should return an error response
    error = RequestValidation._validate_file_size(mock_file)

    assert isinstance(error, ErrorResponse)
    assert "File too large" in error.error_message
    
    # Create a mock file that's within size limits
    mock_file.size = 500  # 500 bytes
    
    # Should return None (no error)
    error = RequestValidation._validate_file_size(mock_file)
    assert error is None


@pytest.mark.unit
def test_validate_file_format():
    """Test validating file format"""
    # Create a mock file with valid format
    mock_file = MagicMock()
    mock_file.filename = "test_video.mp4"
    
    # Should return None (no error)
    error = RequestValidation._validate_file_format(mock_file)
    assert error is None
    
    # Create a mock file with invalid format
    mock_file.filename = "test_audio.mp3"
    
    # Should return an error response
    error = RequestValidation._validate_file_format(mock_file)
    assert isinstance(error, ErrorResponse)
    assert "Invalid file format" in error.error_message


@pytest.mark.unit
def test_validate_minio_params():
    """Test validating MinIO parameters"""
    # Valid parameters
    with patch("audio_analyzer.utils.validation.MinioHandler") as mock_minio_handler:
        mock_minio_handler.ensure_bucket_exists.return_value = True
        
        error = RequestValidation._validate_minio_params(
            "valid-bucket", 
            "valid-id", 
            "video.mp4"
        )
        assert error is None
    
    # Invalid bucket name
    error = RequestValidation._validate_minio_params(
        "Invalid Bucket Name", 
        "valid-id", 
        "video.mp4"
    )
    assert isinstance(error, ErrorResponse)
    assert "Invalid bucket name" in error.error_message

    with patch("audio_analyzer.utils.validation.MinioHandler") as mock_minio_handler:
        mock_minio_handler.ensure_bucket_exists.return_value = True
        # Invalid video name
        error = RequestValidation._validate_minio_params(
            "valid-bucket", 
            "valid-id", 
            "document.pdf"
        )
        assert isinstance(error, ErrorResponse)
        assert "Invalid video file format" in error.error_message


@pytest.mark.unit
def test_validate_device():
    """Test validating device type"""
    # Valid device types
    assert RequestValidation._validate_device("cpu") is None
    assert RequestValidation._validate_device("auto") is None
    
    # Invalid device type
    error = RequestValidation._validate_device("invalid_device")
    assert isinstance(error, ErrorResponse)
    assert "Invalid device" in error.error_message


@pytest.mark.unit
def test_validate_model(mock_settings):
    """Test validating model name"""
    # Configure enabled models
    from audio_analyzer.schemas.types import WhisperModel
    mock_settings.ENABLED_WHISPER_MODELS = [WhisperModel.TINY_EN, WhisperModel.SMALL_EN]
    
    with patch("audio_analyzer.utils.validation.settings") as mock_settings:
        # Configure enabled models
        from audio_analyzer.schemas.types import WhisperModel
        mock_settings.ENABLED_WHISPER_MODELS = [WhisperModel.TINY_EN, WhisperModel.SMALL_EN]
        
        # Valid model name
        assert RequestValidation._validate_model("tiny.en") is None
        
        # Invalid model name
        error = RequestValidation._validate_model("large")
        assert isinstance(error, ErrorResponse)
        assert "Invalid model" in error.error_message
