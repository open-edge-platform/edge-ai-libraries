import traceback
from pathlib import Path
from typing import Optional, Tuple

from huggingface_hub import hf_hub_download
from transformers import AutoConfig, AutoTokenizer
from optimum.intel import OVModelForSpeechSeq2Seq

from audio_intelligence.core.settings import settings
from audio_intelligence.schemas.types import WhisperModel
from audio_intelligence.utils.hardware_utils import is_intel_gpu_available
from audio_intelligence.utils.logger import logger


# Base model directories
GGML_MODEL_DIR = settings.GGML_MODEL_DIR
OPENVINO_MODEL_DIR = settings.OPENVINO_MODEL_DIR


class ModelManager:
    """
    Manager for downloading and managing Whisper models.
    
    Supports:
    - ggml models from huggingface.co/ggerganov/whisper.cpp for whisper.cpp
    - OpenAI whsiper models and converting them to OpenVINO format using optimum-intel
    """
    
    @staticmethod
    async def download_models() -> None:
        """Download all required models based on configuration."""
        logger.debug("Starting model download process")
        
        # Mapping of model names to their respective repositories
        ggml_repo_id = "ggerganov/whisper.cpp"
        openai_repo_prefix = "openai/whisper-"
        
        # Download ggml models for Whisper.cpp to run on CPU
        await ModelManager._download_ggml_models(ggml_repo_id)
        
        # Check if we should download OpenVINO optimized models to run on GPU
        if is_intel_gpu_available():
            logger.debug("Intel GPU detected, will download OpenVINO models to run on GPU")
            await ModelManager._download_openvino_models(openai_repo_prefix)
    
        logger.info(f"Enabled models downloaded successfully : {[m.value for m in settings.ENABLED_WHISPER_MODELS]}")

    @staticmethod
    async def _download_ggml_models(repo_id: str) -> None:
        """
        Download ggml models for whisper.cpp.
        
        Args:
            repo_id: Hugging Face repository ID for whisper.cpp models
        """
        logger.debug("Downloading ggml models for whisper.cpp")
        
        for model in settings.ENABLED_WHISPER_MODELS:
            model_name = model.value
            logger.debug(f"Processing ggml model: {model_name}")

            # Define model filename based on model name
            model_filename = f"ggml-{model_name}.bin"
            model_local_path = Path(GGML_MODEL_DIR) / model_filename

            # Check if the model already exists
            if model_local_path.exists():
                if model_local_path.stat().st_size > 0:
                    logger.debug(f"Model {model_name} already exists at {model_local_path}, skipping download")
                    continue
        

            try:
                logger.debug(f"Downloading {model_name} ggml model from Hugging Face")
                hf_hub_download(
                    repo_id=repo_id,
                    filename=model_filename,
                    local_dir=GGML_MODEL_DIR,
                )
                logger.debug(f"Successfully downloaded {model_name} to {GGML_MODEL_DIR}")
            except Exception as e:
                logger.error(f"Failed to download {model_name} ggml model: {e}")
                logger.debug(f"Error details: {traceback.format_exc()}")
    
    @staticmethod
    async def _download_openvino_models(repo_prefix: str) -> None:
        """
        Download and convert OpenVINO models using optimum-intel.
        
        Args:
            repo_prefix: Base Hugging Face repository ID for Whisper models
        """
        
        logger.debug("Downloading OpenVINO models for Whisper using optimum-intel")
        
        for model in settings.ENABLED_WHISPER_MODELS:
            model_name = model.value
            logger.debug(f"Processing OpenVINO model: {model_name}")
            
            # Define model directory for the model
            model_dir = Path(OPENVINO_MODEL_DIR) / model_name
            model_dir.mkdir(parents=True, exist_ok=True)
            
            if model_dir.exists() and any(model_dir.iterdir()):
                logger.debug(f"Model {model_name} already exists at {model_dir}, skipping download")
                continue
            
            try:
                # Map the model to the corresponding HF model ID
                hf_model_id = f"{repo_prefix}{model_name}"
                logger.debug(f"Downloading and converting {hf_model_id} to OpenVINO format")
                
                ov_config = {}
                # Download and convert to OpenVINO IR format
                ov_model = OVModelForSpeechSeq2Seq.from_pretrained(
                    hf_model_id, 
                    from_transformers=True,
                    config=ov_config,
                    export=True,
                    load_in_8bit=False,
                    trust_remote_code=True,
                    compile=False,
                )
                
                # Convert model to half precision and save the model
                ov_model.half()
                ov_model.save_pretrained(model_dir)
                
                logger.debug(f"Successfully downloaded and converted {model_name} to {model_dir} in half precision")
            except Exception as e:
                logger.error(f"Failed to download/convert {model_name} to OpenVINO format: {e}")
                logger.debug(f"Error details: {traceback.format_exc()}")
    
    @staticmethod
    def get_model_path(model_name: str, use_gpu: bool = False) -> Path:
        """
        Get the path to a downloaded model.
        
        Args:
            model_name: Name of the model
            use_gpu: Whether to use GPU-optimized model (OpenVINO)
            
        Returns:
            Path to the model file/directory
        """
        if use_gpu:
            return OPENVINO_MODEL_DIR / model_name
        else:
            return GGML_MODEL_DIR / f"ggml-{model_name}.bin"
            
    @staticmethod
    def is_model_downloaded(model: WhisperModel, use_gpu: bool = False) -> bool:
        """
        Check if a model is downloaded and available.
        
        Args:
            model: WhisperModel enum or string model name
            use_gpu: Whether to check for GPU-optimized model (OpenVINO)
            
        Returns:
            True if the model is downloaded, False otherwise
        """
        # Ensure model is a WhisperModel enum
        model_name = model.value if isinstance(model, WhisperModel) else model            
        model_path = ModelManager.get_model_path(model_name, use_gpu)
        
        if use_gpu:
            return model_path.is_dir() and any(model_path.iterdir())
        else:
            return model_path.is_file() and model_path.stat().st_size > 0
   