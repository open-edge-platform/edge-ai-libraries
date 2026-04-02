"""OpenVINO GenAI local backend implementation."""

import logging
from pathlib import Path
from typing import Any, Optional

from app.core.config import settings
from app.services.vlm.base import BaseVLMBackend

logger = logging.getLogger(__name__)


class OpenVINOLocalBackend(BaseVLMBackend):
    """OpenVINO GenAI local VLM backend."""
    
    def __init__(self):
        """Initialize OpenVINO local backend."""
        self.model_path = settings.openvino_model_path
        self.device = settings.openvino_device
        self.max_new_tokens = settings.openvino_max_new_tokens
        self.temperature = settings.openvino_temperature
        self._pipeline: Optional[Any] = None
        
        try:
            from openvino_genai import VLMPipeline, GenerationConfig
            
            self._vlm_pipeline_class = VLMPipeline
            self._generation_config_class = GenerationConfig
            
            if Path(self.model_path).exists():
                logger.info(f"Loading OpenVINO model from {self.model_path}")
                self._pipeline = VLMPipeline(
                    models_path=self.model_path,
                    device=self.device,
                )
                logger.info("OpenVINO model loaded successfully")
            else:
                logger.error(f"Model path does not exist: {self.model_path}")
        
        except ImportError:
            logger.warning("openvino-genai not installed, local backend unavailable")
        except Exception as e:
            logger.error(f"Failed to initialize OpenVINO local backend: {e}", exc_info=True)
    
    @property
    def name(self) -> str:
        """Get backend name."""
        return "openvino_local"
    
    def is_available(self) -> bool:
        """Check if OpenVINO pipeline is loaded."""
        return self._pipeline is not None
    
    async def generate_text(
        self,
        prompt: str,
        max_tokens: int = 100,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> str:
        """
        Generate text using local OpenVINO pipeline.
        
        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional parameters
        
        Returns:
            Generated text response
        """
        if not self.is_available():
            raise RuntimeError("OpenVINO pipeline not available")
        
        gen_config = self._generation_config_class(
            max_new_tokens=max_tokens,
            temperature=temperature,
            do_sample=temperature > 0,
        )
        
        logger.debug("Running OpenVINO local inference")
        
        try:
            output = self._pipeline.generate(
                prompt,
                generation_config=gen_config,
            )
            
            response = output.texts[0] if hasattr(output, "texts") else str(output)
            logger.debug(f"OpenVINO response: {response}")
            
            return response
        
        except Exception as e:
            logger.error(f"OpenVINO inference failed: {e}", exc_info=True)
            raise
