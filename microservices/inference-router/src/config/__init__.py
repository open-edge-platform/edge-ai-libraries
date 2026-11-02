# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Configuration module for inference router."""

from src.config.base import (
    RouterConfig,
    ProviderConfig,
    PluginConfig,
    ProviderAuthConfig,
    TelemetryConfig,
    TelemetryBackendType,
    RoutingConfig,
)
from src.config.loader import load_config

__all__ = [
    "RouterConfig",
    "ProviderConfig",
    "PluginConfig",
    "ProviderAuthConfig",
    "TelemetryConfig",
    "TelemetryBackendType",
    "RoutingConfig",
    "load_config",
]
