# Keep track of test paths
import os
import pytest
from fastapi.testclient import TestClient

# Import from the new structure with error handling for missing dependencies
try:
    from src.api.main import app
except ImportError as e:
    # Create a mock app if dependencies are missing
    from fastapi import FastAPI
    app = FastAPI()
    print(f"Warning: Could not import main app due to missing dependencies: {e}")

try:
    from src.core.plugin_registry import PluginRegistry
    from src.core.model_manager import ModelManager
    from src.api.models import ModelPrecision, DeviceType, ModelHub, ModelType
    PLUGINS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Plugin system not available due to missing dependencies: {e}")
    PLUGINS_AVAILABLE = False
    # Create mock classes
    class MockPluginRegistry:
        def __init__(self):
            self.plugins = {}
        def discover_plugins(self, package):
            pass
    
    class MockModelManager:
        def __init__(self, registry, default_dir):
            self._jobs = {}
    
    PluginRegistry = MockPluginRegistry
    ModelManager = MockModelManager
    
    # Create mock enums
    from enum import Enum
    class ModelPrecision(str, Enum):
        INT4 = "int4"
        INT8 = "int8"
        FP16 = "fp16"
        FP32 = "fp32"
    
    class DeviceType(str, Enum):
        CPU = "CPU"
        GPU = "GPU"
    
    class ModelHub(str, Enum):
        HUGGINGFACE = "huggingface"
        ULTRALYTICS = "ultralytics"
        OLLAMA = "ollama"
        OPENVINO = "openvino"
    
    class ModelType(str, Enum):
        LLM = "llm"
        EMBEDDINGS = "embeddings"
        RERANKER = "rerank"
        VISION = "vision"

import importlib

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
def plugin_registry():
    """Fixture to create a plugin registry for testing"""
    if not PLUGINS_AVAILABLE:
        pytest.skip("Plugin dependencies not available")
    
    registry = PluginRegistry()
    try:
        plugins_package = importlib.import_module("src.plugins")
        registry.discover_plugins(plugins_package)
    except ImportError:
        pass  # No plugins available
    return registry

@pytest.fixture
def model_manager(plugin_registry, test_model_path):
    """Fixture to create a model manager for testing"""
    if not PLUGINS_AVAILABLE:
        pytest.skip("Plugin dependencies not available")
    
    return ModelManager(plugin_registry, default_dir=test_model_path)

@pytest.fixture
def hf_token():
    """Get Hugging Face token from environment variable"""
    return os.getenv("HF_TOKEN")

@pytest.fixture
def mock_hf_token():
    """Mock Hugging Face token for testing when HF_TOKEN is not available"""
    return "hf_mock_token_for_testing"

@pytest.fixture
def hf_token_env_setup(monkeypatch):
    """Fixture to set up HF_TOKEN environment variable for testing"""
    test_token = "hf_test_token_12345"
    monkeypatch.setenv("HF_TOKEN", test_token)
    return test_token

@pytest.fixture
def no_hf_token_env_setup(monkeypatch):
    """Fixture to remove HF_TOKEN environment variable for testing"""
    monkeypatch.delenv("HF_TOKEN", raising=False)
    return None

@pytest.fixture
def single_model_request():
    """Fixture for a valid single model request"""
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
def ollama_model_request():
    """Fixture for an Ollama model request"""
    return {
        "models": [
            {
                "name": "tinyllama",
                "hub": "ollama",
                "type": "llm",
                "is_ovms": False
            }
        ],
        "parallel_downloads": False
    }

@pytest.fixture
def ultralytics_model_request():
    """Fixture for an Ultralytics model request"""
    return {
        "models": [
            {
                "name": "yolov8n.pt",
                "hub": "ultralytics",
                "type": "vision",
                "is_ovms": False
            }
        ],
        "parallel_downloads": False
    }

@pytest.fixture
def openvino_model_request():
    """Fixture for an OpenVINO model request"""
    return {
        "models": [
            {
                "name": "microsoft/Phi-3.5-mini-instruct",
                "hub": "openvino",
                "type": "llm",
                "is_ovms": True,
                "config": {
                    "precision": "int4",
                    "device": "CPU",
                    "cache_size": 15
                }
            }
        ],
        "parallel_downloads": False
    }

@pytest.fixture
def invalid_model_requests():
    """Fixture for various invalid request scenarios"""
    return {
        "empty_models": {"models": []},
        "missing_name": {
            "models": [{"hub": "huggingface", "type": "llm", "is_ovms": True}]
        },
        "invalid_hub": {
            "models": [{
                "name": "Intel/neural-chat-7b-v3-3",
                "hub": "invalid_hub",
                "type": "llm",
                "is_ovms": True
            }]
        },
        "invalid_type": {
            "models": [{
                "name": "Intel/neural-chat-7b-v3-3",
                "hub": "huggingface",
                "type": "invalid_type",
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
        "invalid_precision": {
            "models": [{
                "name": "Intel/neural-chat-7b-v3-3",
                "hub": "huggingface",
                "type": "llm",
                "is_ovms": True,
                "config": {
                    "precision": "int6",  # Invalid precision
                    "device": "CPU"
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
        },
        "empty_name": {
            "models": [{
                "name": "",  # Empty name
                "hub": "huggingface",
                "type": "llm"
            }]
        }
    }

@pytest.fixture
def vlm_model_request():
    """Fixture for a valid VLM model request"""
    return {
        "models": [
            {
                "name": "microsoft/Phi-3.5-mini-instruct",
                "hub": "huggingface",
                "type": "vision",
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
                "type": "vision",
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
                "type": "vision",
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

@pytest.fixture
def reranker_model_request():
    """Fixture for a reranker model request"""
    return {
        "models": [
            {
                "name": "BAAI/bge-reranker-v2-m3",
                "hub": "huggingface",
                "type": "rerank",
                "is_ovms": True,
                "config": {
                    "precision": "fp32",
                    "device": "CPU",
                    "cache_size": 5
                }
            }
        ],
        "parallel_downloads": False
    }

@pytest.fixture
def conversion_config():
    """Fixture for model conversion configuration"""
    return {
        "precision": "int8",
        "device": "CPU",
        "cache": 10
    }

@pytest.fixture
def job_data():
    """Fixture for job data structure"""
    return {
        "id": "test-job-id",
        "operation_type": "download",
        "model_name": "test-model",
        "hub": "huggingface",
        "output_dir": "/test/output",
        "status": "queued",
        "start_time": "2023-01-01T00:00:00",
        "plugin_name": "huggingface",
        "progress": {"current": 0, "total": 0, "percentage": 0}
    }

@pytest.fixture
def mock_plugin():
    """Fixture for creating a mock plugin"""
    if not PLUGINS_AVAILABLE:
        pytest.skip("Plugin dependencies not available")
    
    from src.core.interfaces import ModelDownloadPlugin
    
    class MockPlugin(ModelDownloadPlugin):
        def __init__(self, name="mock", plugin_type="downloader"):
            self._name = name
            self._type = plugin_type
        
        @property
        def plugin_name(self):
            return self._name
        
        @property
        def plugin_type(self):
            return self._type
        
        def can_handle(self, model_name, hub, **kwargs):
            return hub == "mock"
        
        def download(self, model_name, output_dir, progress_callback=None, **kwargs):
            return {
                "model_name": model_name,
                "source": "mock",
                "download_path": output_dir,
                "success": True
            }
    
    return MockPlugin

@pytest.fixture
def download_response_success():
    """Fixture for successful download response"""
    return {
        "message": "Started processing 1 model(s)",
        "job_ids": ["test-job-id"],
        "status": "processing"
    }

@pytest.fixture
def job_status_completed():
    """Fixture for completed job status"""
    return {
        "id": "test-job-id",
        "operation_type": "download",
        "model_name": "test-model",
        "hub": "huggingface",
        "status": "completed",
        "completion_time": "2023-01-01T01:00:00",
        "result": {
            "model_name": "test-model",
            "download_path": "/test/output",
            "success": True
        }
    }

# Legacy fixtures for backward compatibility with existing tests
@pytest.fixture
def vlm_compression_request():
    """Legacy fixture for VLM compression request"""
    hf_token = os.getenv("HF_TOKEN", "test_hf_token")
    return {
        "model_name": "microsoft/Phi-3.5-mini-instruct",
        "weight_format": "int8",
        "hf_token": hf_token,
        "model_path": "/test/model/path"
    }

@pytest.fixture
def vlm_compression_request_no_token():
    """Legacy fixture for VLM compression request without HF token"""
    return {
        "model_name": "microsoft/Phi-3.5-mini-instruct",
        "weight_format": "fp16",
        "hf_token": None,
        "model_path": "/test/model/path"
    }

@pytest.fixture
def plugin_availability_response():
    """Fixture for plugin availability response"""
    return {
        "available_plugins": {
            "downloader": [
                {
                    "name": "huggingface",
                    "type": "downloader",
                    "available": True,
                    "unavailable_reason": None
                },
                {
                    "name": "ollama",
                    "type": "downloader", 
                    "available": False,
                    "unavailable_reason": "Ollama not installed"
                }
            ],
            "converter": [
                {
                    "name": "openvino",
                    "type": "converter",
                    "available": True,
                    "unavailable_reason": None
                }
            ]
        },
        "total_count": 3,
        "available_count": 2
    }

# Environment variable testing utilities
@pytest.fixture
def with_hf_token():
    """Context manager fixture to set HF_TOKEN for testing"""
    class HFTokenContext:
        def __init__(self, token="hf_test_token_12345"):
            self.token = token
            self.original_value = None
            
        def __enter__(self):
            self.original_value = os.environ.get("HF_TOKEN")
            os.environ["HF_TOKEN"] = self.token
            return self.token
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            if self.original_value is not None:
                os.environ["HF_TOKEN"] = self.original_value
            else:
                os.environ.pop("HF_TOKEN", None)
    
    return HFTokenContext

@pytest.fixture
def without_hf_token():
    """Context manager fixture to remove HF_TOKEN for testing"""
    class NoHFTokenContext:
        def __init__(self):
            self.original_value = None
            
        def __enter__(self):
            self.original_value = os.environ.get("HF_TOKEN")
            os.environ.pop("HF_TOKEN", None)
            return None
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            if self.original_value is not None:
                os.environ["HF_TOKEN"] = self.original_value
    
    return NoHFTokenContext

# Plugin dependency checks
@pytest.fixture
def require_huggingface():
    """Skip test if huggingface_hub is not available"""
    try:
        import huggingface_hub
    except ImportError:
        pytest.skip("huggingface_hub not available")

@pytest.fixture 
def require_openvino():
    """Skip test if openvino is not available"""
    try:
        import openvino
    except ImportError:
        pytest.skip("openvino not available")

@pytest.fixture
def require_ultralytics():
    """Skip test if ultralytics is not available"""
    try:
        import ultralytics
    except ImportError:
        pytest.skip("ultralytics not available")
