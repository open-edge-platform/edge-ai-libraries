import os
import pytest
import tempfile
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.models import ModelHub, ModelType, ModelPrecision, DeviceType


class TestAPIMain:
    """Test suite for API main endpoints"""

    @pytest.fixture
    def client(self):
        """Create a FastAPI test client"""
        return TestClient(app)

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def mock_plugin_registry(self):
        """Mock plugin registry"""
        mock_registry = MagicMock()
        mock_registry.plugins = {
            "downloader": {
                "huggingface": MagicMock(),
                "ollama": MagicMock(),
                "ultralytics": MagicMock()
            },
            "converter": {
                "openvino": MagicMock()
            }
        }
        mock_registry.get_plugin_names.return_value = ["huggingface", "ollama", "ultralytics", "openvino"]
        mock_registry.check_plugin_dependencies.return_value = (True, None)
        return mock_registry

    @pytest.fixture
    def mock_model_manager(self):
        """Mock model manager"""
        mock_manager = MagicMock()
        mock_manager._jobs = {}
        mock_manager.register_job.return_value = "test-job-id"
        mock_manager.process_download = AsyncMock()
        mock_manager.process_conversion = AsyncMock()
        return mock_manager

    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @patch('src.api.main.model_manager')
    @patch('src.api.main.plugin_registry')
    @patch('os.getenv')
    def test_download_huggingface_model_success(self, mock_getenv, mock_registry, mock_manager, client):
        """Test successful HuggingFace model download"""
        # Setup mocks
        mock_getenv.side_effect = lambda key, default=None: {
            "HF_TOKEN": "test_hf_token",
            "MODELS_DIR": "/opt/models"
        }.get(key, default)
        
        mock_registry.plugins = {"downloader": {"huggingface": MagicMock()}}
        mock_registry.get_plugin_names.return_value = ["huggingface"]
        mock_registry.check_plugin_dependencies.return_value = (True, None)
        mock_manager.register_job.return_value = "job-123"
        mock_manager.process_download = AsyncMock()

        request_data = {
            "models": [
                {
                    "name": "bert-base-uncased",
                    "hub": "huggingface",
                    "type": "llm",
                    "is_ovms": False
                }
            ]
        }

        response = client.post("/models/download?download_path=test_models", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "Started processing 1 model(s)" in data["message"]
        assert data["job_ids"] == ["job-123"]
        assert data["status"] == "processing"

    @patch('src.api.main.model_manager')
    @patch('src.api.main.plugin_registry')
    @patch('os.getenv')
    def test_download_ollama_model_success(self, mock_getenv, mock_registry, mock_manager, client):
        """Test successful Ollama model download"""
        # Setup mocks
        mock_getenv.side_effect = lambda key, default=None: {
            "MODELS_DIR": "/opt/models"
        }.get(key, default)
        
        mock_registry.plugins = {"downloader": {"ollama": MagicMock()}}
        mock_registry.get_plugin_names.return_value = ["ollama"]
        mock_registry.check_plugin_dependencies.return_value = (True, None)
        mock_manager.register_job.return_value = "job-456"
        mock_manager.process_download = AsyncMock()

        request_data = {
            "models": [
                {
                    "name": "llama2",
                    "hub": "ollama",
                    "type": "llm",
                    "is_ovms": False
                }
            ]
        }

        response = client.post("/models/download?download_path=ollama_models", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "Started processing 1 model(s)" in data["message"]
        assert data["job_ids"] == ["job-456"]

    @patch('src.api.main.model_manager')
    @patch('src.api.main.plugin_registry')
    @patch('os.getenv')
    def test_download_ultralytics_model_success(self, mock_getenv, mock_registry, mock_manager, client):
        """Test successful Ultralytics model download"""
        # Setup mocks
        mock_getenv.side_effect = lambda key, default=None: {
            "MODELS_DIR": "/opt/models"
        }.get(key, default)
        
        mock_registry.plugins = {"downloader": {"ultralytics": MagicMock()}}
        mock_registry.get_plugin_names.return_value = ["ultralytics"]
        mock_registry.check_plugin_dependencies.return_value = (True, None)
        mock_manager.register_job.return_value = "job-789"
        mock_manager.process_download = AsyncMock()

        request_data = {
            "models": [
                {
                    "name": "yolov8n.pt",
                    "hub": "ultralytics",
                    "type": "vision",
                    "is_ovms": False
                }
            ]
        }

        response = client.post("/models/download?download_path=ultralytics_models", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "Started processing 1 model(s)" in data["message"]
        assert data["job_ids"] == ["job-789"]

    @patch('src.api.main.model_manager')
    @patch('src.api.main.plugin_registry')
    @patch('os.getenv')
    def test_download_with_openvino_conversion(self, mock_getenv, mock_registry, mock_manager, client):
        """Test model download with OpenVINO conversion"""
        # Setup mocks
        mock_getenv.side_effect = lambda key, default=None: {
            "HF_TOKEN": "test_hf_token",
            "MODELS_DIR": "/opt/models"
        }.get(key, default)
        
        mock_registry.plugins = {
            "downloader": {"huggingface": MagicMock()},
            "converter": {"openvino": MagicMock()}
        }
        mock_registry.get_plugin_names.return_value = ["huggingface", "openvino"]
        mock_registry.check_plugin_dependencies.return_value = (True, None)
        mock_manager.register_job.return_value = "job-conversion"
        mock_manager.process_conversion = AsyncMock()

        request_data = {
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
                }
            ]
        }

        response = client.post("/models/download?download_path=converted_models", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "Started processing 1 model(s)" in data["message"]
        assert data["job_ids"] == ["job-conversion"]

    @patch('src.api.main.model_manager')
    @patch('src.api.main.plugin_registry')
    @patch('os.getenv')
    def test_download_multiple_models(self, mock_getenv, mock_registry, mock_manager, client):
        """Test downloading multiple models from different hubs"""
        # Setup mocks
        mock_getenv.side_effect = lambda key, default=None: {
            "HF_TOKEN": "test_hf_token",
            "MODELS_DIR": "/opt/models"
        }.get(key, default)
        
        mock_registry.plugins = {
            "downloader": {"huggingface": MagicMock(), "ollama": MagicMock()},
            "converter": {"openvino": MagicMock()}
        }
        mock_registry.get_plugin_names.return_value = ["huggingface", "ollama", "openvino"]
        mock_registry.check_plugin_dependencies.return_value = (True, None)
        mock_manager.register_job.side_effect = ["job-1", "job-2", "job-3"]
        mock_manager.process_download = AsyncMock()
        mock_manager.process_conversion = AsyncMock()

        request_data = {
            "models": [
                {
                    "name": "bert-base-uncased",
                    "hub": "huggingface",
                    "type": "embeddings",
                    "is_ovms": False
                },
                {
                    "name": "llama2",
                    "hub": "ollama",
                    "type": "llm",
                    "is_ovms": False
                },
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

        response = client.post("/models/download?download_path=multi_models", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "Started processing 3 model(s)" in data["message"]
        assert len(data["job_ids"]) == 3

    @patch('src.api.main.plugin_registry')
    def test_download_unsupported_hub(self, mock_registry, client):
        """Test download with unsupported hub"""
        mock_registry.plugins = {"downloader": {"huggingface": MagicMock()}}
        mock_registry.get_plugin_names.return_value = ["huggingface"]

        request_data = {
            "models": [
                {
                    "name": "test-model",
                    "hub": "unsupported_hub",
                    "type": "llm",
                    "is_ovms": False
                }
            ]
        }

        response = client.post("/models/download?download_path=test", json=request_data)
        
        assert response.status_code == 422
        # Check that it's a validation error due to invalid hub value
        error_detail = response.json()["detail"]
        assert isinstance(error_detail, list)  # Pydantic validation errors are returned as a list
        # Check that the error is related to the hub field
        assert any("hub" in str(error).lower() for error in error_detail)

    @patch('src.api.main.plugin_registry')
    def test_download_plugin_unavailable(self, mock_registry, client):
        """Test download when plugin is unavailable"""
        mock_registry.plugins = {"downloader": {"huggingface": MagicMock()}}
        mock_registry.get_plugin_names.return_value = ["huggingface"]
        mock_registry.check_plugin_dependencies.return_value = (False, "Missing huggingface_hub dependency")

        request_data = {
            "models": [
                {
                    "name": "bert-base-uncased",
                    "hub": "huggingface",
                    "type": "llm",
                    "is_ovms": False
                }
            ]
        }

        response = client.post("/models/download?download_path=test", json=request_data)
        
        assert response.status_code == 400
        assert "Plugin 'huggingface' is not available" in response.json()["detail"]

    @patch('src.api.main.model_manager')
    @patch('src.api.main.plugin_registry')
    def test_download_openvino_conversion_unavailable(self, mock_registry, mock_manager, client):
        """Test download when OpenVINO conversion is requested but unavailable"""
        mock_registry.plugins = {"downloader": {"huggingface": MagicMock()}}
        mock_registry.get_plugin_names.return_value = ["huggingface"]
        
        # Mock different responses for different plugins
        def mock_check_dependencies(plugin_name):
            if plugin_name == "huggingface":
                return (True, None)
            elif plugin_name == "openvino":
                return (False, "OpenVINO not installed")
            return (False, "Unknown plugin")
        
        mock_registry.check_plugin_dependencies.side_effect = mock_check_dependencies

        request_data = {
            "models": [
                {
                    "name": "bert-base-uncased",
                    "hub": "huggingface",
                    "type": "llm",
                    "is_ovms": True,
                    "config": {
                        "precision": "int8",
                        "device": "CPU"
                    }
                }
            ]
        }

        response = client.post("/models/download?download_path=test", json=request_data)
        
        assert response.status_code == 400
        assert "OpenVINO conversion requested but plugin is not available" in response.json()["detail"]

    @patch('src.api.main.model_manager')
    def test_get_job_status_success(self, mock_manager, client):
        """Test getting job status successfully"""
        mock_manager._jobs = {
            "job-123": {
                "id": "job-123",
                "operation_type": "download",
                "model_name": "bert-base-uncased",
                "status": "completed",
                "progress": {"current": 100, "total": 100, "percentage": 100}
            }
        }

        response = client.get("/jobs/job-123")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "job-123"
        assert data["status"] == "completed"

    @patch('src.api.main.model_manager')
    def test_get_job_status_not_found(self, mock_manager, client):
        """Test getting status for non-existent job"""
        mock_manager._jobs = {}

        response = client.get("/jobs/nonexistent-job")
        
        assert response.status_code == 404
        assert "Job nonexistent-job not found" in response.json()["detail"]

    @patch('src.api.main.model_manager')
    def test_get_model_jobs_success(self, mock_manager, client):
        """Test getting jobs for a specific model"""
        mock_manager._jobs = {
            "job-1": {
                "id": "job-1",
                "model_name": "bert-base-uncased",
                "operation_type": "download",
                "status": "completed"
            },
            "job-2": {
                "id": "job-2",
                "model_name": "bert-base-uncased",
                "operation_type": "convert",
                "status": "processing"
            },
            "job-3": {
                "id": "job-3",
                "model_name": "other-model",
                "operation_type": "download",
                "status": "completed"
            }
        }

        response = client.get("/models/jobs?model_name=bert-base-uncased")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) == 2
        assert all(job["model_name"] == "bert-base-uncased" for job in data["jobs"])

    @patch('src.api.main.model_manager')
    def test_get_model_jobs_not_found(self, mock_manager, client):
        """Test getting jobs for model with no jobs"""
        mock_manager._jobs = {}

        response = client.get("/models/jobs?model_name=nonexistent-model")
        
        assert response.status_code == 404
        assert "No jobs found for model nonexistent-model" in response.json()["detail"]

    @patch('src.api.main.model_manager')
    def test_get_model_results(self, mock_manager, client):
        """Test getting completed model results"""
        mock_manager._jobs = {
            "job-1": {
                "id": "job-1",
                "model_name": "bert-base-uncased",
                "hub": "huggingface",
                "operation_type": "download",
                "status": "completed",
                "output_dir": "/opt/models/bert",
                "completion_time": "2023-01-01T12:00:00"
            },
            "job-2": {
                "id": "job-2",
                "model_name": "llama2",
                "hub": "ollama",
                "operation_type": "download",
                "status": "processing",
                "output_dir": "/opt/models/llama2"
            },
            "job-3": {
                "id": "job-3",
                "model_name": "neural-chat",
                "hub": "huggingface",
                "operation_type": "convert",
                "status": "completed",
                "output_dir": "/opt/models/neural-chat-ovms",
                "completion_time": "2023-01-01T13:00:00"
            }
        }

        response = client.get("/models/results")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2  # Only completed jobs
        
        # Check that both completed jobs are included
        job_ids = [result["job_id"] for result in data["results"]]
        assert "job-1" in job_ids
        assert "job-3" in job_ids
        
        # Check OVMS flag is set correctly
        for result in data["results"]:
            if result["job_id"] == "job-1":
                assert result["is_ovms"] == False  # download operation
            elif result["job_id"] == "job-3":
                assert result["is_ovms"] == True   # convert operation

    @patch('src.api.main.model_manager')
    def test_list_jobs(self, mock_manager, client):
        """Test listing all jobs"""
        mock_manager._jobs = {
            "job-1": {"id": "job-1", "status": "completed"},
            "job-2": {"id": "job-2", "status": "processing"}
        }

        response = client.get("/jobs")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) == 2

    @patch('src.api.main.plugin_registry')
    def test_list_plugins(self, mock_registry, client):
        """Test listing available plugins"""
        # Setup mocks
        mock_hf_plugin = MagicMock()
        mock_hf_plugin.__doc__ = "HuggingFace plugin for model downloads"
        mock_ollama_plugin = MagicMock()
        mock_ollama_plugin.__doc__ = "Ollama plugin for local models"
        mock_openvino_plugin = MagicMock()
        mock_openvino_plugin.__doc__ = "OpenVINO converter plugin"

        mock_registry.plugins = {
            "downloader": {
                "huggingface": mock_hf_plugin,
                "ollama": mock_ollama_plugin
            },
            "converter": {
                "openvino": mock_openvino_plugin
            }
        }
        
        def mock_check_dependencies(plugin_name):
            if plugin_name == "huggingface":
                return (True, None)
            elif plugin_name == "ollama":
                return (False, "Ollama not installed")
            elif plugin_name == "openvino":
                return (True, None)
            return (False, "Unknown plugin")
        
        mock_registry.check_plugin_dependencies.side_effect = mock_check_dependencies

        response = client.get("/plugins")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "available_plugins" in data
        assert "downloader" in data["available_plugins"]
        assert "converter" in data["available_plugins"]
        assert data["total_count"] == 3
        assert data["available_count"] == 2  # huggingface and openvino are available

    def test_invalid_request_format(self, client):
        """Test API with invalid request format"""
        invalid_request = {
            "models": [
                {
                    "name": "",  # Empty name should fail validation
                    "hub": "huggingface"
                }
            ]
        }

        response = client.post("/models/download?download_path=test", json=invalid_request)
        
        assert response.status_code == 422

    @pytest.mark.parametrize("model_data,expected_status", [
        # Valid requests
        ({"name": "bert-base-uncased", "hub": "huggingface", "type": "llm"}, 200),
        ({"name": "llama2", "hub": "ollama", "type": "llm"}, 200),
        ({"name": "yolov8n.pt", "hub": "ultralytics", "type": "vision"}, 200),
        
        # Invalid requests
        ({"name": "", "hub": "huggingface"}, 422),  # Empty name
        ({"name": "test", "hub": "invalid_hub"}, 422),  # Invalid hub
    ])
    @patch('src.api.main.model_manager')
    @patch('src.api.main.plugin_registry')
    @patch('os.getenv')
    def test_various_request_formats(self, mock_getenv, mock_registry, mock_manager, client, model_data, expected_status):
        """Test API with various request formats"""
        # Setup mocks for valid requests
        if expected_status == 200:
            mock_getenv.return_value = "/opt/models"
            mock_registry.plugins = {"downloader": {"huggingface": MagicMock(), "ollama": MagicMock(), "ultralytics": MagicMock()}}
            mock_registry.get_plugin_names.return_value = ["huggingface", "ollama", "ultralytics"]
            mock_registry.check_plugin_dependencies.return_value = (True, None)
            mock_manager.register_job.return_value = "test-job"
            mock_manager.process_download = AsyncMock()

        request_data = {"models": [model_data]}
        response = client.post("/models/download?download_path=test", json=request_data)
        
        assert response.status_code == expected_status

    @patch('src.api.main.model_manager')
    @patch('src.api.main.plugin_registry')
    @patch('os.getenv')
    def test_vlm_model_conversion(self, mock_getenv, mock_registry, mock_manager, client):
        """Test VLM model download with automatic conversion"""
        # Setup mocks
        mock_getenv.side_effect = lambda key, default=None: {
            "HF_TOKEN": "test_hf_token",
            "MODELS_DIR": "/opt/models"
        }.get(key, default)
        
        mock_registry.plugins = {
            "downloader": {"huggingface": MagicMock()},
            "converter": {"openvino": MagicMock()}
        }
        mock_registry.get_plugin_names.return_value = ["huggingface", "openvino"]
        mock_registry.check_plugin_dependencies.return_value = (True, None)
        mock_manager.register_job.return_value = "job-vlm"
        mock_manager.process_conversion = AsyncMock()

        request_data = {
            "models": [
                {
                    "name": "microsoft/Phi-3.5-vision-instruct",
                    "hub": "huggingface",
                    "type": "vision",
                    "is_ovms": True,  # Set to True to trigger conversion
                    "config": {
                        "precision": "fp16",
                        "device": "GPU",
                        "cache_size": 15
                    }
                }
            ]
        }

        response = client.post("/models/download?download_path=vlm_models", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "Started processing 1 model(s)" in data["message"]
        assert data["job_ids"] == ["job-vlm"]

    @patch('src.api.main.model_manager')
    @patch('src.api.main.plugin_registry')
    @patch('os.getenv')
    def test_mixed_operations_download_and_convert(self, mock_getenv, mock_registry, mock_manager, client):
        """Test mixed operations - some models for download only, some for conversion"""
        # Setup mocks
        mock_getenv.side_effect = lambda key, default=None: {
            "HF_TOKEN": "test_hf_token",
            "MODELS_DIR": "/opt/models"
        }.get(key, default)
        
        mock_registry.plugins = {
            "downloader": {"huggingface": MagicMock(), "ollama": MagicMock()},
            "converter": {"openvino": MagicMock()}
        }
        mock_registry.get_plugin_names.return_value = ["huggingface", "ollama", "openvino"]
        mock_registry.check_plugin_dependencies.return_value = (True, None)
        mock_manager.register_job.side_effect = ["job-download", "job-convert"]
        mock_manager.process_download = AsyncMock()
        mock_manager.process_conversion = AsyncMock()

        request_data = {
            "models": [
                {
                    "name": "llama2",
                    "hub": "ollama",
                    "type": "llm",
                    "is_ovms": False  # Download only
                },
                {
                    "name": "Intel/neural-chat-7b-v3-3",
                    "hub": "huggingface",
                    "type": "llm",
                    "is_ovms": True,  # Conversion required
                    "config": {
                        "precision": "int8",
                        "device": "CPU",
                        "cache_size": 10
                    }
                }
            ]
        }

        response = client.post("/models/download?download_path=mixed_models", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "Started processing 2 model(s)" in data["message"]
        assert len(data["job_ids"]) == 2


class TestAPIErrorHandling:
    """Test suite for API error handling"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @patch('src.api.main.model_manager')
    @patch('src.api.main.plugin_registry')
    def test_unexpected_exception_handling(self, mock_registry, mock_manager, client):
        """Test handling of unexpected exceptions"""
        # Setup mocks to raise an exception
        mock_registry.plugins = {"downloader": {"huggingface": MagicMock()}}
        mock_registry.get_plugin_names.side_effect = Exception("Unexpected error")

        request_data = {
            "models": [
                {
                    "name": "bert-base-uncased",
                    "hub": "huggingface",
                    "type": "llm",
                    "is_ovms": False
                }
            ]
        }

        response = client.post("/models/download?download_path=test", json=request_data)
        
        assert response.status_code == 500
        assert "Unexpected error in model download process" in response.json()["detail"]

    def test_missing_download_path_parameter(self, client):
        """Test API call without required download_path parameter"""
        request_data = {
            "models": [
                {
                    "name": "bert-base-uncased",
                    "hub": "huggingface",
                    "type": "llm",
                    "is_ovms": False
                }
            ]
        }

        response = client.post("/models/download", json=request_data)
        
        assert response.status_code == 422  # Validation error for missing required parameter

    def test_invalid_json_request(self, client):
        """Test API with invalid JSON"""
        response = client.post(
            "/models/download?download_path=test",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 422

    @pytest.mark.parametrize("invalid_config", [
        {"precision": "invalid_precision", "device": "CPU"},
        {"precision": "int8", "device": "INVALID_DEVICE"},
        {"precision": "int8", "device": "CPU", "cache_size": -1},  # Negative cache size
        {"precision": "int8", "device": "CPU", "cache_size": 0},   # Zero cache size
    ])
    def test_invalid_config_parameters(self, client, invalid_config):
        """Test API with various invalid config parameters"""
        request_data = {
            "models": [
                {
                    "name": "bert-base-uncased",
                    "hub": "huggingface",
                    "type": "llm",
                    "is_ovms": True,
                    "config": invalid_config
                }
            ]
        }

        response = client.post("/models/download?download_path=test", json=request_data)
        
        assert response.status_code == 422  # Validation error

    def test_empty_models_list(self, client):
        """Test API with empty models list"""
        request_data = {"models": []}

        response = client.post("/models/download?download_path=test", json=request_data)
        
        # This should be valid but result in no processing
        assert response.status_code == 200
        data = response.json()
        assert "Started processing 0 model(s)" in data["message"]
        assert data["job_ids"] == []