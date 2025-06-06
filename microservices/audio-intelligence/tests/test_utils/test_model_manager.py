from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from audio_intelligence.schemas.types import WhisperModel
from audio_intelligence.utils.model_manager import ModelManager


@pytest.mark.asyncio
@pytest.mark.unit
async def test_download_models():
    """Test downloading models based on configuration"""
    # Mock the download methods
    with patch.object(ModelManager, "_download_ggml_models", AsyncMock()) as mock_ggml, \
         patch.object(ModelManager, "_download_openvino_models", AsyncMock()) as mock_openvino, \
         patch("audio_intelligence.utils.model_manager.is_intel_gpu_available", return_value=True):
        
        # Call the method
        await ModelManager.download_models()
        
        # Verify the correct download methods were called
        mock_ggml.assert_called_once()
        mock_openvino.assert_called_once()


@pytest.mark.unit
def test_is_model_downloaded_ggml_exists():
    """Test checking if GGML model is downloaded and available"""
    # Mock settings and Path
    mock_path = MagicMock()
    mock_path.is_file.return_value = True
    mock_stat = MagicMock()
    mock_stat.st_size = 12345  # Non-zero file size
    mock_path.stat.return_value = mock_stat
    
    with patch("audio_intelligence.utils.model_manager.ModelManager.get_model_path", return_value=mock_path):
        # Call the method
        result = ModelManager.is_model_downloaded(WhisperModel.TINY_EN, use_gpu=False)
        
        # Verify result
        assert result is True


@pytest.mark.unit
def test_is_model_downloaded_ggml_not_exists():
    """Test checking if GGML model does not exist"""
    # Mock settings and Path
    mock_path = MagicMock()
    mock_path.is_file.return_value = False
    
    with patch("audio_intelligence.utils.model_manager.ModelManager.get_model_path", return_value=mock_path):
        # Call the method
        result = ModelManager.is_model_downloaded(WhisperModel.TINY_EN, use_gpu=False)
        
        # Verify result
        assert result is False


@pytest.mark.unit
def test_is_model_downloaded_openvino_exists():
    """Test checking if OpenVINO model is downloaded and available"""
    # Mock settings and Path
    mock_path = MagicMock()
    mock_path.is_dir.return_value = True
    mock_path.iterdir.return_value = [MagicMock()]  # Non-empty directory
    
    with patch("audio_intelligence.utils.model_manager.ModelManager.get_model_path", return_value=mock_path):
        # Call the method
        result = ModelManager.is_model_downloaded(WhisperModel.TINY_EN, use_gpu=True)
        
        # Verify result
        assert result is True


@pytest.mark.unit
def test_is_model_downloaded_openvino_not_exists():
    """Test checking if OpenVINO model does not exist"""
    # Mock settings and Path
    mock_path = MagicMock()
    mock_path.is_dir.return_value = True
    mock_path.iterdir.return_value = []  # Empty directory
    
    with patch("audio_intelligence.utils.model_manager.ModelManager.get_model_path", return_value=mock_path):
        # Call the method
        result = ModelManager.is_model_downloaded(WhisperModel.TINY_EN, use_gpu=True)
        
        # Verify result
        assert result is False
