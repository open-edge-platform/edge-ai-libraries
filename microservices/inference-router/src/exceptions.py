# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Exception classes for the inference router."""


class InferenceRouterError(Exception):
    """Base exception for all inference router errors."""

    pass


class ProviderError(InferenceRouterError):
    """Raised when a provider operation fails."""

    pass


class ConfigurationError(InferenceRouterError):
    """Raised when configuration is invalid."""

    pass


class RoutingError(InferenceRouterError):
    """Raised when routing decision fails."""

    pass
