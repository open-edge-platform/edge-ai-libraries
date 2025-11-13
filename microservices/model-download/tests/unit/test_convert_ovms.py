import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from app.main import convert_to_ovms_format

class TestConvertToOvmsFormat:
    """Test the convert_to_ovms_format function"""

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.makedirs")
    def test_successful_conversion(self, mock_makedirs, mock_exists, mock_subprocess):
        """Test successful model conversion to OVMS format"""
        # Setup mocks
        mock_exists.return_value = True  # Script already exists
        mock_subprocess.return_value = MagicMock(returncode=0)
        
        # Call function
        result = convert_to_ovms_format(
            model_name="microsoft/Phi-3.5-mini-instruct",
            weight_format="int8",
            huggingface_token="test_token",
            model_type="llm",
            target_device="CPU",
            model_directory="/test/model/dir",
            cache_size=10
        )
        
        # Verify
        assert "successfully downloaded, converted, and prepared for OVMS deployment" in result["message"]
        mock_makedirs.assert_called_with("/test/model/dir", exist_ok=True)
        assert mock_subprocess.call_count >= 2  # Login + export commands

    def test_invalid_model_type(self):
        """Test conversion with invalid model type"""
        with pytest.raises(HTTPException) as exc_info:
            convert_to_ovms_format(
                model_name="microsoft/Phi-3.5-mini-instruct",
                weight_format="int8",
                huggingface_token="test_token",
                model_type="invalid_type",
                target_device="CPU",
                model_directory="/test/model/dir"
            )
        
        assert exc_info.value.status_code == 400
        assert "Invalid model_type: invalid_type" in exc_info.value.detail

    def test_missing_huggingface_token(self):
        """Test conversion without Hugging Face token"""
        with pytest.raises(HTTPException) as exc_info:
            convert_to_ovms_format(
                model_name="microsoft/Phi-3.5-mini-instruct",
                weight_format="int8",
                huggingface_token=None,
                model_type="llm",
                target_device="CPU",
                model_directory="/test/model/dir"
            )
        
        assert exc_info.value.status_code == 401
        assert "Hugging Face token is required" in exc_info.value.detail

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.makedirs")
    def test_huggingface_login_failure(self, mock_makedirs, mock_exists, mock_subprocess):
        """Test handling of Hugging Face login failure"""
        mock_exists.return_value = True
        mock_subprocess.return_value = MagicMock(returncode=1)  # Login fails
        
        with pytest.raises(HTTPException) as exc_info:
            convert_to_ovms_format(
                model_name="microsoft/Phi-3.5-mini-instruct",
                weight_format="int8",
                huggingface_token="invalid_token",
                model_type="llm",
                target_device="CPU",
                model_directory="/test/model/dir"
            )
        
        assert exc_info.value.status_code == 401
        assert "Failed to authenticate with Hugging Face" in exc_info.value.detail

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.makedirs")
    def test_script_download_failure(self, mock_makedirs, mock_exists, mock_subprocess):
        """Test handling of export script download failure"""
        mock_exists.return_value = False  # Script doesn't exist
        
        def subprocess_side_effect(*args, **kwargs):
            if "huggingface-cli" in args[0]:
                return MagicMock(returncode=0)  # Login succeeds
            elif "curl" in args[0]:
                from subprocess import CalledProcessError
                raise CalledProcessError(1, "curl")  # Download fails
            return MagicMock(returncode=0)
        
        mock_subprocess.side_effect = subprocess_side_effect
        
        with pytest.raises(HTTPException) as exc_info:
            convert_to_ovms_format(
                model_name="microsoft/Phi-3.5-mini-instruct",
                weight_format="int8",
                huggingface_token="test_token",
                model_type="llm",
                target_device="CPU",
                model_directory="/test/model/dir"
            )
        
        assert exc_info.value.status_code == 500
        assert "Failed to download export script" in exc_info.value.detail

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.makedirs")
    def test_model_export_failure(self, mock_makedirs, mock_exists, mock_subprocess):
        """Test handling of model export failure"""
        mock_exists.return_value = True
        
        def subprocess_side_effect(*args, **kwargs):
            if "huggingface-cli" in args[0]:
                return MagicMock(returncode=0)  # Login succeeds
            elif "python3" in args[0] and "export_model.py" in args[0]:
                from subprocess import CalledProcessError
                raise CalledProcessError(1, "export_model.py")  # Export fails
            return MagicMock(returncode=0)
        
        mock_subprocess.side_effect = subprocess_side_effect
        
        with pytest.raises(HTTPException) as exc_info:
            convert_to_ovms_format(
                model_name="microsoft/Phi-3.5-mini-instruct",
                weight_format="int8",
                huggingface_token="test_token",
                model_type="llm",
                target_device="CPU",
                model_directory="/test/model/dir"
            )
        
        assert exc_info.value.status_code == 500
        assert "Model conversion failed" in exc_info.value.detail

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.makedirs")
    def test_different_model_types(self, mock_makedirs, mock_exists, mock_subprocess):
        """Test conversion with different valid model types"""
        mock_exists.return_value = True
        mock_subprocess.return_value = MagicMock(returncode=0)
        
        model_types = ["llm", "embeddings", "rerank"]
        
        for model_type in model_types:
            result = convert_to_ovms_format(
                model_name="microsoft/Phi-3.5-mini-instruct",
                weight_format="int8",
                huggingface_token="test_token",
                model_type=model_type,
                target_device="CPU",
                model_directory="/test/model/dir"
            )
            
            assert "successfully downloaded, converted, and prepared for OVMS deployment" in result["message"]

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.makedirs")
    def test_script_download_when_missing(self, mock_makedirs, mock_exists, mock_subprocess):
        """Test that script is downloaded when missing"""
        mock_exists.return_value = False  # Script doesn't exist
        mock_subprocess.return_value = MagicMock(returncode=0)
        
        convert_to_ovms_format(
            model_name="microsoft/Phi-3.5-mini-instruct",
            weight_format="int8",
            huggingface_token="test_token",
            model_type="llm",
            target_device="CPU",
            model_directory="/test/model/dir"
        )
        
        # Verify curl command was called to download script
        curl_calls = [call for call in mock_subprocess.call_args_list if "curl" in str(call)]
        assert len(curl_calls) > 0

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.makedirs")
    def test_conversion_with_cache_size(self, mock_makedirs, mock_exists, mock_subprocess):
        """Test conversion with cache size parameter"""
        mock_exists.return_value = True
        mock_subprocess.return_value = MagicMock(returncode=0)
        
        result = convert_to_ovms_format(
            model_name="microsoft/Phi-3.5-mini-instruct",
            weight_format="fp16",
            huggingface_token="test_token",
            model_type="llm",  # Use text_generation type for cache_size
            target_device="GPU",
            model_directory="/test/model/dir",
            cache_size=20
        )
        
        assert "successfully downloaded, converted, and prepared for OVMS deployment" in result["message"]
        
        # Verify cache size was included in the command
        export_calls = [call for call in mock_subprocess.call_args_list 
                       if "export_model.py" in str(call)]
        assert len(export_calls) > 0
        # Check that cache size argument is in the command
        assert any("--cache_size" in str(call) and "20" in str(call) for call in export_calls)

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.makedirs")
    def test_different_weight_formats(self, mock_makedirs, mock_exists, mock_subprocess):
        """Test conversion with different weight formats"""
        mock_exists.return_value = True
        mock_subprocess.return_value = MagicMock(returncode=0)
        
        weight_formats = ["int8", "fp16", "fp32"]
        
        for weight_format in weight_formats:
            result = convert_to_ovms_format(
                model_name="microsoft/Phi-3.5-mini-instruct",
                weight_format=weight_format,
                huggingface_token="test_token",
                model_type="llm",
                target_device="CPU",
                model_directory="/test/model/dir"
            )
            
            assert "successfully downloaded, converted, and prepared for OVMS deployment" in result["message"]
            
            # Verify weight format was used in command
            export_calls = [call for call in mock_subprocess.call_args_list 
                           if "export_model.py" in str(call)]
            assert any(weight_format in str(call) for call in export_calls)

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.makedirs")
    def test_different_target_devices(self, mock_makedirs, mock_exists, mock_subprocess):
        """Test conversion with different target devices"""
        mock_exists.return_value = True
        mock_subprocess.return_value = MagicMock(returncode=0)
        
        devices = ["CPU", "GPU"]
        
        for device in devices:
            result = convert_to_ovms_format(
                model_name="microsoft/Phi-3.5-mini-instruct",
                weight_format="int8",
                huggingface_token="test_token",
                model_type="llm",
                target_device=device,
                model_directory="/test/model/dir"
            )
            
            assert "successfully downloaded, converted, and prepared for OVMS deployment" in result["message"]
            
            # Verify device was used in command
            export_calls = [call for call in mock_subprocess.call_args_list 
                           if "export_model.py" in str(call)]
            assert any(device in str(call) for call in export_calls)
