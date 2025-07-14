import os
from unittest.mock import patch, MagicMock, ANY
import pytest
from fastapi import HTTPException

class TestAuthentication:
    def test_model_download_missing_token(self, test_client):
        """Test that API returns 401 when authorization token is missing"""
        response = test_client.post("/models/download")
        assert response.status_code == 401
        assert "Authorization token is empty" in response.json()["detail"]

    def test_model_download_empty_token(self, test_client):
        """Test that API returns 401 when authorization token is empty"""
        response = test_client.post("/models/download", headers={"Authorization": ""})
        assert response.status_code == 401
        assert "Authorization token is empty" in response.json()["detail"]

class TestSingleModelDownload:
    @patch("app.main.snapshot_download")
    @patch("app.main.convert_to_ovms_format")
    def test_successful_single_model_download(self, mock_convert, mock_download, 
                                           test_client, mock_hf_token, single_model_request, test_model_path):
        """Test successful single model download and conversion"""
        mock_download.return_value = os.path.join(test_model_path, "model")
        mock_convert.return_value = {"message": "Model converted successfully"}

        response = test_client.post(
            "/models/download",
            json=single_model_request,
            headers={"Authorization": mock_hf_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert "Model downloaded successfully" in data["message"]
        assert data["model_path"] == "/mock/path/model"
        assert len(data["results"]) == 1
        assert data["results"][0]["status"] == "success"
        
        mock_download.assert_called_once()
        mock_convert.assert_called_once()

    @patch("app.main.snapshot_download")
    def test_single_model_download_without_ovms(self, mock_download, test_client, mock_hf_token, test_model_path):
        """Test single model download without OVMS conversion"""
        mock_download.return_value = os.path.join(test_model_path, "model")
        request = {
            "models": [
                {
                    "name": "bert-base-uncased",
                    "is_ovms": False
                }
            ]
        }

        response = test_client.post(
            "/models/download",
            json=request,
            headers={"Authorization": mock_hf_token}
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
                    "is_ovms": False
                }
            ]
        }

        response = test_client.post(
            "/models/download",
            json=request,
            headers={"Authorization": mock_hf_token}
        )

        assert response.status_code == 400
        assert "Download failed" in response.json()["detail"]

class TestMultiModelDownload:
    @patch("app.main.snapshot_download")
    @patch("app.main.convert_to_ovms_format")
    def test_successful_multi_model_download(self, mock_convert, mock_download, 
                                          test_client, mock_hf_token, multi_model_request, test_model_path):
        """Test successful multiple model download and conversion"""
        mock_download.return_value = os.path.join(test_model_path, "model")
        mock_convert.return_value = {"message": "Model converted successfully"}

        response = test_client.post(
            "/models/download",
            json=multi_model_request,
            headers={"Authorization": mock_hf_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2
        assert all(result["status"] == "success" for result in data["results"])
        assert mock_download.call_count == 2
        assert mock_convert.call_count == 2

    @patch("app.main.snapshot_download")
    def test_partial_download_failure(self, mock_download, test_client, mock_hf_token):
        """Test handling of partial failure in multiple model download"""
        def mock_download_effect(repo_id, **kwargs):
            if repo_id == "successful-model":
                return "/mock/path/success"
            raise Exception("Download failed for second model")

        mock_download.side_effect = mock_download_effect
        request = {
            "models": [
                {"name": "successful-model", "is_ovms": False},
                {"name": "failing-model", "is_ovms": False}
            ],
            "parallel_downloads": True
        }

        response = test_client.post(
            "/models/download",
            json=request,
            headers={"Authorization": mock_hf_token}
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
                    {"name": "model1", "is_ovms": False},
                    {"name": "model2", "is_ovms": False}
                ],
                "parallel_downloads": True
            }

            response = test_client.post(
                "/models/download",
                json=request,
                headers={"Authorization": mock_hf_token}
            )

            assert response.status_code == 200
            mock_executor.assert_called_once_with(max_workers=2)

class TestValidation:
    @pytest.mark.parametrize("scenario", [
        "empty_models",
        "missing_name",
        "invalid_type",
        "invalid_ovms_config",
        "invalid_revision"
    ])
    def test_invalid_requests(self, test_client, mock_hf_token, invalid_model_requests, scenario):
        """Test various invalid request scenarios"""
        response = test_client.post(
            "/models/download",
            json=invalid_model_requests[scenario],
            headers={"Authorization": mock_hf_token}
        )
        assert response.status_code in [400, 422]

    @patch("app.main.snapshot_download")
    @patch("app.main.convert_to_ovms_format")
    def test_ovms_config_override(self, mock_convert, mock_download, 
                                test_client, mock_hf_token):
        """Test OVMS configuration override behavior"""
        mock_download.return_value = "/mock/path/model"
        request = {
            "models": [
                {
                    "name": "bert-base-uncased",
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
            headers={"Authorization": mock_hf_token}
        )

        assert response.status_code == 200
        mock_convert.assert_called_once()
        call_args = mock_convert.call_args[1]
        assert call_args["weight_format"] == "fp16"
        assert call_args["target_device"] == "GPU"
        assert call_args["cache_size"] == 20

class TestEnvironment:
    def test_environment_variable_setting(self, test_client, mock_hf_token, single_model_request):
        """Test that HF_TOKEN environment variable is set correctly"""
        response = test_client.post(
            "/models/download",
            json=single_model_request,
            headers={"Authorization": mock_hf_token}
        )
        
        assert response.status_code == 200
        assert os.environ.get("HF_TOKEN") == mock_hf_token

    @patch("app.main.os.makedirs")
    def test_directory_creation(self, mock_makedirs, test_client, mock_hf_token, single_model_request):
        """Test that necessary directories are created"""
        response = test_client.post(
            "/models/download",
            json=single_model_request,
            headers={"Authorization": mock_hf_token}
        )
        
        assert response.status_code == 200
        mock_makedirs.assert_called_with(ANY, exist_ok=True)
