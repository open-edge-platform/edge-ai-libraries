# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Inference Router: A pluggable inference router for chat completion requests."""

__version__ = "0.1.0"

from src.exceptions import (
    InferenceRouterError,
    ProviderError,
    ConfigurationError,
    RoutingError,
)

__all__ = [
    "InferenceRouterError",
    "ProviderError",
    "ConfigurationError",
    "RoutingError",
]
