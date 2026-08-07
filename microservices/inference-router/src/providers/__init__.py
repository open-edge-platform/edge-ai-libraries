# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Provider registry and factory."""

from typing import Optional, Union

from src.config import ProviderConfig
from src.providers.base import ProviderAdapter, ProviderMetadata
from src.providers.litellm_provider import LitellmProvider
from src.providers.passthrough_provider import (
    PASSTHROUGH_SERVICES,
    PASSTHROUGH_TYPES,
    PassthroughProvider,
    PassthroughSpec,
)
from src.exceptions import ConfigurationError


def create_provider(
    provider_config: ProviderConfig,
) -> Optional[Union[ProviderAdapter, PassthroughProvider]]:
    """
    Create a provider instance from configuration.

    Dispatch is by ``type``:

    - A ``type`` in :data:`PASSTHROUGH_TYPES` (``transcription``, ``tts``,
      ``embeddings``, ``rerank``, ``ocr``) builds a :class:`PassthroughProvider`,
      which forwards requests verbatim to a backing service.
    - Any other ``type`` builds a :class:`LitellmProvider`, which delegates to
      litellm (set ``type`` to a value litellm recognises: ``hosted_vllm``,
      ``openai``, ``ollama``, ``minimax``, ``anthropic``, ...).

    Returns None if the provider is disabled.
    """
    if not provider_config.enabled:
        return None

    if not provider_config.type:
        raise ConfigurationError(
            f"Provider '{provider_config.name}' missing required 'type' field"
        )

    if provider_config.type in PASSTHROUGH_TYPES:
        return PassthroughProvider(provider_config)

    return LitellmProvider(provider_config)


__all__ = [
    "ProviderAdapter",
    "ProviderMetadata",
    "LitellmProvider",
    "PassthroughProvider",
    "PassthroughSpec",
    "PASSTHROUGH_SERVICES",
    "PASSTHROUGH_TYPES",
    "create_provider",
]
