# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Compressor contract: input / output containers + protocol."""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .health import HealthStatus
from .metrics import CompressorMetrics


@dataclass
class CompressionContext:
    """Compressor input. Only `messages` + `tools`; OpenAI protocol fields stay with the caller."""

    messages: list[dict]
    tools: list[dict] | None = None

    @classmethod
    def from_openai_request(cls, request: dict) -> "CompressionContext":
        """Pull `messages` and optional `tools` from an OpenAI Chat Completions request dict."""
        ...


@dataclass
class CompressorResult:
    """Compressor output. Symmetric with `CompressionContext`."""

    messages: list[dict]
    tools: list[dict] | None = None
    metrics: CompressorMetrics | None = None


@runtime_checkable
class BaseCompressor(Protocol):
    """Structural type every compressor implements."""

    name: str

    def compress(self, ctx: CompressionContext) -> CompressorResult: ...

    def health_check(self, *, timeout: float = 5.0) -> HealthStatus: ...
