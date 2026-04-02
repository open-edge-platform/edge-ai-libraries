"""OpenAI API backend implementation (fallback)."""

import logging
from typing import Any, Optional

from app.core.config import settings
from app.services.vlm.base import BaseVLMBackend

logger = logging.getLogger(__name__)


class OpenAIBackend(BaseVLMBackend):
    """OpenAI API backend for semantic matching."""
    
    def __init__(self):
        """Initialize OpenAI backend."""
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model
        self.max_tokens = settings.openai_max_tokens
        self._client: Optional[Any] = None
        
        if self.api_key:
            try:
                from openai import AsyncOpenAI
                
                self._client = AsyncOpenAI(api_key=self.api_key)
                logger.info(f"Initialized OpenAI backend with model: {self.model}")
            except ImportError:
                logger.warning("openai package not installed, OpenAI backend unavailable")
        else:
            logger.warning("OpenAI API key not configured")
    
    @property
    def name(self) -> str:
        """Get backend name."""
        return "openai"
    
    def is_available(self) -> bool:
        """Check if OpenAI client is configured."""
        return self._client is not None
    
    async def generate_text(
        self,
        prompt: str,
        max_tokens: int = 100,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> str:
        """
        Generate text using OpenAI API.
        
        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional parameters
        
        Returns:
            Generated text response
        """
        if not self.is_available():
            raise RuntimeError("OpenAI client not available")
        
        logger.debug(f"OpenAI request: model={self.model}, max_tokens={max_tokens}")
        
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            
            content = response.choices[0].message.content
            logger.debug(f"OpenAI response: {content}")
            
            return content
        
        except Exception as e:
            logger.error(f"OpenAI request failed: {e}", exc_info=True)
            raise
