import os
import yaml
import pytest

# Configure the environment variable prior to importing the app
# This ensures the app operates in test mode, bypassing the startup function responsible for model downloading and conversion
os.environ['RUN_TEST'] = "True"

def pytest_addoption(parser):
    parser.addoption(
        "--model-backend",
        action="store",
        default="default",
        help="Specify the model backend to use (e.g., openvino, ollama)"
    )

@pytest.fixture
def skip_if_not_ollama(request):
    if request.config.getoption("--model-backend") != "ollama":
        pytest.skip("Only valid for ollama backend")

@pytest.fixture
def skip_if_not_openvino(request):
    if request.config.getoption("--model-backend") != "openvino":
        pytest.skip("Only valid for openvino backend")

@pytest.fixture(scope="session", autouse=True)
def setup_dummy_config(request):
    # Get model backend from CLI
    model_backend = request.config.getoption("--model-backend")
    os.environ['MODEL_BACKEND'] = model_backend

    # Create dummy config
    config_dir = "/tmp/model_config"
    config_file = os.path.join(config_dir, "default_model.yaml")

    if not os.path.exists(config_file):
        os.makedirs(config_dir, exist_ok=True)
        dummy_config = {
            "model_settings": {
                "MODEL_BACKEND": model_backend,
                "EMBEDDING_MODEL_ID": f"{model_backend}/embedding-model",
                "RERANKER_MODEL_ID": f"{model_backend}/reranker-model",
                "LLM_MODEL_ID": f"{model_backend}/llm-model"
            },
            "device_settings": {
                "EMBEDDING_DEVICE": "CPU",
                "RERANKER_DEVICE": "CPU",
                "LLM_DEVICE": "CPU"
            }
        }
        with open(config_file, "w") as f:
            yaml.dump(dummy_config, f, default_flow_style=False)
        print(f"Created dummy config at {config_file} for backend '{model_backend}'")

    yield

    # Cleanup after session
    if os.path.exists(config_file):
        os.remove(config_file)
        print(f"Deleted dummy config at {config_file}")

    if os.path.isdir(config_dir) and not os.listdir(config_dir):
        os.rmdir(config_dir)
        print(f"Deleted empty config directory at {config_dir}")


@pytest.fixture(scope="module")
def test_client():
    from fastapi.testclient import TestClient
    from app.server import app

    client = TestClient(app)
    yield client