# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Compression backend: protocol + Lingua HTTP client + noop."""
from __future__ import annotations

import logging
import requests
from typing import Protocol, runtime_checkable

from .exceptions import BackendError
from .health import HealthState, HealthStatus

logger = logging.getLogger("adaptive_token_compressor.core.backends")


@runtime_checkable
class CompressionBackend(Protocol):
    # Per-backend identity mixed into cache keys so backends producing
    # different output for the same text never collide on a shared entry.
    cache_tag: str

    def compress(
        self,
        text: str,
        *,
        mode: str | None = None,
        rate: float,
        force_tokens: list[str] | None = None,
        force_reserve_digit: bool = False,
        digit_neighbor_radius: int = 0,
    ) -> str: ...

    def health_check(self, *, timeout: float = 5.0) -> HealthStatus: ...


class LinguaHTTPBackend:

    # Historical prefix kept so existing caches stay valid.
    cache_tag: str = "lingua"

    def __init__(
        self,
        *,
        lingua_url: str = "http://localhost:8001/compress",
        timeout: float = 60.0,
        health_endpoint: str | None = None,
    ) -> None:
        self._lingua_url = lingua_url
        self._timeout = timeout
        # None → derive f"{base}/health"
        if health_endpoint is None:
            base = lingua_url.rstrip("/compress").rstrip("/")
            health_endpoint = f"{base}/health"
        self._health_endpoint = health_endpoint

    def compress(
        self,
        text: str,
        *,
        mode: str | None = None,
        rate: float,
        force_tokens: list[str] | None = None,
        force_reserve_digit: bool = False,
        digit_neighbor_radius: int = 0,
    ) -> str:
        payload = {
            "text": text,
            "rate": rate,
            "force_reserve_digit": force_reserve_digit,
            "digit_neighbor_radius": digit_neighbor_radius,
        }
        if mode is not None:
            payload["mode"] = mode
        if force_tokens is not None:
            payload["force_tokens"] = force_tokens
        component = f"backend@{self._lingua_url}"
        try:
            resp = requests.post(self._lingua_url, json=payload, timeout=self._timeout)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise BackendError(f"HTTP request failed: {e}", component=component, cause=e) from e

        try:
            body = resp.json()
        except ValueError as e:
            raise BackendError(f"Invalid JSON response: {e}", component=component, cause=e) from e

        # Prefer compressed_prompt, fall back to compressed_text.
        result = body.get("compressed_prompt") or body.get("compressed_text")
        if not result:
            raise BackendError(
                "Response missing compressed_prompt/compressed_text", component=component
            )
        return result

    def health_check(self, *, timeout: float = 5.0) -> HealthStatus:
        component = f"backend@{self._lingua_url}"
        try:
            resp = requests.get(self._health_endpoint, timeout=timeout)
            resp.raise_for_status()
            body = resp.json()
            status_val = body.get("status", "unknown")
            if status_val == "ok":
                return HealthStatus.healthy(component, **body)
            return HealthStatus.degraded(component, f"status={status_val}", **body)
        except Exception as e:
            return HealthStatus.unhealthy(component, str(e))


class NoopBackend:

    cache_tag: str = "noop"

    def compress(
        self,
        text: str,
        *,
        mode: str | None = None,
        rate: float,
        force_tokens: list[str] | None = None,
        force_reserve_digit: bool = False,
        digit_neighbor_radius: int = 0,
    ) -> str:
        return text

    def health_check(self, *, timeout: float = 5.0) -> HealthStatus:
        return HealthStatus.healthy("noop_backend")


def build_backend(
    compressor_backend: str,
    *,
    lingua_url: str,
    timeout: float,
) -> CompressionBackend:
    """Construct the backend selected by `compressor_backend` ("lingua"), which
    satisfies the `CompressionBackend` protocol. An unknown backend name raises
    ValueError; callers wrap it as ConfigError.
    """
    if compressor_backend == "lingua":
        return LinguaHTTPBackend(lingua_url=lingua_url, timeout=timeout)
    raise ValueError(
        f"Unknown compressor_backend {compressor_backend!r}; expected 'lingua'"
    )
