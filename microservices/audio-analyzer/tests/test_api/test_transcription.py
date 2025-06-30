# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from audio_analyzer.schemas.types import StorageBackend, TranscriptionStatus


@pytest.mark.api
@pytest.mark.asyncio
@patch("audio_analyzer.utils.validation.settings")
@patch("audio_analyzer.api.endpoints.transcription.get_video_path")
@patch("audio_analyzer.api.endpoints.transcription.AudioExtractor.extract_audio")
@patch("audio_analyzer.api.endpoints.transcription.get_file_duration")
@patch("audio_analyzer.api.endpoints.transcription.store_transcript_output")
async def test_transcription_endpoint_with_file_upload(
    mock_store_transcript, 
    mock_get_duration, 
    mock_extract_audio, 
    mock_get_video_path,
    mock_validator,
    test_client: TestClient,
    mock_transcriber,
    mock_upload_file, 
    mock_settings,
    mock_audio_file,
    mock_video_file
):
    """Test the transcription endpoint with file upload"""
    
    transcript_path = mock_settings.OUTPUT_DIR / f"{mock_video_file.stem}.srt"
    
    # Set up mock return values
    mock_store_transcript.return_value = str(transcript_path)
    mock_get_video_path.return_value = await AsyncMock(return_value=(mock_video_file, mock_video_file.name))()
    mock_extract_audio.return_value = await AsyncMock(return_value=mock_audio_file)()
    mock_get_duration.return_value = 59
    
    # Set up mock transcription service
    # mock_transcriber_instance = MagicMock()
    # mock_transcription_service.return_value = mock_transcriber_instance
    # mock_transcriber_instance.transcribe.return_value = AsyncMock(return_value=("test-job-id", transcript_path))()

    
    # Configure storage backend to filesystem
    mock_validator.STORAGE_BACKEND = StorageBackend.FILESYSTEM
    mock_validator.ENABLED_WHISPER_MODELS = mock_settings.ENABLED_WHISPER_MODELS
    mock_validator.MAX_FILE_SIZE = mock_settings.MAX_FILE_SIZE
    
    # Prepare form data for file upload
    form_data = {
        "model_name": "tiny.en",
        "device": "cpu",
        "include_timestamps": "true"
    }
    
    # Use await for the async read method
    file_content = await mock_upload_file.read()
    files = {"file": (mock_upload_file.filename, file_content, mock_upload_file.content_type)}
    
    # Make request to transcription endpoint
    response = test_client.post(
        "/api/v1/transcriptions", 
        data=form_data,
        files=files
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify the response structure and content
    assert data["status"] == TranscriptionStatus.COMPLETED
    assert data["job_id"] == "test-job-id"
    assert data["transcript_path"] == str(transcript_path)
    assert data["video_name"] == "test_video.mp4"
    assert data["video_duration"] == 59
    
    # Verify the mocks were called with expected parameters
    mock_get_video_path.assert_called_once()
    mock_extract_audio.assert_called_once_with(mock_video_file)
    mock_get_duration.assert_called_once_with(mock_video_file)
    mock_transcriber.transcribe.assert_called_once()
    mock_store_transcript.assert_called_once_with(
        transcript_path,
        "test-job-id",
        mock_video_file.name,
        minio_bucket="",
        video_id=""
    )


@pytest.mark.api
@pytest.mark.asyncio
@patch("audio_analyzer.utils.validation.MinioHandler.ensure_bucket_exists")
@patch("audio_analyzer.utils.validation.settings")
@patch("audio_analyzer.api.endpoints.transcription.get_video_path")
@patch("audio_analyzer.api.endpoints.transcription.AudioExtractor.extract_audio")
@patch("audio_analyzer.api.endpoints.transcription.get_file_duration")
@patch("audio_analyzer.api.endpoints.transcription.store_transcript_output")
async def test_transcription_endpoint_with_minio(
    mock_store_transcript, 
    mock_get_duration, 
    mock_extract_audio, 
    mock_get_video_path,
    mock_validator,
    mock_bucket_validation,
    test_client: TestClient,
    mock_transcriber,
    mock_settings,
    mock_video_file,
    mock_audio_file
):
    """Test the transcription endpoint with MinIO source"""
    # Configure mocks
    # video_path = temp_test_dir / "test_video.mp4"
    # audio_path = temp_test_dir / "test_audio.wav"
    # transcript_path = temp_test_dir / "output" / "test_transcript.srt"
    output_file_name = f"{mock_video_file.stem}.srt"
    minio_bucket = "test-bucket"
    minio_video_id = "test-video-id"

    transcript_path = mock_settings.OUTPUT_DIR / output_file_name
    minio_location = f"minio://{minio_bucket}/{minio_video_id}/{output_file_name}"
    
    # Set up mock return values
    mock_bucket_validation.return_value = True
    mock_store_transcript.return_value = minio_location
    mock_get_video_path.return_value = await AsyncMock(return_value=(mock_video_file, mock_video_file.name))()
    mock_extract_audio.return_value = await AsyncMock(return_value=mock_audio_file)()
    mock_get_duration.return_value = 59
    
    # Set up mock transcription service
    # mock_transcriber_instance = MagicMock()
    # mock_transcription_service.return_value = mock_transcriber_instance
    # mock_transcriber_instance.transcribe.return_value = AsyncMock(return_value=("test-job-id", transcript_path))()

    
    # Configure storage backend to MinIO
    mock_validator.STORAGE_BACKEND = StorageBackend.MINIO
    mock_validator.ENABLED_WHISPER_MODELS = mock_settings.ENABLED_WHISPER_MODELS
    
    # Prepare form data for MinIO source
    form_data = {
        "minio_bucket": minio_bucket,
        "video_id": minio_video_id,
        "video_name": mock_video_file.name,
        "model_name": "tiny.en",
        "device": "cpu",
        "include_timestamps": "true"
    }
    
    # Make request to transcription endpoint
    response = test_client.post(
        "/api/v1/transcriptions",
        data=form_data
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify the response structure and content
    assert data["status"] == TranscriptionStatus.COMPLETED
    assert data["job_id"] == "test-job-id"
    assert data["transcript_path"] == minio_location
    assert data["video_name"] == mock_video_file.name
    assert data["video_duration"] == 59
    
    # Verify the mocks were called with expected parameters
    mock_bucket_validation.assert_called_once()
    mock_get_video_path.assert_called_once()
    mock_extract_audio.assert_called_once_with(mock_video_file)
    mock_get_duration.assert_called_once_with(mock_video_file)
    mock_transcriber.transcribe.assert_called_once()
    mock_store_transcript.assert_called_once_with(
        transcript_path, 
        "test-job-id", 
        mock_video_file.name,
        minio_bucket=minio_bucket,
        video_id=minio_video_id
    )


@pytest.mark.api
@patch("audio_analyzer.utils.validation.settings")
def test_transcription_endpoint_validation_error(mock_validator, test_client):
    """Test the transcription endpoint with invalid request parameters"""
    # Configure storage backend to filesystem which requires a file upload
    mock_validator.STORAGE_BACKEND = StorageBackend.FILESYSTEM
    
    # Attempt to make request without required file
    form_data = {
        "model_name": "tiny.en",
        "device": "cpu",
    }
    
    response = test_client.post("/api/v1/transcriptions", data=form_data)
    
    # Assert response indicates a validation error
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "error_message" in data["detail"]
    assert "Missing file upload" in data["detail"]["error_message"]
