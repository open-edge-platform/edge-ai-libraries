import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient

from audio_intelligence.main import app
from audio_intelligence.schemas.types import DeviceType, StorageBackend, WhisperModel


@pytest.fixture
def test_client():
    """Fixture for creating a FastAPI TestClient"""

    return TestClient(app)


@pytest.fixture
def temp_test_dir():
    """Fixture to create a temporary directory for test files"""

    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def mock_settings(temp_test_dir):
    """Fixture to provide mocked settings with test values"""

    with patch("audio_intelligence.core.settings.settings") as mock_settings:
        mock_settings.MAX_FILE_SIZE = 1024 * 1024 * 10 
        mock_settings.DEBUG = True
        mock_settings.STORAGE_BACKEND = StorageBackend.FILESYSTEM
        mock_settings.DEFAULT_WHISPER_MODEL = WhisperModel.TINY_EN
        mock_settings.ENABLED_WHISPER_MODELS = [WhisperModel.TINY_EN, WhisperModel.BASE_EN]
        mock_settings.DEFAULT_DEVICE = DeviceType.CPU
        mock_settings.USE_FP16 = True
        
        # Create a computed_field property
        mock_settings.AUDIO_FORMAT_PARAMS = {
            "fps": 16000,
            "nbytes": 2,
            "nchannels": 1,
        }
        
        # Create temporary test directories for several paths required in application
        mock_settings.UPLOAD_DIR = temp_test_dir / "uploads"
        mock_settings.AUDIO_DIR = temp_test_dir / "audio"
        mock_settings.OUTPUT_DIR = temp_test_dir / "output"
        mock_settings.GGML_MODEL_DIR = temp_test_dir / "models" / "ggml"
        mock_settings.OPENVINO_MODEL_DIR = temp_test_dir / "models" / "openvino"
        
        for dir_path in [mock_settings.UPLOAD_DIR, mock_settings.AUDIO_DIR, 
                        mock_settings.OUTPUT_DIR, mock_settings.GGML_MODEL_DIR,
                        mock_settings.OPENVINO_MODEL_DIR]:
            dir_path.mkdir(parents=True, exist_ok=True)
            
        yield mock_settings


@pytest.fixture
def mock_audio_file(mock_settings):
    """Fixture to create a mock audio file for testing"""

    # Create a sample WAV file 
    audio_path = mock_settings.AUDIO_DIR / "test_video.wav"
    with open(audio_path, 'wb') as f:
        # Basic WAV header (44 bytes) and some empty audio data
        f.write(b'RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00')
        f.write(b'\x00' * 1000) 
    
    yield audio_path


@pytest.fixture
def mock_video_file(temp_test_dir):
    """Fixture to create a mock video file for testing"""

    # Create a sample MP4 file
    video_path = temp_test_dir / "test_video.mp4"
    with open(video_path, 'wb') as f:
        # Basic MP4 header and add some empty data
        f.write(b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42mp41\x00\x00\x00\x00')
        f.write(b'\x00' * 1000) 
    
    yield video_path


@pytest.fixture
def mock_upload_file(mock_video_file):
    """Fixture to create a mock FastAPI UploadFile for testing"""
    
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = mock_video_file.name
    mock_file.content_type = "video/mp4"
    mock_file.size = Path(mock_video_file).stat().st_size
    
    # Mock the read method to return the file content
    async def mock_read():
        with open(mock_video_file, "rb") as f:
            return f.read()
    
    mock_file.read = mock_read
    
    yield mock_file


@pytest.fixture
def mock_minio_client():
    """Fixture to create a mock MinIO client for testing"""
    with patch("audio_intelligence.utils.minio_handler.Minio") as mock_minio:
        minio_instance = MagicMock()
        mock_minio.return_value = minio_instance
        
        # Mock common MinIO methods
        minio_instance.bucket_exists.return_value = True
        minio_instance.fget_object.return_value = None
        minio_instance.fput_object.return_value = None
        
        yield minio_instance


@pytest.fixture
@pytest.mark.asyncio
async def mock_transcriber(mock_settings, mock_video_file):
    """Fixture to create a mock transcriber for testing"""
    with patch("audio_intelligence.api.endpoints.transcription.TranscriptionService") as mock_transcription_class:
        mock_instance = MagicMock()
        mock_transcription_class.return_value = mock_instance
        
        # Set up the mock to return successful transcription results
        transcript_path = mock_settings.OUTPUT_DIR / f"{mock_video_file.stem}.srt"
        mock_instance.transcribe.return_value = AsyncMock(return_value=("test-job-id", transcript_path))()
        
        yield mock_instance
