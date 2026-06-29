# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Abstract base class for provider adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, List, Dict, Any, Optional

from src.models import ChatCompletionRequest, ChatCompletionResponse, ChatCompletionStreamChunk


@dataclass
class ProviderMetadata:
    """Provider attributes used by routing strategies."""

    labels: List[str] = field(default_factory=list)
    cost: Optional[float] = None
    performance: Optional[float] = None
    capability: Dict[str, Any] = field(default_factory=dict)
    attributes: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, metadata: Dict[str, Any]) -> "ProviderMetadata":
        """Build provider metadata from a dictionary."""
        known_keys = {"labels", "cost", "performance", "capability"}
        labels = metadata.get("labels", [])
        capability = metadata.get("capability", {})

        return cls(
            labels=list(labels) if isinstance(labels, list) else [],
            cost=metadata.get("cost"),
            performance=metadata.get("performance"),
            capability=dict(capability) if isinstance(capability, dict) else {},
            attributes={
                key: value for key, value in metadata.items() if key not in known_keys
            },
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return routing metadata as a dictionary."""
        payload = dict(self.attributes)

        if self.labels:
            payload["labels"] = list(self.labels)
        if self.cost is not None:
            payload["cost"] = self.cost
        if self.performance is not None:
            payload["performance"] = self.performance
        if self.capability:
            payload["capability"] = dict(self.capability)

        return payload


class ProviderAdapter(ABC):
    """Abstract base class for LLM provider adapters."""

    def __init__(self, name: str, metadata: Optional[ProviderMetadata] = None):
        """
        Initialize the provider adapter.

        Args:
            name: Name identifier for this provider
            metadata: Routing metadata for this provider
        """
        self.name = name
        self.metadata = metadata or ProviderMetadata()

    @abstractmethod
    async def chat(
        self,
        request: ChatCompletionRequest,
    ) -> ChatCompletionResponse:
        """
        Send a chat completion request and get a single response.

        Args:
            request: OpenAI-compatible chat completion request

        Returns:
            ChatCompletionResponse

        Raises:
            ProviderError: If the request fails
        """
        pass

    @abstractmethod
    async def chat_stream(
        self,
        request: ChatCompletionRequest,
    ) -> AsyncIterator[ChatCompletionStreamChunk]:
        """
        Send a chat completion request and get streaming responses.

        Args:
            request: OpenAI-compatible chat completion request

        Yields:
            ChatCompletionStreamChunk for each chunk

        Raises:
            ProviderError: If the request fails
        """
        pass

    @abstractmethod
    async def list_models(self) -> List[Dict[str, Any]]:
        """
        List available models from the provider.

        Returns:
            List of model information dicts

        Raises:
            ProviderError: If the request fails
        """
        pass

    async def health_check(self) -> bool:
        """
        Check if provider is healthy and accessible.

        Returns:
            True if healthy, False otherwise
        """
        try:
            await self.list_models()
            return True
        except Exception:
            return False
