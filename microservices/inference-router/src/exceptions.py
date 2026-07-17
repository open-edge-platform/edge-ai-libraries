# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Exception classes for the inference router."""


class InferenceRouterError(Exception):
    """Base exception for all inference router errors."""

    pass


class ProviderError(InferenceRouterError):
    """Raised when a provider operation fails.

    ``status_code`` carries the upstream HTTP status (e.g. litellm's 400 for a
    bad request) so the API layer can forward client errors instead of masking
    every provider failure as a 500.
    """

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ConfigurationError(InferenceRouterError):
    """Raised when configuration is invalid."""

    pass


class RoutingError(InferenceRouterError):
    """Raised when routing decision fails."""

    pass
