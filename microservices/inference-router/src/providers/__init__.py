# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Provider registry and factory."""

from typing import Optional

from src.config import ProviderConfig
from src.providers.base import ProviderAdapter, ProviderMetadata
from src.providers.litellm_provider import LitellmProvider
from src.exceptions import ConfigurationError


def create_provider(provider_config: ProviderConfig) -> Optional[ProviderAdapter]:
    """
    Create a provider adapter instance from configuration.

    All provider types are routed through ``LitellmProvider``, which delegates
    to litellm. Set ``type`` in config.yaml to a value litellm recognises
    (``hosted_vllm``, ``openai``, ``ollama``, ``minimax``, ``anthropic``, ...).

    Returns None if the provider is disabled.
    """
    if not provider_config.enabled:
        return None

    if not provider_config.type:
        raise ConfigurationError(
            f"Provider '{provider_config.name}' missing required 'type' field"
        )

    return LitellmProvider(provider_config)


__all__ = [
    "ProviderAdapter",
    "ProviderMetadata",
    "LitellmProvider",
    "create_provider",
]
