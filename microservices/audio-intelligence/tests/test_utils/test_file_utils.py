import os
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock, AsyncMock

import pytest
import aiofiles
from fastapi import UploadFile

from audio_intelligence.utils.file_utils import (
    save_upload_file, 
    get_file_duration, 
    is_video_file
)

@pytest.mark.asyncio
@pytest.mark.unit
async def test_save_upload_file_mkdir_error():
    """Test error handling when directory creation fails"""
    # Mock UploadFile
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "test_video.mp4"
    
    # Mock settings
    mock_settings = MagicMock()
    mock_settings.UPLOAD_DIR = "/tmp/uploads"
    
    # Mock Path.mkdir to raise an exception
    with patch("audio_intelligence.utils.file_utils.settings", mock_settings), \
         patch("pathlib.Path.mkdir", side_effect=PermissionError("Permission denied")):
        
        # Call the function and expect an exception
        with pytest.raises(RuntimeError) as exc_info:
            await save_upload_file(mock_file)
        
        # Verify error message
        assert "Failed to create upload directory" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_save_upload_file_write_error():
    """Test error handling when file writing fails"""
    # Mock UploadFile
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "test_video.mp4"
    mock_file.read = AsyncMock(return_value=b"file content")
    
    # Mock settings
    mock_settings = MagicMock()
    mock_settings.UPLOAD_DIR = "/tmp/uploads"
    
    # Create a patch for aiofiles.open to raise an exception
    with patch("audio_intelligence.utils.file_utils.settings", mock_settings), \
         patch("audio_intelligence.utils.file_utils.aiofiles.open", side_effect=IOError("I/O error")):
        
        # Call the function and expect an exception
        with pytest.raises(RuntimeError) as exc_info:
            await save_upload_file(mock_file)
        
        # Verify error message
        assert "Failed to save uploaded file" in str(exc_info.value)


@pytest.mark.unit
def test_is_video_file_valid():
    """Test detection of valid video file extensions"""
    valid_files = [
        "video.mp4", 
        "movie.avi", 
        "clip.mov", 
        "file.mkv", 
        "video.webm", 
        "sample.flv", 
        "recording.wmv", 
        "film.mpg", 
        "show.mpeg"
    ]
    
    for file_name in valid_files:
        assert is_video_file(file_name) is True


@pytest.mark.unit
def test_is_video_file_invalid():
    """Test rejection of non-video file extensions"""
    invalid_files = [
        "audio.mp3", 
        "document.pdf", 
        "image.jpg", 
        "text.txt", 
        "data.csv", 
        "archive.zip", 
        "script.py"
    ]
    
    for file_name in invalid_files:
        assert is_video_file(file_name) is False


@pytest.mark.unit
def test_is_video_file_case_insensitive():
    """Test that file extension detection is case insensitive"""
    upper_case_files = ["VIDEO.MP4", "MOVIE.AVI", "CLIP.MOV"]
    
    for file_name in upper_case_files:
        assert is_video_file(file_name) is True
