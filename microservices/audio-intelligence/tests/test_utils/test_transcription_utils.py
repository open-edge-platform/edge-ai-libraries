# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi import HTTPException, UploadFile

from audio_intelligence.schemas.transcription import TranscriptionFormData
from audio_intelligence.schemas.types import StorageBackend
from audio_intelligence.utils.transcription_utils import get_video_path, store_transcript_output


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_video_path_filesystem():
    """Test getting video path with filesystem storage and file upload"""
    # Create mock request with file upload
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "test_video.mp4"
    
    request = TranscriptionFormData()
    request.file = mock_file
    
    # Mock settings and save_upload_file
    mock_settings = MagicMock()
    mock_settings.STORAGE_BACKEND = StorageBackend.FILESYSTEM
    
    upload_path = Path("/tmp/uploads/test_video.mp4")
    mock_save_upload = AsyncMock(return_value=upload_path)
    
    with patch("audio_intelligence.utils.transcription_utils.settings", mock_settings), \
         patch("audio_intelligence.utils.transcription_utils.save_upload_file", mock_save_upload):
        
        # Call the function
        video_path, filename = await get_video_path(request)
        
        # Check results
        assert video_path == upload_path
        assert filename == "test_video.mp4"
        
        # Verify interactions
        mock_save_upload.assert_called_once_with(mock_file)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_video_path_minio():
    """Test getting video path with MinIO storage"""
    # Create mock request with MinIO parameters
    request = TranscriptionFormData()
    request.file = None
    request.minio_bucket = "videos"
    request.video_id = "test-id"
    request.video_name = "test_video.mp4"
    
    # Mock settings and MinioHandler.get_video_from_minio
    mock_settings = MagicMock()
    mock_settings.STORAGE_BACKEND = StorageBackend.MINIO
    
    video_path = Path("/tmp/downloads/test_video.mp4")
    mock_get_video = AsyncMock(return_value=(video_path, None))
    
    with patch("audio_intelligence.utils.transcription_utils.settings", mock_settings), \
         patch("audio_intelligence.utils.transcription_utils.MinioHandler.get_video_from_minio", mock_get_video):
        
        # Call the function
        result_path, filename = await get_video_path(request)
        
        # Check results
        assert result_path == video_path
        assert filename == "test_video.mp4"
        
        # Verify interactions
        mock_get_video.assert_called_once_with(
            "videos",
            "test-id",
            "test_video.mp4"
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_video_path_minio_error():
    """Test error handling when MinIO video retrieval fails"""
    # Create mock request with MinIO parameters
    request = TranscriptionFormData()
    request.file = None
    request.minio_bucket = "videos"
    request.video_id = "test-id"
    request.video_name = "test_video.mp4"
    
    # Mock settings and MinioHandler.get_video_from_minio with error
    mock_settings = MagicMock()
    mock_settings.STORAGE_BACKEND = StorageBackend.MINIO
    
    mock_get_video = AsyncMock(return_value=(None, "MinIO error"))
    
    with patch("audio_intelligence.utils.transcription_utils.settings", mock_settings), \
         patch("audio_intelligence.utils.transcription_utils.MinioHandler.get_video_from_minio", mock_get_video):
        
        # Call the function and expect exception
        with pytest.raises(HTTPException) as excinfo:
            await get_video_path(request)
        
        # Check exception details
        assert excinfo.value.status_code == 404
        assert "Source video not found" in excinfo.value.detail["error_message"]
        
        # Verify interactions
        mock_get_video.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_video_path_unsupported_backend():
    """Test error when unsupported storage backend is configured"""
    # Create mock request
    request = TranscriptionFormData()
    
    # Mock settings with unsupported backend
    mock_settings = MagicMock()
    mock_settings.STORAGE_BACKEND = "unsupported"
    
    with patch("audio_intelligence.utils.transcription_utils.settings", mock_settings):
        # Call the function and expect exception
        with pytest.raises(HTTPException) as excinfo:
            await get_video_path(request)
        
        # Check exception details
        assert excinfo.value.status_code == 500
        assert "Unsupported storage backend" in excinfo.value.detail["error_message"]


@pytest.mark.unit
def test_store_transcript_output_filesystem():
    """Test storing transcript with filesystem backend"""
    # Mock settings
    mock_settings = MagicMock()
    mock_settings.STORAGE_BACKEND = StorageBackend.FILESYSTEM
    
    # Prepare parameters
    transcript_path = Path("/tmp/output/transcript-123.srt")
    job_id = "123"
    original_filename = "video.mp4"
    
    with patch("audio_intelligence.utils.transcription_utils.settings", mock_settings):
        # Call the function
        result = store_transcript_output(
            transcript_path, job_id, original_filename
        )
        
        # Check result
        assert result == str(transcript_path)


@pytest.mark.unit
def test_store_transcript_output_minio_missing_params():
    """Test error when MinIO parameters are missing"""
    # Mock settings
    mock_settings = MagicMock()
    mock_settings.STORAGE_BACKEND = StorageBackend.MINIO
    
    # Prepare parameters - missing bucket and video_id
    transcript_path = Path("/tmp/output/transcript-123.srt")
    job_id = "123"
    original_filename = "video.mp4"
    
    with patch("audio_intelligence.utils.transcription_utils.settings", mock_settings):
        # Call the function and expect exception
        with pytest.raises(ValueError) as excinfo:
            store_transcript_output(transcript_path, job_id, original_filename)
        
        # Check error message
        assert "MinIO bucket and video ID must be provided" in str(excinfo.value)


@pytest.mark.unit
def test_store_transcript_output_different_extensions():
    """Test storing transcript with different file extensions"""
    # Test with SRT file
    mock_settings = MagicMock()
    mock_settings.STORAGE_BACKEND = StorageBackend.MINIO
    
    srt_path = Path("/tmp/output/transcript-123.srt")
    txt_path = Path("/tmp/output/transcript-123.txt")
    job_id = "123"
    original_filename = "video.mp4"
    minio_bucket = "transcripts"
    video_id = "test-id"
    
    # Mock MinioHandler.save_transcript_to_minio
    mock_save = MagicMock(return_value=(True, None))
    
    with patch("audio_intelligence.utils.transcription_utils.settings", mock_settings), \
         patch("audio_intelligence.utils.transcription_utils.MinioHandler.save_transcript_to_minio", mock_save):
        
        # Test with SRT file
        store_transcript_output(srt_path, job_id, original_filename, minio_bucket, video_id)
        assert mock_save.call_args[0][0] == srt_path
        assert ".srt" in mock_save.call_args[0][2]
        
        # Test with TXT file
        mock_save.reset_mock()
        store_transcript_output(txt_path, job_id, original_filename, minio_bucket, video_id)
        assert mock_save.call_args[0][0] == txt_path
        assert ".txt" in mock_save.call_args[0][2]
