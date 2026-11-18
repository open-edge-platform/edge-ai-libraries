"""Telemetry — the measurement spine (walkthrough §5).

Metrics are a **strategy**: anything implementing ``MetricsBackend`` (a ``span``
context manager + ``drain``) can be injected into a service. Two implementations
ship here — in-memory ``Telemetry`` (default) and ``NullTelemetry`` (no-op) —
and a deployment can supply its own (OpenTelemetry, Prometheus, …).
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator, Protocol, runtime_checkable


@dataclass
class Span:
    name: str
    duration_ms: float
    ok: bool
    ts_ms: int


@runtime_checkable
class MetricsBackend(Protocol):
    """Strategy interface for metrics backends."""

    def span(self, name: str):  # returns a context manager
        ...

    def drain(self) -> list[Span]:
        ...


@dataclass
class Telemetry:
    service: str
    _spans: list[Span] = field(default_factory=list)

    @contextmanager
    def span(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        ok = True
        try:
            yield
        except Exception:
            ok = False
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000.0
            self._spans.append(
                Span(
                    name=name,
                    duration_ms=duration_ms,
                    ok=ok,
                    ts_ms=int(time.time() * 1000),
                )
            )

    def drain(self) -> list[Span]:
        """Return and clear collected spans (for an exporter to ship)."""
        spans, self._spans = self._spans, []
        return spans


@dataclass
class NullTelemetry:
    """No-op metrics backend for services that opt out of measurement."""

    service: str = "unknown"

    @contextmanager
    def span(self, name: str) -> Iterator[None]:
        yield

    def drain(self) -> list[Span]:
        return []

