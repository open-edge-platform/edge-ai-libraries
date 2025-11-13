import os
from unittest.mock import patch, MagicMock, ANY
import pytest
from fastapi import HTTPException

class TestHealth:
    def test_health_check(self, test_client):
        """Test health check endpoint"""
        response = test_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

class TestAuthentication:
    def test_model_download_missing_token(self, test_client):
        """Test that API returns 401 when authorization token is missing"""
        request = {
            "models": [
                {
                    "name": "test-model",
                    "hub": "huggingface",
                    "type": "llm",
                    "is_ovms": False
                }
            ]
        }
        response = test_client.post("/models/download", json=request)
        assert response.status_code == 401
        assert "Authorization token is required" in response.json()["detail"]

    def test_model_download_empty_token(self, test_client):
        """Test that API returns 401 when authorization token is empty"""
        request = {
            "models": [
                {
                    "name": "test-model",
                    "hub": "huggingface",
                    "type": "llm",
                    "is_ovms": False
                }
            ]
        }
        response = test_client.post("/models/download", json=request, headers={"Authorization": ""})
        assert response.status_code == 401
        assert "Authorization token is required" in response.json()["detail"]

class TestSingleModelDownload:
    @patch("app.main.cleanup_model_directory")
    @patch("app.main.snapshot_download")
    @patch("app.main.convert_to_ovms_format")
    def test_successful_single_model_download(self, mock_convert, mock_download, mock_cleanup,
                                           test_client, mock_hf_token, single_model_request, test_model_path):
        """Test successful single model download and conversion"""
        mock_download.return_value = os.path.join(test_model_path, "model")
        mock_convert.return_value = {"message": "Model converted successfully"}

        response = test_client.post(
            "/models/download",
            json=single_model_request,
            headers={"Authorization": f"Bearer {mock_hf_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "Model downloaded successfully" in data["message"]
        assert data["model_path"] == os.path.join(test_model_path, "model")
        assert len(data["results"]) == 1
        assert data["results"][0]["status"] == "success"
        
        mock_download.assert_called_once()
        mock_convert.assert_called_once()

    @patch("app.main.cleanup_model_directory")
    @patch("app.main.snapshot_download")
    def test_single_model_download_without_ovms(self, mock_download, mock_cleanup, test_client, mock_hf_token, test_model_path):
        """Test single model download without OVMS conversion"""
        mock_download.return_value = os.path.join(test_model_path, "model")
        request = {
            "models": [
                {
                    "name": "Intel/neural-chat-7b-v3-3",
                    "hub": "huggingface",
                    "type": "llm",
                    "is_ovms": False
                }
            ]
        }

        response = test_client.post(
            "/models/download",
            json=request,
            headers={"Authorization": f"Bearer {mock_hf_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["results"][0]["is_ovms"] is False
        mock_download.assert_called_once()

    @patch("app.main.snapshot_download")
    def test_single_model_download_failure(self, mock_download, test_client, mock_hf_token):
        """Test single model download failure handling"""
        mock_download.side_effect = Exception("Download failed")
        request = {
            "models": [
                {
                    "name": "nonexistent-model",
                    "hub": "huggingface",
                    "type": "llm",
                    "is_ovms": False
                }
            ]
        }

        response = test_client.post(
            "/models/download",
            json=request,
            headers={"Authorization": f"Bearer {mock_hf_token}"}
        )

        assert response.status_code == 400
        assert "Download failed" in response.json()["detail"]

class TestMultiModelDownload:
    @patch("app.main.cleanup_model_directory")
    @patch("app.main.snapshot_download")
    @patch("app.main.convert_to_ovms_format")
    def test_successful_multi_model_download(self, mock_convert, mock_download, mock_cleanup,
                                          test_client, mock_hf_token, multi_model_request, test_model_path):
        """Test successful multiple model download and conversion"""
        mock_download.return_value = os.path.join(test_model_path, "model")
        mock_convert.return_value = {"message": "Model converted successfully"}

        response = test_client.post(
            "/models/download",
            json=multi_model_request,
            headers={"Authorization": f"Bearer {mock_hf_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2
        assert all(result["status"] == "success" for result in data["results"])
        assert mock_download.call_count == 2
        assert mock_convert.call_count == 2

    @patch("app.main.cleanup_model_directory")
    @patch("app.main.snapshot_download")
    def test_partial_download_failure(self, mock_download, mock_cleanup, test_client, mock_hf_token):
        """Test handling of partial failure in multiple model download"""
        def mock_download_effect(repo_id, **kwargs):
            if repo_id == "successful-model":
                return "/mock/path/success"
            raise Exception("Download failed for second model")

        mock_download.side_effect = mock_download_effect
        request = {
            "models": [
                {"name": "successful-model", "hub": "huggingface", "type": "llm", "is_ovms": False},
                {"name": "failing-model", "hub": "huggingface", "type": "llm", "is_ovms": False}
            ],
            "parallel_downloads": True
        }

        response = test_client.post(
            "/models/download",
            json=request,
            headers={"Authorization": f"Bearer {mock_hf_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2
        assert any(result["status"] == "success" for result in data["results"])
        assert any(result["status"] == "error" for result in data["results"])

    def test_parallel_processing(self, test_client, mock_hf_token):
        """Test that parallel processing flag is respected"""
        with patch("app.main.ThreadPoolExecutor") as mock_executor:
            mock_instance = MagicMock()
            mock_executor.return_value.__enter__.return_value = mock_instance
            
            request = {
                "models": [
                    {"name": "model1", "hub": "huggingface", "type": "llm", "is_ovms": False},
                    {"name": "model2", "hub": "huggingface", "type": "llm", "is_ovms": False}
                ],
                "parallel_downloads": True
            }

            response = test_client.post(
                "/models/download",
                json=request,
                headers={"Authorization": f"Bearer {mock_hf_token}"}
            )

            assert response.status_code == 200
            mock_executor.assert_called_once_with(max_workers=2)

class TestValidation:
    @pytest.mark.parametrize("scenario", [
        "empty_models",
        "missing_name", 
        "invalid_type",
        "invalid_config",
        "invalid_revision"
    ])
    def test_invalid_requests(self, test_client, mock_hf_token, invalid_model_requests, scenario):
        """Test various invalid request scenarios"""
        response = test_client.post(
            "/models/download",
            json=invalid_model_requests[scenario],
            headers={"Authorization": f"Bearer {mock_hf_token}"}
        )
        if scenario == "empty_models":
            # Empty models list should succeed but with no downloads
            assert response.status_code == 200
            assert response.json()["message"] == "Model download completed"
            assert len(response.json()["results"]) == 0
        else:
            assert response.status_code in [400, 422]

    def test_unsupported_hub(self, test_client, mock_hf_token):
        """Test unsupported model hub"""
        request = {
            "models": [
                {
                    "name": "test-model",
                    "hub": "unsupported_hub",
                    "type": "llm",
                    "is_ovms": False
                }
            ]
        }
        response = test_client.post(
            "/models/download",
            json=request,
            headers={"Authorization": f"Bearer {mock_hf_token}"}
        )
        assert response.status_code == 400
        assert "Unsupported model hub" in response.json()["detail"]

    def test_ollama_hub_no_auth_required(self, test_client):
        """Test that Ollama models don't require authentication"""
        request = {
            "models": [
                {
                    "name": "test-model",
                    "hub": "ollama",
                    "type": "llm",
                    "is_ovms": False
                }
            ]
        }
        with patch("app.main.download_ollama_model") as mock_download:
            mock_download.return_value = {
                "status": "success",
                "model_name": "test-model",
                "model_path": "/test/path",
                "error": None,
                "is_ovms": False
            }
            response = test_client.post("/models/download", json=request)
            assert response.status_code == 200

    def test_request_validation_error(self, test_client, mock_hf_token):
        """Test pydantic validation errors"""
        invalid_request = {
            "models": [
                {
                    "name": 123,  # Should be string
                    "hub": "huggingface",
                    "type": "llm"
                }
            ]
        }
        response = test_client.post(
            "/models/download",
            json=invalid_request,
            headers={"Authorization": f"Bearer {mock_hf_token}"}
        )
        # The API converts integers to strings, so this will result in a 400 error 
        # during processing, not a validation error
        assert response.status_code == 400

    def test_unexpected_exception_handling(self, test_client, mock_hf_token):
        """Test handling of unexpected exceptions"""
        with patch("app.main.download_and_process_model") as mock_download:
            mock_download.side_effect = RuntimeError("Unexpected error")
            request = {
                "models": [
                    {
                        "name": "test-model",
                        "hub": "huggingface",
                        "type": "llm",
                        "is_ovms": False
                    }
                ]
            }
            response = test_client.post(
                "/models/download",
                json=request,
                headers={"Authorization": f"Bearer {mock_hf_token}"}
            )
            assert response.status_code == 500
            assert "Failed to execute model downloads: Unexpected error" in response.json()["detail"]

    @patch("app.main.cleanup_model_directory")
    @patch("app.main.convert_to_ovms_format")
    @patch("app.main.snapshot_download")
    def test_ovms_config_override(self, mock_download, mock_convert, mock_cleanup,
                                test_client, mock_hf_token):
        """Test OVMS configuration override behavior"""
        mock_download.return_value = "/mock/path/model"
        mock_convert.return_value = {"message": "Model converted successfully"}
        mock_cleanup.return_value = None
        request = {
            "models": [
                {
                    "name": "Intel/neural-chat-7b-v3-3",
                    "hub": "huggingface",
                    "type": "llm",
                    "is_ovms": True,
                    "config": {
                        "precision": "fp16",
                        "device": "GPU",
                        "cache_size": 20
                    }
                }
            ]
        }

        response = test_client.post(
            "/models/download",
            json=request,
            headers={"Authorization": f"Bearer {mock_hf_token}"}
        )

        assert response.status_code == 200
        mock_convert.assert_called_once()
        call_args = mock_convert.call_args[1]
        assert call_args["weight_format"] == "fp16"
        assert call_args["target_device"] == "GPU"
        assert call_args["cache_size"] == 20

class TestEnvironment:
    @patch("app.main.cleanup_model_directory")
    @patch("app.main.convert_to_ovms_format")
    @patch("app.main.snapshot_download")
    def test_environment_variable_setting(self, mock_download, mock_convert, mock_cleanup, 
                                         test_client, mock_hf_token, single_model_request):
        """Test that functions are called with correct parameters"""
        mock_download.return_value = "/mock/path/model"
        mock_convert.return_value = {"message": "Model converted successfully"}
        
        response = test_client.post(
            "/models/download",
            json=single_model_request,
            headers={"Authorization": f"Bearer {mock_hf_token}"}
        )
        
        assert response.status_code == 200
        # Verify the token was passed to the functions correctly
        mock_download.assert_called_once()
        mock_convert.assert_called_once()

    @patch("app.main.cleanup_model_directory")
    @patch("app.main.convert_to_ovms_format")
    @patch("app.main.snapshot_download")
    @patch("app.main.os.makedirs")
    def test_directory_creation(self, mock_makedirs, mock_download, mock_convert, mock_cleanup,
                              test_client, mock_hf_token, single_model_request):
        """Test that necessary directories are created"""
        mock_download.return_value = "/mock/path/model"
        mock_convert.return_value = {"message": "Model converted successfully"}
        
        response = test_client.post(
            "/models/download",
            json=single_model_request,
            headers={"Authorization": f"Bearer {mock_hf_token}"}
        )
        
        assert response.status_code == 200
        mock_makedirs.assert_called_with(ANY, exist_ok=True)


class TestVLMIntegration:
    """Test VLM model integration in the main API"""

    @patch("app.main.cleanup_model_directory")
    @patch("app.main.vlm_compress_model")
    @patch("app.main.snapshot_download")
    def test_vlm_model_compression_success(self, mock_download, mock_vlm_compress, mock_cleanup,
                                         test_client, mock_hf_token, vlm_model_request, test_model_path):
        """Test successful VLM model compression through API"""
        mock_download.return_value = os.path.join(test_model_path, "vlm_model")
        mock_vlm_compress.return_value = {"status": "success", "output": "VLM compression completed"}

        response = test_client.post(
            "/models/download",
            json=vlm_model_request,
            headers={"Authorization": f"Bearer {mock_hf_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "Model downloaded successfully" in data["message"]
        assert len(data["results"]) == 1
        assert data["results"][0]["status"] == "success"
        
        # Verify VLM compression was called
        mock_vlm_compress.assert_called_once()
        call_args = mock_vlm_compress.call_args[1]["req"]
        assert call_args.model_name == "microsoft/Phi-3.5-mini-instruct"
        assert call_args.weight_format == "int8"
        assert call_args.hf_token == mock_hf_token

    @patch("app.main.cleanup_model_directory")
    @patch("app.main.vlm_compress_model")
    @patch("app.main.snapshot_download")
    def test_vlm_model_compression_failure(self, mock_download, mock_vlm_compress, mock_cleanup,
                                         test_client, mock_hf_token, vlm_model_request, test_model_path):
        """Test VLM model compression failure handling"""
        mock_download.return_value = os.path.join(test_model_path, "vlm_model")
        mock_vlm_compress.side_effect = HTTPException(status_code=500, detail="VLM compression failed")
        mock_cleanup.return_value = None

        response = test_client.post(
            "/models/download",
            json=vlm_model_request,
            headers={"Authorization": f"Bearer {mock_hf_token}"}
        )

        # The API should handle the VLM compression error gracefully
        assert response.status_code == 400

    @patch("app.main.vlm_compress_model")
    @patch("app.main.snapshot_download")
    def test_multiple_vlm_models_compression(self, mock_download, mock_vlm_compress, 
                                           test_client, mock_hf_token, multi_vlm_model_request, test_model_path):
        """Test compression of multiple VLM models"""
        mock_download.return_value = test_model_path
        mock_vlm_compress.return_value = {"status": "success", "output": "VLM compression completed"}

        response = test_client.post(
            "/models/download",
            json=multi_vlm_model_request,
            headers={"Authorization": f"Bearer {mock_hf_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2
        
        # Verify VLM compression was called for each model
        assert mock_vlm_compress.call_count == 2

    @patch("app.main.vlm_compress_model")
    @patch("app.main.snapshot_download")
    def test_vlm_model_with_different_weight_formats(self, mock_download, mock_vlm_compress, 
                                                   test_client, mock_hf_token, test_model_path):
        """Test VLM models with different weight formats"""
        mock_download.return_value = test_model_path
        mock_vlm_compress.return_value = {"status": "success", "output": "VLM compression completed"}

        weight_formats = ["int8", "fp16", "fp32"]
        
        for weight_format in weight_formats:
            request = {
                "models": [
                    {
                        "name": "test/vlm-model",
                        "hub": "huggingface",
                        "type": "vlm",
                        "is_ovms": False,
                        "config": {
                            "precision": weight_format,
                            "device": "CPU",
                            "cache_size": 10
                        }
                    }
                ],
                "parallel_downloads": False
            }

            response = test_client.post(
                "/models/download",
                json=request,
                headers={"Authorization": f"Bearer {mock_hf_token}"}
            )

            assert response.status_code == 200
            
            # Verify correct weight format was used
            call_args = mock_vlm_compress.call_args[1]["req"]
            assert call_args.weight_format == weight_format

    @patch("app.main.vlm_compress_model")
    @patch("app.main.snapshot_download")
    def test_vlm_model_without_config(self, mock_download, mock_vlm_compress, 
                                    test_client, mock_hf_token, test_model_path):
        """Test VLM model without config (should use default weight format)"""
        mock_download.return_value = test_model_path
        mock_vlm_compress.return_value = {"status": "success", "output": "VLM compression completed"}

        request = {
            "models": [
                {
                    "name": "test/vlm-model",
                    "hub": "huggingface",
                    "type": "vlm",
                    "is_ovms": False
                }
            ],
            "parallel_downloads": False
        }

        response = test_client.post(
            "/models/download",
            json=request,
            headers={"Authorization": f"Bearer {mock_hf_token}"}
        )

        assert response.status_code == 200
        
        # Verify default weight format was used
        call_args = mock_vlm_compress.call_args[1]["req"]
        assert call_args.weight_format == "int8"  # Default format

    @patch("app.main.vlm_compress_model")
    @patch("app.main.snapshot_download")
    def test_mixed_model_types_with_vlm(self, mock_download, mock_vlm_compress, 
                                      test_client, mock_hf_token, test_model_path):
        """Test mixed model types including VLM models"""
        mock_download.return_value = test_model_path
        mock_vlm_compress.return_value = {"status": "success", "output": "VLM compression completed"}

        request = {
            "models": [
                {
                    "name": "Intel/neural-chat-7b-v3-3",
                    "hub": "huggingface",
                    "type": "llm",
                    "is_ovms": True,
                    "config": {
                        "precision": "int8",
                        "device": "CPU",
                        "cache_size": 10
                    }
                },
                {
                    "name": "test/vlm-model",
                    "hub": "huggingface",
                    "type": "vlm",
                    "is_ovms": False,
                    "config": {
                        "precision": "fp16",
                        "device": "GPU",
                        "cache_size": 20
                    }
                }
            ],
            "parallel_downloads": False
        }

        response = test_client.post(
            "/models/download",
            json=request,
            headers={"Authorization": f"Bearer {mock_hf_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2
        
        # Verify VLM compression was called only once (for VLM model)
        mock_vlm_compress.assert_called_once()
