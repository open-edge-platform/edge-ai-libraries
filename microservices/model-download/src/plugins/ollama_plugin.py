
import os
import subprocess
from typing import Optional
from utils.helper import cleanup_model_directory
from utils.logging import logger
from src.api.models import ModelRequest, ModelResult
from src.core.interfaces import ModelDownloadPlugin


class OllamaPlugin(ModelDownloadPlugin):
    def download(self, model: ModelRequest, model_path: str, hf_token: Optional[str] = None) -> ModelResult:
        return download_ollama_model(model, model_path)

def download_ollama_model(model: ModelRequest, model_path: str) -> ModelResult:
    """
    Download a model from Ollama.

    Args:
        model (ModelRequest): The Ollama model request object to download.
        model_path: Base path for model downloads

    Returns:
        ModelResult: Result containing the status and details of the model processing.

    Raises:
        OSError: If directory creation fails
        HTTPException: If model download fails
    """
    import time

    if model.is_ovms:
        raise NotImplementedError(
            "Ollama models do not support OVMS conversion at this time."
        )

    model_downloaded_path = None
    try:
        # Create model-specific directory
        model_downloaded_path = os.path.join(
            model_path, "ollama_models", model.name.replace("/", "_")
        )
        os.environ["OLLAMA_MODELS"] = model_downloaded_path

        logger.info(f"Directory for Ollama model: {model_downloaded_path}")
        try:
            os.makedirs(model_downloaded_path, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create directory {model_downloaded_path}: {str(e)}")
            return ModelResult(
                status="error",
                model_name=model.name,
                model_path=None,
                error=f"Failed to create model directory: {str(e)}",
                is_ovms=None,
            )

        logger.info("Starting ollama server")
        process = subprocess.Popen(["ollama", "serve"])

        # Sleep for 1 second to allow the server to be start
        time.sleep(1)

        logger.info(f"Starting download for Ollama model: {model.name}")
        subprocess.run(["ollama", "pull", model.name], check=True)
        logger.info(f"Ollama model {model} downloaded successfully.")

        return ModelResult(
            status="success",
            model_name=model.name,
            model_path=model_downloaded_path,
            error=None,
            is_ovms=model.is_ovms,
        )

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to download Ollama model {model}: {str(e)}")
        return ModelResult(
            status="error",
            model_name=model.name,
            model_path=None,
            error=f"Failed to download Ollama model: {str(e)}",
            is_ovms=False,
        )
    finally:
        logger.info("Stopping ollama server")
        process.terminate()
        if model_downloaded_path is not None:
            cleanup_model_directory(model_downloaded_path)