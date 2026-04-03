"""VLM backend factory."""

import logging
from typing import Literal

from app.services.vlm.base import BaseVLMBackend
from app.services.vlm.openai import OpenAIBackend
from app.services.vlm.openvino_local import OpenVINOLocalBackend
from app.services.vlm.ovms import OVMSBackend

logger = logging.getLogger(__name__)


class VLMBackendFactory:
    """Factory for creating VLM backend instances."""
    
    _instances: dict[str, BaseVLMBackend] = {}
    
    @classmethod
    def create(
        cls,
        backend: Literal["ovms", "openvino_local", "openai"] = "ovms",
    ) -> BaseVLMBackend:
        """
        Create or return cached VLM backend instance.
        
        Args:
            backend: Backend type (ovms, openvino_local, openai)
        
        Returns:
            BaseVLMBackend instance
        """
        if backend in cls._instances:
            return cls._instances[backend]
        
        logger.info(f"Creating VLM backend: {backend}")
        
        if backend == "ovms":
            instance = OVMSBackend()
        elif backend == "openvino_local":
            instance = OpenVINOLocalBackend()
        elif backend == "openai":
            instance = OpenAIBackend()
        else:
            raise ValueError(f"Unknown VLM backend: {backend}")
        
        cls._instances[backend] = instance
        return instance
    
    @classmethod
    def clear_cache(cls):
        """Clear cached backend instances."""
        cls._instances.clear()
