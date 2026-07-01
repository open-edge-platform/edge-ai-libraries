# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Event Definitions

Defines various observable events for telemetry recording
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Event:
    """Base Event"""
    event_type: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    request_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RouteEvent(Event):
    """Routing Event"""
    stage: str = ""  # "route"
    target: str = ""  # "local", "cloud"
    reason: str | None = None
    confidence: float | None = None

    def __post_init__(self):
        self.event_type = "route"


@dataclass
class InferenceEvent(Event):
    """Inference Event"""
    model_name: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float | None = None
    success: bool = True
    error: str | None = None

    def __post_init__(self):
        self.event_type = "inference"

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class EvaluationEvent(Event):
    """Evaluation Event"""
    evaluator_name: str = ""
    score: float = 0.0  # 0.0-1.0
    passed: bool = False
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.event_type = "evaluation"


@dataclass
class CompressionEvent(Event):
    """Compression Event — one per compression pipeline invocation."""
    strategy: str = ""  # e.g. "lingua", "tool_compact", "lingua+tool_compact"

    # System prompt dimension
    original_system_tokens: int = 0
    compressed_system_tokens: int = 0
    original_system_chars: int = 0
    compressed_system_chars: int = 0

    # Tool schema dimension
    original_tool_schema_tokens: int = 0
    compressed_tool_schema_tokens: int = 0
    original_tool_count: int = 0
    compressed_tool_count: int = 0

    # Full input dimension (messages + tools)
    original_total_tokens: int = 0
    compressed_total_tokens: int = 0

    # Per-role token breakdown
    original_role_tokens: dict[str, int] = field(default_factory=dict)
    compressed_role_tokens: dict[str, int] = field(default_factory=dict)

    # Timing
    duration_ms: float = 0.0  # total (token counting + compression)
    compress_duration_ms: float = 0.0  # actual compression only

    # Strategy-specific details
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.event_type = "compression"

    @property
    def system_tokens_saved(self) -> int:
        return self.original_system_tokens - self.compressed_system_tokens

    @property
    def system_reduction_pct(self) -> float:
        if self.original_system_tokens == 0:
            return 0.0
        return (self.system_tokens_saved / self.original_system_tokens) * 100

    @property
    def system_rest_pct(self) -> float:
        """Percentage of system tokens remaining after compression."""
        if self.original_system_tokens == 0:
            return 100.0
        return (self.compressed_system_tokens / self.original_system_tokens) * 100

    @property
    def total_tokens_saved(self) -> int:
        return self.original_total_tokens - self.compressed_total_tokens

    @property
    def total_reduction_pct(self) -> float:
        if self.original_total_tokens == 0:
            return 0.0
        return (self.total_tokens_saved / self.original_total_tokens) * 100

    @property
    def total_rest_pct(self) -> float:
        if self.original_total_tokens == 0:
            return 100.0
        return (self.compressed_total_tokens / self.original_total_tokens) * 100

    @property
    def tool_schema_rest_pct(self) -> float:
        if self.original_tool_schema_tokens == 0:
            return 100.0
        return (self.compressed_tool_schema_tokens / self.original_tool_schema_tokens) * 100


@dataclass
class RequestCompletedEvent(Event):
    """Request Completed Event (summary)"""
    # Diagnostic only — "direct" (client picked the provider) or
    # "routed" (DecisionEngine picked the provider). Telemetry buckets by
    # ``provider_name``, not by this string.
    route_path: str = ""
    provider_name: str = ""  # Configured provider name from config.yaml
    models_used: list[str] = field(default_factory=list)
    final_model: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_latency_ms: float | None = None
    ttft_ms: float | None = None  # Time To First Token
    tpot_ms: float | None = None  # Time Per Output Token

    def __post_init__(self):
        self.event_type = "request_completed"

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens
