from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi import HTTPException
from moviepy import VideoFileClip, AudioFileClip

from audio_intelligence.core.audio_extractor import AudioExtractor


@pytest.mark.asyncio
@pytest.mark.unit
async def test_extract_audio_success(
    mock_video_file, 
    mock_audio_file, 
    mock_settings
):
    """Test successful audio extraction from video file"""
    
    # Mock VideoFileClip context manager behavior
    mock_video_clip = MagicMock(spec=VideoFileClip)
    mock_video_clip.__enter__.return_value = mock_video_clip
    mock_video_clip.__exit__.return_value = None
    
    # Set up the audio mock
    mock_audio = MagicMock()
    mock_audio.write_audiofile = MagicMock()
    mock_video_clip.audio = mock_audio
    
    # Mock Setup for AudioFileClip context manager
    mock_audio_clip = MagicMock(spec=AudioFileClip)
    mock_audio_clip.__enter__.return_value = mock_audio_clip
    mock_audio_clip.__exit__.return_value = None
    mock_audio_clip.fps = 16000
    mock_audio_clip.nchannels = 1
    
    with patch("audio_intelligence.core.audio_extractor.VideoFileClip", return_value=mock_video_clip) as mock_video_instance, \
         patch("audio_intelligence.core.audio_extractor.AudioFileClip", return_value=mock_audio_clip) as mock_audio_instance, \
         patch("audio_intelligence.core.audio_extractor.settings", mock_settings):
        
        # Call the function
        result = await AudioExtractor.extract_audio(mock_video_file)
        
        # Check results
        assert result == mock_audio_file
        
        mock_video_instance.assert_called_once_with(str(mock_video_file))
        mock_audio.write_audiofile.assert_called_once_with(
            str(mock_audio_file),
            fps=mock_settings.AUDIO_FORMAT_PARAMS["fps"],
            nbytes=mock_settings.AUDIO_FORMAT_PARAMS["nbytes"],
            codec='pcm_s16le',
            ffmpeg_params=["-ac", str(mock_settings.AUDIO_FORMAT_PARAMS["nchannels"])],
            logger=None
        )
        mock_audio_instance.assert_called_once_with(str(mock_audio_file))
        mock_video_clip.__exit__.assert_called_once()
        mock_audio_clip.__exit__.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_extract_audio_nonexisting_custom_output_path(mock_settings, temp_test_dir):
    """Test audio extraction with custom output path which does not exist"""

    # Create custom mock paths 
    video_path = temp_test_dir / "test_video.mp4"
    custom_output_path = temp_test_dir / "custom_output.wav" # Does not exist
    
    # Mock VideoFileClip context manager behavior
    mock_video_clip = MagicMock(spec=VideoFileClip)
    mock_video_clip.__enter__.return_value = mock_video_clip
    mock_video_clip.__exit__.return_value = None

    # Setup mocking for VideoFileClip's audio attribute
    mock_audio = MagicMock()
    mock_audio.write_audiofile = MagicMock()
    mock_video_clip.audio = mock_audio
    
    # Mock AudioFileClip context manager
    mock_audio_clip = MagicMock(spec=AudioFileClip)
    mock_audio_clip.__enter__.return_value = mock_audio_clip
    mock_audio_clip.__exit__.return_value = None
    
    with patch("audio_intelligence.core.audio_extractor.VideoFileClip", return_value=mock_video_clip) as mock_video_instance, \
         patch("audio_intelligence.core.audio_extractor.AudioFileClip", return_value=mock_audio_clip) as mock_audio_instance, \
         patch("audio_intelligence.core.audio_extractor.settings", mock_settings):
        
        # Call the function with custom output path
        result = await AudioExtractor.extract_audio(video_path, custom_output_path)
        
        # Check results
        assert result == custom_output_path
        
        mock_video_instance.assert_called_once_with(str(video_path))
        mock_audio.write_audiofile.assert_called_once_with(
            str(custom_output_path),
            fps=mock_settings.AUDIO_FORMAT_PARAMS["fps"],
            nbytes=mock_settings.AUDIO_FORMAT_PARAMS["nbytes"],
            codec='pcm_s16le',
            ffmpeg_params=["-ac", str(mock_settings.AUDIO_FORMAT_PARAMS["nchannels"])],
            logger=None
        )
        mock_audio_instance.assert_not_called()
        mock_video_clip.__exit__.assert_called_once()
        mock_audio_clip.__exit__.assert_not_called()



@pytest.mark.asyncio
@pytest.mark.unit
async def test_extract_audio_custom_output_path(temp_test_dir, mock_settings):
    """Test successful audio extraction using a custom output path which exists"""

    # Create custom mock paths 
    video_path = temp_test_dir / "test_video.mp4"
    custom_output_path = temp_test_dir / "custom_output.wav"
    
    # Mock VideoFileClip context manager behavior
    mock_video_clip = MagicMock(spec=VideoFileClip)
    mock_video_clip.__enter__.return_value = mock_video_clip
    mock_video_clip.__exit__.return_value = None
    
    # Set up the audio mock
    mock_audio = MagicMock()
    mock_audio.write_audiofile = MagicMock()
    mock_video_clip.audio = mock_audio
    
    # Mock Setup for AudioFileClip context manager
    mock_audio_clip = MagicMock(spec=AudioFileClip)
    mock_audio_clip.__enter__.return_value = mock_audio_clip
    mock_audio_clip.__exit__.return_value = None
    mock_audio_clip.fps = 16000
    mock_audio_clip.nchannels = 1
    
    with patch("audio_intelligence.core.audio_extractor.VideoFileClip", return_value=mock_video_clip) as mock_video_instance, \
         patch("audio_intelligence.core.audio_extractor.AudioFileClip", return_value=mock_audio_clip) as mock_audio_instance, \
         patch("audio_intelligence.core.audio_extractor.Path.exists", return_value=True), \
         patch("audio_intelligence.core.audio_extractor.settings", mock_settings):
        
        # Call the function with custom output path
        result = await AudioExtractor.extract_audio(video_path, custom_output_path)
        
        # Check results
        assert result == custom_output_path
        
        mock_video_instance.assert_called_once_with(str(video_path))
        mock_audio.write_audiofile.assert_called_once_with(
            str(custom_output_path),
            fps=mock_settings.AUDIO_FORMAT_PARAMS["fps"],
            nbytes=mock_settings.AUDIO_FORMAT_PARAMS["nbytes"],
            codec='pcm_s16le',
            ffmpeg_params=["-ac", str(mock_settings.AUDIO_FORMAT_PARAMS["nchannels"])],
            logger=None
        )
        mock_audio_instance.assert_called_once_with(str(custom_output_path))
        mock_video_clip.__exit__.assert_called_once()
        mock_audio_clip.__exit__.assert_called_once()



@pytest.mark.asyncio
@pytest.mark.unit
async def test_extract_audio_no_audio_stream(mock_video_file, mock_settings):
    """Test audio extraction when video has no audio stream"""
    
    # Mock VideoFileClip context manager with no audio
    mock_video = MagicMock(spec=VideoFileClip)
    mock_video.__enter__.return_value = mock_video
    mock_video.__exit__.return_value = None
    mock_video.audio = None
    
    with patch("audio_intelligence.core.audio_extractor.VideoFileClip", return_value=mock_video) as mock_video_clip, \
         patch("audio_intelligence.core.audio_extractor.settings", mock_settings):
        
        # Call the function and expect an exception
        with pytest.raises(HTTPException) as exc_info:
            await AudioExtractor.extract_audio(mock_video_file)
        
        # Verify error details
        assert exc_info.value.status_code == 400
        assert "No audio stream found" in exc_info.value.detail["error_message"]
        
        mock_video_clip.assert_called_once_with(str(mock_video_file))
        # Assert VideoFileClip context caused exception before exiting
        mock_video_clip.__exit__.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_extract_audio_moviepy_error(mock_video_file):
    """Test audio extraction when MoviePy raises an error"""
    
    # Mock VideoFileClip to raise an exception
    with patch("audio_intelligence.core.audio_extractor.VideoFileClip", side_effect=Exception("MoviePy error")) as mock_video_clip:
        # Call the function and expect an exception
        with pytest.raises(RuntimeError) as exc_info:
            await AudioExtractor.extract_audio(mock_video_file)
        
        # Verify error message
        assert "Failed to extract audio from video" in str(exc_info.value)
        
        # Verify interactions
        mock_video_clip.assert_called_once_with(str(mock_video_file))
