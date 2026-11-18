# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Immutable capability groups populated by the context constructor."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .result_stub import StubGuidance

CompressionMode = Literal["none", "backend_only", "claw_only", "claw_with_backend"]


@dataclass(frozen=True)
class ContextWindowConfig:
    protect_recent_tool_turns: int
    compress_stride_tool_turns: int


@dataclass(frozen=True)
class ResultRulesConfig:
    enabled: bool
    status: bool
    error: bool
    web_search_strip: bool


@dataclass(frozen=True)
class LargeResultStubConfig:
    enabled: bool
    guidance: StubGuidance
    min_tokens: int
    keep_tool_turns: int
    exempt_edited_files: bool


@dataclass(frozen=True)
class CompressBackendConfig:
    url: str
    rate: float
    timeout: float


@dataclass(frozen=True)
class ContentCompressionConfig:
    mode: CompressionMode
    min_chars: int
    compress_backend: CompressBackendConfig


@dataclass(frozen=True)
class ToolResultPolicy:
    enabled: bool
    excluded_tools: tuple[str, ...]
    rules: ResultRulesConfig
    large_result_stub: LargeResultStubConfig
    compression: ContentCompressionConfig
