# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Compressor exception family + fallback contract.

The class hierarchy encodes the fallback contract:
  - BackendError / PredictorError: caught inside compressor, surfaced via
    `metrics.error`; never re-raised to the caller.
  - ConfigError: raised at construction time, propagates to the caller (fail-fast).
"""


class CompressorError(Exception):
    """Base class for all compressor exceptions."""


class BackendError(CompressorError):
    """Backend service (HTTP / LLM) call failed.

    Typically caught inside the compressor and turned into
    `metrics.error` / `details["backend_errors"]`. Not surfaced to the caller.
    """

    def __init__(self, message: str, *, component: str, cause: Exception | None = None):
        super().__init__(message)
        self.component = component
        self.cause = cause


class PredictorError(BackendError):
    """Tools-subpackage predictor failure (HTTP / parse / threshold)."""


class ConfigError(CompressorError):
    """Invalid configuration. Raised at construction time; fail-fast."""
