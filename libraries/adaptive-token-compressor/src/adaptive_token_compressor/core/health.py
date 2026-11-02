# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Startup readiness probes for compressors / backends / predictors."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class HealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class HealthStatus:
    state: HealthState
    component: str
    message: str | None = None
    latency_ms: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def healthy(cls, component: str, **details: Any) -> "HealthStatus":
        """Factory for HEALTHY. `latency_ms` is pulled out of `**details` if present."""
        latency_ms = details.pop("latency_ms", None)
        return cls(
            state=HealthState.HEALTHY,
            component=component,
            message=None,
            latency_ms=latency_ms,
            details=details,
        )

    @classmethod
    def unhealthy(cls, component: str, message: str, **details: Any) -> "HealthStatus":
        """Factory for UNHEALTHY (unreachable / misconfigured); `message` required."""
        latency_ms = details.pop("latency_ms", None)
        return cls(
            state=HealthState.UNHEALTHY,
            component=component,
            message=message,
            latency_ms=latency_ms,
            details=details,
        )

    @classmethod
    def degraded(cls, component: str, message: str, **details: Any) -> "HealthStatus":
        """Factory for DEGRADED (responsive but partial); `message` required."""
        latency_ms = details.pop("latency_ms", None)
        return cls(
            state=HealthState.DEGRADED,
            component=component,
            message=message,
            latency_ms=latency_ms,
            details=details,
        )


@runtime_checkable
class HealthCheckable(Protocol):
    def health_check(self, *, timeout: float = 5.0) -> HealthStatus: ...
