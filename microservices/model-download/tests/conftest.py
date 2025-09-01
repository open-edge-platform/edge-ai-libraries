# Keep track of test paths
import os
import pytest
from fastapi.testclient import TestClient
from app.main import app

# Base path for all test files
TEST_BASE_PATH = os.path.join(os.path.dirname(__file__), "test_data")

@pytest.fixture(scope="session", autouse=True)
def setup_test_paths():
    """Create and clean up test directories"""
    # Create test directories if they don't exist
    os.makedirs(TEST_BASE_PATH, exist_ok=True)
    yield

@pytest.fixture
def test_model_path():
    """Fixture to provide model path within test directory"""
    path = os.path.join(TEST_BASE_PATH, "models")
    os.makedirs(path, exist_ok=True)
    return path

@pytest.fixture
def test_client():
    """TestClient fixture for FastAPI application"""
    return TestClient(app)

@pytest.fixture
def mock_hf_token():
    """Mock Hugging Face token"""
    return "mock_hf_token"

@pytest.fixture
def single_model_request(test_model_path):
    """Fixture for a valid single model request with test path"""
    return {
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
        ],
        "parallel_downloads": False
    }

@pytest.fixture
def multi_model_request():
    """Fixture for a valid multi-model request"""
    return {
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
                "name": "BAAI/bge-small-en-v1.5",
                "hub": "huggingface",
                "type": "embeddings",
                "is_ovms": True,
                "config": {
                    "precision": "fp16",
                    "device": "GPU",
                    "cache_size": 20
                }
            }
        ],
        "parallel_downloads": True
    }

@pytest.fixture
def invalid_model_requests():
    """Fixture for various invalid request scenarios"""
    return {
        "empty_models": {"models": []},
        "missing_name": {
            "models": [{"hub": "huggingface", "type": "llm", "is_ovms": True}]
        },
        "invalid_type": {
            "models": [{
                "name": "Intel/neural-chat-7b-v3-3",
                "hub": "huggingface",
                "type": "invalid",
                "is_ovms": True
            }]
        },
        "invalid_config": {
            "models": [{
                "name": "Intel/neural-chat-7b-v3-3",
                "hub": "huggingface",
                "type": "llm",
                "is_ovms": True,
                "config": {
                    "precision": "invalid",
                    "device": "invalid",
                    "cache_size": -1
                }
            }]
        },
        "invalid_revision": {
            "models": [{
                "name": "Intel/neural-chat-7b-v3-3",
                "hub": "huggingface",
                "revision": 123,  # Should be string
                "is_ovms": True
            }]
        }
    }

@pytest.fixture
def vlm_compression_request():
    """Fixture for a valid VLM compression request"""
    return {
        "model_name": "microsoft/Phi-3.5-mini-instruct",
        "weight_format": "int8",
        "hf_token": "test_hf_token",
        "model_path": "/test/model/path"
    }

@pytest.fixture
def vlm_compression_request_no_token():
    """Fixture for VLM compression request without HF token"""
    return {
        "model_name": "microsoft/Phi-3.5-mini-instruct",
        "weight_format": "fp16",
        "hf_token": None,
        "model_path": "/test/model/path"
    }

@pytest.fixture
def vlm_model_request(test_model_path):
    """Fixture for a valid VLM model request"""
    return {
        "models": [
            {
                "name": "microsoft/Phi-3.5-mini-instruct",
                "hub": "huggingface",
                "type": "vlm",
                "is_ovms": False,
                "config": {
                    "precision": "int8",
                    "device": "CPU",
                    "cache_size": 10
                }
            }
        ],
        "parallel_downloads": False
    }

@pytest.fixture
def multi_vlm_model_request():
    """Fixture for multiple VLM models request"""
    return {
        "models": [
            {
                "name": "Qwen/Qwen2.5-VL-7B-Instruct",
                "hub": "huggingface",
                "type": "vlm",
                "is_ovms": False,
                "config": {
                    "precision": "int8",
                    "device": "CPU",
                    "cache_size": 10
                }
            },
            {
                "name": "microsoft/Phi-3.5-vision-instruct",
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
        "parallel_downloads": True
    }
