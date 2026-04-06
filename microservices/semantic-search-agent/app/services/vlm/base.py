"""Base VLM backend interface."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseVLMBackend(ABC):
    """Abstract base class for VLM backends."""
    
    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        max_tokens: int = 100,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> str:
        """
        Generate text response from VLM.
        
        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional backend-specific parameters
        
        Returns:
            Generated text response
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if VLM backend is available.
        
        Returns:
            True if backend is ready, False otherwise
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Get backend name."""
        pass
