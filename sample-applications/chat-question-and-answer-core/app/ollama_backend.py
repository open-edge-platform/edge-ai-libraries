from .config import config
from .logger import logger
from langchain_ollama import OllamaEmbeddings
from langchain_ollama.llms import OllamaLLM
from datetime import datetime, timezone
import ollama
import os
import re
import shutil
import time
# subprocess is used safely without shell=True and with validated input
import subprocess  # nosec B404


class OllamaBackend:
    def __init__(self):
        self.cache_dir = config._CACHE_DIR
        self.embedding_model_id = config.EMBEDDING_MODEL_ID
        self.llm_model_id = config.LLM_MODEL_ID
        self.keep_alive = config.KEEP_ALIVE

    def start_server(self):
        """
        Starts the Ollama server with the specified cache directory for model storage.
        This function sets the `OLLAMA_MODELS` environment variable to the provided
        cache directory, locates the `ollama` executable, and launches the Ollama server
        as a subprocess. It waits briefly to allow the server to initialize.

        Raises:
            FileNotFoundError: If the `ollama` executable is not found in the system PATH.
            Exception: For any other unexpected errors during server startup.
        """

        # Set the `OLLAMA_MODELS` to store the Ollama models
        os.environ['OLLAMA_MODELS'] = f"{self.cache_dir}/ollama_models"

        try:
            # Resolved full path to avoid partial path execution
            ollama_path = shutil.which("ollama")
            if ollama_path is None:
                raise FileNotFoundError("ollama executable not found in PATH")

            # full path used, not relying on PATH
            # ollama_path is resolved via shutil.which() and not user-controlled
            serve_process = subprocess.Popen([ollama_path, "serve"])  # nosec B603 B607

            # Optional: wait a few seconds to ensure the server starts
            time.sleep(5)

        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise

    def download_model(self, model_id: str, model_type: str):
        """
        Downloads and preloads an Ollama model based on the specified model type.
        This function pulls the specified Ollama model, then preloads it into memory
        by sending an empty prompt (for LLM models) or an empty list (for embedding models).
        It logs the progress and handles errors, raising a RuntimeError if the download fails.

        Args:
        model_id (str): The identifier of the Ollama model to download.
        model_type (str): The type of the model, either "llm" for language models or "embedding" for embedding models.

        Raises:
            RuntimeError: If the Ollama model download fails.
            Exception: For any unexpected errors during the process.
        """

        try:
            # Download ollama model
            ollama.pull(model_id)

            # Preload the LLM model into memory.
            # Only applicable for LLM models not embeddings.
            response = None
            if model_type == "llm":
                # Preload the model by sending an empty prompt
                response = ollama.generate(model=model_id, keep_alive=self.keep_alive)

            elif model_type == "embedding":
                # Preload the model by sending empty list
                response = ollama.embed(model=model_id, keep_alive=self.keep_alive)

            if response:
                logger.info(f"Ollama: {model_id} run successfully.")

        except subprocess.CalledProcessError as e:
            # Clean ANSI escape sequences and extract the last meaningful error line
            raw_error = e.stderr or str(e)
            clean_error = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', raw_error) # Remove ANSI codes
            lines = clean_error.strip().splitlines()
            err_message = next((line for line in reversed(lines) if "Error:" in line), lines[-1] if lines else "Unknown error")
            logger.error(f"Error downloading Ollama model {model_id}: {err_message}")
            raise RuntimeError(f"Ollama failed: {err_message}") from e

        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise

    def init_models(self):
        """
        Initializes the Ollama models for embeddings and LLMs.
        This function checks if the models are already downloaded, and if not,
        it downloads them using the `download_model` method. It then creates
        instances of `OllamaEmbeddings` and `OllamaLLM` with the specified model IDs.

        Returns:
            tuple: A tuple containing the initialized embedding, LLM, and reranker models.
        """

        # Start the Ollama server
        self.start_server()

        # Download and preload the embedding and llm models
        self.download_model(self.embedding_model_id, "embedding")
        self.download_model(self.llm_model_id, "llm")

        # Initialize embedding with OllamaEmbeddings
        embedding = OllamaEmbeddings(model=self.embedding_model_id)

        # Initialize LLM with OllamaLLM
        llm = OllamaLLM(model=self.llm_model_id)

        # Ollama doesn't support reranker model
        reranker = None

        return embedding, llm, reranker

    @staticmethod
    def list_active_models():
        """
        Retrieves and returns a list of currently active models with their status and remaining duration.
        This function queries the Ollama backend for active models, calculates the remaining time until each model expires,
        and adds this information to the model's dictionary. If the KEEP_ALIVE configuration is set to -1, the duration is
        marked as "forever".

        Returns:
            list[dict]: A list of dictionaries, each representing an active model with its details and remaining duration.
        """

        active_models = ollama.ps()
        updated_models = []

        now = datetime.now(timezone.utc)
        for model in active_models.get("models", []):
            # Convert model from its pydantic class to dictionary for manipulation
            model_dict = model.model_dump()

            # Skip duration calculation if KEEP_ALIVE is set to '-1(always run forever)'
            if config.KEEP_ALIVE == -1:
                model_dict["duration"] = "forever"
                updated_models.append(model_dict)
                continue

            expires_at = model_dict.get("expires_at")
            if expires_at:
                # Calculate time left
                time_left = expires_at - now

                if time_left.total_seconds() > 0:
                    days = time_left.days
                    hours, remainder = divmod(time_left.seconds, 3600)
                    minutes, _ = divmod(remainder, 60)
                    duration_str = f"{days}d {hours}h {minutes}m from now."

                model_dict["duration_left"] = duration_str

            updated_models.append(model_dict)

        return updated_models

    @staticmethod
    def show_model_info(model_id: str):
        """
        Retrieves and returns metadata information for a specified model.

        Args:
            model_id (str): The identifier of the model to retrieve metadata for.

        Returns:
            dict: Metadata information of the specified model as returned by ollama.show().

        Raises:
            Exception: If the model metadata cannot be retrieved.
        """

        try:
            return ollama.show(model_id)

        except Exception as e:
            logger.error(f"Error retrieving model metadata for {model_id}: {e}")
            raise