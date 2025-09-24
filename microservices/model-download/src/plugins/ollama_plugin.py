
import os
import subprocess
import time
from typing import Optional, Dict, Any, List, Callable
from pathlib import Path
from src.utils.helper import cleanup_model_directory
from src.utils.logging import logger
from src.core.interfaces import ModelDownloadPlugin, DownloadTask


class OllamaPlugin(ModelDownloadPlugin):
    """Plugin for downloading Ollama models"""
    
    @property
    def plugin_name(self) -> str:
        return "ollama"
    
    @property
    def plugin_type(self) -> str:
        return "downloader"
    
    def can_handle(self, model_name: str, hub: str, **kwargs) -> bool:
        """Check if this plugin can handle the given model"""
        # Case-insensitive check for the hub name
        if hub.lower() == "ollama":
            return True
        return False
    
    def download(self, model_name: str, output_dir: str, progress_callback=None, **kwargs) -> Dict[str, Any]:
        """Download the Ollama model"""
        process = None
        model_downloaded_path = os.path.join(output_dir, model_name.replace("/", "_"))
        
        try:
            
            logger.info(f"Model will be downloaded to: {model_downloaded_path}")
            
            os.environ["OLLAMA_MODELS"] = model_downloaded_path

            logger.info(f"Directory for Ollama model: {model_downloaded_path}")
            try:
                os.makedirs(model_downloaded_path, exist_ok=True)
            except OSError as e:
                logger.error(f"Failed to create directory {model_downloaded_path}: {str(e)}")
                raise RuntimeError(f"Failed to create model directory: {str(e)}")

            logger.info("Starting ollama server")
            process = subprocess.Popen(["ollama", "serve"])

            # Sleep for 1 second to allow the server to be start
            time.sleep(1)

            logger.info(f"Starting download for Ollama model: {model_name}")
            subprocess.run(["ollama", "pull", model_name], check=True)
            logger.info(f"Ollama model {model_name} downloaded successfully.")

            return {
                "model_name": model_name,
                "source": "ollama",
                "download_path": model_downloaded_path,
                "success": True
            }
        
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to download Ollama model {model_name}: {str(e)}")
            raise RuntimeError(f"Failed to download Ollama model: {str(e)}")
        finally:
            if process is not None:
                logger.info("Stopping ollama server")
                process.terminate()
    
    def get_download_tasks(self, model_name: str, **kwargs) -> List[DownloadTask]:
        """
        Get list of download tasks for a model.
        Ollama does not support task-based downloading.
        """
        raise NotImplementedError("Ollama plugin does not support task-based downloading")
    
    def download_task(self, task: DownloadTask, output_dir: str, **kwargs) -> str:
        """
        Download a single task file.
        Ollama does not support task-based downloading.
        """
        raise NotImplementedError("Ollama plugin does not support task-based downloading")
    
    def post_process(self, model_name: str, output_dir: str, downloaded_paths: List[str], **kwargs) -> Dict[str, Any]:
        """
        Post-process the downloaded files.
        For Ollama, this is usually handled by the download process directly.
        """
        return {
            "model_name": model_name,
            "source": "ollama",
            "download_path": output_dir,
            "success": True
        }