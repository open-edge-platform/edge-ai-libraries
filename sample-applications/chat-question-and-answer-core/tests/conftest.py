import os
import yaml
import pytest

# Configure the environment variable prior to importing the app
# This ensures the app operates in test mode, bypassing the startup function responsible for model downloading and conversion
os.environ['RUN_TEST'] = "True"

def pytest_addoption(parser):
    parser.addoption(
        "--model-runtime",
        action="store",
        default="default",
        help="Specify the model backend to use (e.g., openvino, ollama)"
    )

@pytest.fixture
def skip_if_not_ollama(request):
    if request.config.getoption("--model-runtime") != "ollama":
        pytest.skip("Only valid for ollama backend")

@pytest.fixture
def skip_if_not_openvino(request):
    if request.config.getoption("--model-runtime") != "openvino":
        pytest.skip("Only valid for openvino backend")

@pytest.fixture(scope="session", autouse=True)
def setup_dummy_config(request):
    # Get model backend from CLI
    model_runtime = request.config.getoption("--model-runtime")
    os.environ['MODEL_RUNTIME'] = model_runtime

    # Create dummy config
    config_dir = "/tmp/model_config"
    config_file = os.path.join(config_dir, "default_model.yaml")

    if not os.path.exists(config_file):
        os.makedirs(config_dir, exist_ok=True)
        dummy_config = {
            "model_settings": {
                "MODEL_RUNTIME": model_runtime,
                "EMBEDDING_MODEL_ID": f"{model_runtime}/embedding-model",
                "RERANKER_MODEL_ID": f"{model_runtime}/reranker-model",
                "LLM_MODEL_ID": f"{model_runtime}/llm-model"
            },
            "device_settings": {
                "EMBEDDING_DEVICE": "CPU",
                "RERANKER_DEVICE": "CPU",
                "LLM_DEVICE": "CPU"
            }
        }
        with open(config_file, "w") as f:
            yaml.dump(dummy_config, f, default_flow_style=False)
        print(f"Created dummy config at {config_file} for backend runtime '{model_runtime}'")

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
