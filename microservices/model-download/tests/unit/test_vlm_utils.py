import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from app.vlm_utils import vlm_compress_model, CompressionRequest


class TestCompressionRequest:
    """Test cases for CompressionRequest model validation"""
    
    def test_compression_request_valid_data(self):
        """Test CompressionRequest with valid data"""
        req = CompressionRequest(
            model_name="microsoft/Phi-3.5-mini-instruct",
            weight_format="int8",
            hf_token="hf_token_123",
            model_path="/path/to/model"
        )
        
        assert req.model_name == "microsoft/Phi-3.5-mini-instruct"
        assert req.weight_format == "int8"
        assert req.hf_token == "hf_token_123"
        assert req.model_path == "/path/to/model"

    def test_compression_request_without_token(self):
        """Test CompressionRequest without HF token (optional field)"""
        req = CompressionRequest(
            model_name="microsoft/Phi-3.5-mini-instruct",
            weight_format="fp16",
            model_path="/path/to/model"
        )
        
        assert req.model_name == "microsoft/Phi-3.5-mini-instruct"
        assert req.weight_format == "fp16"
        assert req.hf_token is None
        assert req.model_path == "/path/to/model"

    def test_compression_request_missing_required_fields(self):
        """Test CompressionRequest with missing required fields"""
        with pytest.raises(ValueError):
            CompressionRequest(
                weight_format="int8",
                model_path="/path/to/model"
                # Missing model_name
            )

        with pytest.raises(ValueError):
            CompressionRequest(
                model_name="microsoft/Phi-3.5-mini-instruct",
                model_path="/path/to/model"
                # Missing weight_format
            )

        with pytest.raises(ValueError):
            CompressionRequest(
                model_name="microsoft/Phi-3.5-mini-instruct",
                weight_format="int8"
                # Missing model_path
            )


class TestVLMCompressModel:
    """Test cases for vlm_compress_model function"""

    @patch('app.vlm_utils.subprocess.run')
    def test_vlm_compress_model_success(self, mock_subprocess):
        """Test successful VLM model compression"""
        # Setup mock
        mock_result = MagicMock()
        mock_result.stdout = "Model compression completed successfully"
        mock_subprocess.return_value = mock_result
        
        # Create request
        req = CompressionRequest(
            model_name="microsoft/Phi-3.5-mini-instruct",
            weight_format="int8",
            hf_token="hf_token_123",
            model_path="/path/to/model"
        )
        
        # Call function
        result = vlm_compress_model(req)
        
        # Assertions
        assert result["status"] == "success"
        assert result["output"] == "Model compression completed successfully"
        
        # Verify subprocess was called with correct arguments
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert call_args[0] == "bash"
        assert "vlm_compress_model.sh" in call_args[1]
        assert call_args[2] == "microsoft/Phi-3.5-mini-instruct"
        assert call_args[3] == "int8"
        assert call_args[4] == "hf_token_123"
        assert call_args[5] == "/path/to/model"

    @patch('app.vlm_utils.subprocess.run')
    def test_vlm_compress_model_success_without_token(self, mock_subprocess):
        """Test successful VLM model compression without HF token"""
        # Setup mock
        mock_result = MagicMock()
        mock_result.stdout = "Model compression completed successfully"
        mock_subprocess.return_value = mock_result
        
        # Create request without token
        req = CompressionRequest(
            model_name="microsoft/Phi-3.5-mini-instruct",
            weight_format="fp16",
            hf_token=None,
            model_path="/path/to/model"
        )
        
        # Call function
        result = vlm_compress_model(req)
        
        # Assertions
        assert result["status"] == "success"
        assert result["output"] == "Model compression completed successfully"
        
        # Verify subprocess was called with empty token
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert call_args[4] == ""  # Empty token

    @patch('app.vlm_utils.subprocess.run')
    def test_vlm_compress_model_script_failure(self, mock_subprocess):
        """Test VLM model compression when script fails"""
        # Setup mock to raise CalledProcessError
        from subprocess import CalledProcessError
        mock_subprocess.side_effect = CalledProcessError(
            returncode=1,
            cmd="bash vlm_compress_model.sh",
            stderr="Script execution failed"
        )
        
        # Create request
        req = CompressionRequest(
            model_name="microsoft/Phi-3.5-mini-instruct",
            weight_format="int8",
            hf_token="hf_token_123",
            model_path="/path/to/model"
        )
        
        # Call function and expect HTTPException
        with pytest.raises(HTTPException) as exc_info:
            vlm_compress_model(req)
        
        assert exc_info.value.status_code == 500
        assert "Script execution failed" in str(exc_info.value.detail)

    @patch('app.vlm_utils.subprocess.run')
    def test_vlm_compress_model_different_weight_formats(self, mock_subprocess):
        """Test VLM model compression with different weight formats"""
        mock_result = MagicMock()
        mock_result.stdout = "Compression successful"
        mock_subprocess.return_value = mock_result
        
        weight_formats = ["int8", "fp16", "fp32"]
        
        for weight_format in weight_formats:
            req = CompressionRequest(
                model_name="test/model",
                weight_format=weight_format,
                hf_token="token",
                model_path="/test/path"
            )
            
            result = vlm_compress_model(req)
            assert result["status"] == "success"
            
            # Verify correct weight format was passed
            call_args = mock_subprocess.call_args[0][0]
            assert call_args[3] == weight_format

    @patch('app.vlm_utils.subprocess.run')
    @patch('app.vlm_utils.os.path.dirname')
    @patch('app.vlm_utils.os.path.join')
    def test_vlm_compress_model_script_path_construction(self, mock_join, mock_dirname, mock_subprocess):
        """Test that the script path is constructed correctly"""
        # Setup mocks
        mock_dirname.return_value = "/app"
        mock_join.return_value = "/app/../scripts/vlm_compress_model.sh"
        
        mock_result = MagicMock()
        mock_result.stdout = "Success"
        mock_subprocess.return_value = mock_result
        
        # Create request
        req = CompressionRequest(
            model_name="test/model",
            weight_format="int8",
            model_path="/test/path"
        )
        
        # Call function
        vlm_compress_model(req)
        
        # Verify path construction
        mock_dirname.assert_called_once()
        mock_join.assert_called_once_with("/app", "../scripts/vlm_compress_model.sh")

    @patch('app.vlm_utils.subprocess.run')
    def test_vlm_compress_model_subprocess_parameters(self, mock_subprocess):
        """Test that subprocess is called with correct parameters"""
        import subprocess
        
        mock_result = MagicMock()
        mock_result.stdout = "Success"
        mock_subprocess.return_value = mock_result
        
        req = CompressionRequest(
            model_name="test/model",
            weight_format="int8",
            model_path="/test/path"
        )
        
        vlm_compress_model(req)
        
        # Verify subprocess parameters
        mock_subprocess.assert_called_once()
        call_kwargs = mock_subprocess.call_args[1]
        assert call_kwargs["stdout"] == subprocess.PIPE
        assert call_kwargs["stderr"] == subprocess.STDOUT
        assert call_kwargs["text"] is True
        assert call_kwargs["check"] is True

    @patch('app.vlm_utils.subprocess.run')
    @patch('builtins.print')
    def test_vlm_compress_model_prints_output(self, mock_print, mock_subprocess):
        """Test that function prints the subprocess output"""
        mock_result = MagicMock()
        mock_result.stdout = "Detailed compression output"
        mock_subprocess.return_value = mock_result
        
        req = CompressionRequest(
            model_name="test/model",
            weight_format="int8",
            model_path="/test/path"
        )
        
        vlm_compress_model(req)
        
        # Verify print was called with the output
        mock_print.assert_called_once_with("Detailed compression output")

    @patch('app.vlm_utils.subprocess.run')
    def test_vlm_compress_model_empty_output(self, mock_subprocess):
        """Test VLM model compression with empty stdout"""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_subprocess.return_value = mock_result
        
        req = CompressionRequest(
            model_name="test/model",
            weight_format="int8",
            model_path="/test/path"
        )
        
        result = vlm_compress_model(req)
        
        assert result["status"] == "success"
        assert result["output"] == ""

    @patch('app.vlm_utils.subprocess.run')
    def test_vlm_compress_model_special_characters_in_paths(self, mock_subprocess):
        """Test VLM model compression with special characters in paths and names"""
        mock_result = MagicMock()
        mock_result.stdout = "Success"
        mock_subprocess.return_value = mock_result
        
        req = CompressionRequest(
            model_name="test/model-with-hyphens_and_underscores",
            weight_format="int8",
            hf_token="hf_token-with-special_chars123",
            model_path="/path/with spaces/and-special_chars"
        )
        
        result = vlm_compress_model(req)
        
        assert result["status"] == "success"
        
        # Verify the arguments were passed correctly
        call_args = mock_subprocess.call_args[0][0]
        assert call_args[2] == "test/model-with-hyphens_and_underscores"
        assert call_args[4] == "hf_token-with-special_chars123"
        assert call_args[5] == "/path/with spaces/and-special_chars"


class TestVLMUtilsIntegration:
    """Integration tests for VLM utilities"""

    def test_compression_request_to_vlm_compress_model_flow(self):
        """Test the complete flow from request creation to function call"""
        with patch('app.vlm_utils.subprocess.run') as mock_subprocess:
            mock_result = MagicMock()
            mock_result.stdout = "Integration test success"
            mock_subprocess.return_value = mock_result
            
            # Create and use request
            req = CompressionRequest(
                model_name="integration/test-model",
                weight_format="fp16",
                hf_token="integration_token",
                model_path="/integration/test/path"
            )
            
            result = vlm_compress_model(req)
            
            # Verify end-to-end flow
            assert result["status"] == "success"
            assert result["output"] == "Integration test success"
            
            # Verify all request fields were used
            call_args = mock_subprocess.call_args[0][0]
            assert "integration/test-model" in call_args
            assert "fp16" in call_args
            assert "integration_token" in call_args
            assert "/integration/test/path" in call_args
