"""OVMS (OpenVINO Model Server) backend implementation."""

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.services.vlm.base import BaseVLMBackend

logger = logging.getLogger(__name__)


class OVMSBackend(BaseVLMBackend):
    """OVMS VLM backend using OpenAI-compatible API."""
    
    def __init__(self):
        """Initialize OVMS backend."""
        self.endpoint = settings.ovms_endpoint
        self.model_name = settings.ovms_model_name
        self.timeout = settings.ovms_timeout
        self.api_url = f"{self.endpoint}/v3/chat/completions"
        # Disable proxy for internal OVMS requests (trust_env=False ignores HTTP_PROXY env vars)
        self._client = httpx.AsyncClient(timeout=self.timeout, trust_env=False)
        
        logger.info(f"Initialized OVMS backend: {self.endpoint}")
    
    @property
    def name(self) -> str:
        """Get backend name."""
        return "ovms"
    
    def is_available(self) -> bool:
        """Check if OVMS backend is configured (no network call)."""
        return True
    
    async def generate_text(
        self,
        prompt: str,
        max_tokens: int = 100,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> str:
        """
        Generate text using OVMS endpoint.
        
        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional parameters
        
        Returns:
            Generated text response
        """
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        
        logger.debug(f"OVMS request: {self.api_url}")
        
        try:
            response = await self._client.post(
                self.api_url,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Extract response text
            if "choices" in data and len(data["choices"]) > 0:
                message = data["choices"][0].get("message", {})
                content = message.get("content", "")
                logger.debug(f"OVMS response: {content}")
                return content
            
            logger.error(f"Unexpected OVMS response format: {data}")
            raise ValueError("No content in OVMS response")
        
        except httpx.HTTPStatusError as e:
            logger.error(f"OVMS HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"OVMS request failed: {e}", exc_info=True)
            raise
