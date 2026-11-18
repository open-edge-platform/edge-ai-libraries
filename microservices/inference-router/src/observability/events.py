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

    # Token breakdown BEFORE router plugins (raw request) and AFTER (compressed
    # request forwarded to the backend). Same tiktoken unit → before/after are
    # directly comparable to see how much the compressors actually saved.
    before_router_system_tokens: int = 0
    before_router_tool_tokens: int = 0
    before_router_context_tokens: int = 0
    before_router_overall_tokens: int = 0
    after_router_system_tokens: int = 0
    after_router_tool_tokens: int = 0
    after_router_context_tokens: int = 0
    after_router_overall_tokens: int = 0

    def __post_init__(self):
        self.event_type = "request_completed"

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens
