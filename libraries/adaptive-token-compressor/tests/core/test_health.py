"""Tests for core/health.py — covers plan §13 row `core/health`."""
from __future__ import annotations

import pytest

from adaptive_token_compressor.core.health import (
    HealthCheckable,
    HealthState,
    HealthStatus,
)


# ─────────────────────────────────────────────────────────────────────────────
# HealthState enum
# ─────────────────────────────────────────────────────────────────────────────


class TestHealthState:
    def test_four_states(self):
        assert {s.value for s in HealthState} == {
            "healthy",
            "degraded",
            "unhealthy",
            "unknown",
        }

    def test_str_subclass(self):
        # Convenient for `if status.state == "healthy"` style checks.
        assert HealthState.HEALTHY == "healthy"


# ─────────────────────────────────────────────────────────────────────────────
# HealthStatus dataclass
# ─────────────────────────────────────────────────────────────────────────────


class TestHealthStatusFrozen:
    def test_frozen(self):
        s = HealthStatus(state=HealthState.HEALTHY, component="x")
        with pytest.raises(Exception):  # FrozenInstanceError
            s.state = HealthState.DEGRADED  # type: ignore[misc]

    def test_default_message_none(self):
        s = HealthStatus(state=HealthState.HEALTHY, component="x")
        assert s.message is None
        assert s.latency_ms is None
        assert s.details == {}

    def test_default_details_independent(self):
        s1 = HealthStatus(state=HealthState.HEALTHY, component="x")
        s2 = HealthStatus(state=HealthState.HEALTHY, component="y")
        # field(default_factory=dict) → distinct dicts per instance
        # (s1/s2 are frozen, so we can only assert they don't share identity).
        assert s1.details is not s2.details


# ─────────────────────────────────────────────────────────────────────────────
# Factory: healthy()
# ─────────────────────────────────────────────────────────────────────────────


class TestHealthyFactory:
    def test_minimal(self):
        s = HealthStatus.healthy("backend@http://localhost:8000")
        assert s.state is HealthState.HEALTHY
        assert s.component == "backend@http://localhost:8000"
        assert s.message is None
        assert s.latency_ms is None
        assert s.details == {}

    def test_latency_pulled_from_details(self):
        s = HealthStatus.healthy("x", latency_ms=12.5)
        assert s.latency_ms == 12.5
        assert "latency_ms" not in s.details

    def test_extra_details_kept(self):
        s = HealthStatus.healthy("x", model_id="qwen35", server="0.5.0")
        assert s.details == {"model_id": "qwen35", "server": "0.5.0"}

    def test_latency_plus_details(self):
        s = HealthStatus.healthy("x", latency_ms=10.0, build="abc123")
        assert s.latency_ms == 10.0
        assert s.details == {"build": "abc123"}


# ─────────────────────────────────────────────────────────────────────────────
# Factory: unhealthy()
# ─────────────────────────────────────────────────────────────────────────────


class TestUnhealthyFactory:
    def test_minimal(self):
        s = HealthStatus.unhealthy("x", "connection refused")
        assert s.state is HealthState.UNHEALTHY
        assert s.message == "connection refused"

    def test_message_required(self):
        # `message` is positional — TypeError if omitted.
        with pytest.raises(TypeError):
            HealthStatus.unhealthy("x")  # type: ignore[call-arg]

    def test_latency_and_details(self):
        s = HealthStatus.unhealthy("x", "timeout", latency_ms=30000.0, attempt=3)
        assert s.latency_ms == 30000.0
        assert s.details == {"attempt": 3}


# ─────────────────────────────────────────────────────────────────────────────
# Factory: degraded()
# ─────────────────────────────────────────────────────────────────────────────


class TestDegradedFactory:
    def test_minimal(self):
        s = HealthStatus.degraded("x", "loading model")
        assert s.state is HealthState.DEGRADED
        assert s.message == "loading model"

    def test_message_required(self):
        with pytest.raises(TypeError):
            HealthStatus.degraded("x")  # type: ignore[call-arg]

    def test_with_latency(self):
        s = HealthStatus.degraded("x", "partial", latency_ms=5.0)
        assert s.latency_ms == 5.0


# ─────────────────────────────────────────────────────────────────────────────
# HealthCheckable Protocol — runtime_checkable
# ─────────────────────────────────────────────────────────────────────────────


class TestHealthCheckableProtocol:
    def test_object_with_health_check_passes(self):
        class C:
            def health_check(self, *, timeout: float = 5.0) -> HealthStatus:
                return HealthStatus.healthy("c")

        assert isinstance(C(), HealthCheckable)

    def test_object_without_health_check_fails(self):
        class C:
            pass

        assert not isinstance(C(), HealthCheckable)

    def test_callable_attribute_alone_is_enough_for_runtime_check(self):
        # @runtime_checkable Protocols only check method *presence*, not signature.
        class Loose:
            health_check = lambda self, *, timeout=5.0: None  # noqa: E731

        assert isinstance(Loose(), HealthCheckable)
