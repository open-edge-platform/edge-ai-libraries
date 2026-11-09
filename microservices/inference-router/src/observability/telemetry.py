# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Telemetry Core

Independent observability layer that can be used by any module
"""

import dataclasses as _dc
import fcntl
import json
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .events import (
    Event,
    RouteEvent,
    InferenceEvent,
    EvaluationEvent,
    RequestCompletedEvent,
)

logger = logging.getLogger("telemetry")


# Note on long-running accumulation: every counter below is a Python ``int``,
# which is arbitrary-precision and cannot overflow no matter how long the
# process runs — so there is no numeric overflow to guard against here.
@dataclass
class ProviderTokenStats:
    """Per-provider token, latency, TTFT and TPOT counters."""
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    total_latency_ms: float = 0.0
    total_ttft_ms: float = 0.0
    total_tpot_ms: float = 0.0
    ttft_count: int = 0
    tpot_count: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def avg_tokens_per_request(self) -> float:
        return self.total_tokens / self.requests if self.requests else 0.0

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.requests if self.requests else 0.0

    @property
    def avg_ttft_ms(self) -> float:
        return self.total_ttft_ms / self.ttft_count if self.ttft_count else 0.0

    @property
    def avg_tpot_ms(self) -> float:
        return self.total_tpot_ms / self.tpot_count if self.tpot_count else 0.0


@dataclass
class TokenMetrics:
    """Aggregate metrics keyed by provider name.

    Telemetry no longer distinguishes "local" vs "cloud" — every request is
    counted against the provider that handled it. The top-level totals are
    the sum across all providers.
    """
    by_provider: dict[str, ProviderTokenStats] = field(default_factory=dict)

    # Aggregates across all providers
    total_requests: int = 0
    total_latency_ms: float = 0.0
    total_ttft_ms: float = 0.0
    total_tpot_ms: float = 0.0
    ttft_count: int = 0
    tpot_count: int = 0

    # Token totals BEFORE router plugins (raw) and AFTER (compressed request
    # forwarded to backend), system / tool / context / overall. Same tiktoken
    # unit → the before/after delta is the actual compressor saving.
    before_router_system_tokens: int = 0
    before_router_tool_tokens: int = 0
    before_router_context_tokens: int = 0
    before_router_overall_tokens: int = 0
    after_router_system_tokens: int = 0
    after_router_tool_tokens: int = 0
    after_router_context_tokens: int = 0
    after_router_overall_tokens: int = 0

    def for_provider(self, name: str) -> ProviderTokenStats:
        """Return (creating if needed) the stats bucket for ``name``."""
        if name not in self.by_provider:
            self.by_provider[name] = ProviderTokenStats()
        return self.by_provider[name]

    @property
    def total_input_tokens(self) -> int:
        return sum(p.input_tokens for p in self.by_provider.values())

    @property
    def total_output_tokens(self) -> int:
        return sum(p.output_tokens for p in self.by_provider.values())

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def avg_tokens_per_request(self) -> float:
        return self.total_tokens / self.total_requests if self.total_requests else 0.0

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.total_requests if self.total_requests else 0.0

    @property
    def avg_ttft_ms(self) -> float:
        return self.total_ttft_ms / self.ttft_count if self.ttft_count else 0.0

    @property
    def avg_tpot_ms(self) -> float:
        return self.total_tpot_ms / self.tpot_count if self.tpot_count else 0.0


class Telemetry(ABC):
    """
    Telemetry Abstract Base Class

    Defines a unified observability interface, supports multiple implementations (memory, database, time-series database, etc.)
    """

    @abstractmethod
    def record_event(self, event: Event) -> None:
        """Record event"""
        pass

    @abstractmethod
    def get_metrics(self, time_window: timedelta | None = None) -> TokenMetrics:
        """Get statistics metrics"""
        pass

    @abstractmethod
    def get_events(
        self,
        event_type: str | None = None,
        time_window: timedelta | None = None
    ) -> list[Event]:
        """Query events"""
        pass

    @abstractmethod
    def print_report(self, time_window: timedelta | None = None) -> None:
        """Print statistics report"""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset all telemetry data"""
        pass


@dataclass
class InMemoryTelemetry(Telemetry):
    """
    In-Memory Telemetry

    Stores data in memory, suitable for development and testing
    """
    events: list[Event] = field(default_factory=list)

    def record_event(self, event: Event) -> None:
        """Record event"""
        self.events.append(event)

    def reset(self) -> None:
        """Reset all telemetry data"""
        self.events.clear()

    def get_metrics(self, time_window: timedelta | None = None) -> TokenMetrics:
        """Aggregate completed-request events into per-provider TokenMetrics."""
        completed_events = [
            e for e in self.events
            if isinstance(e, RequestCompletedEvent)
        ]

        if time_window:
            cutoff_time = datetime.now() - time_window
            completed_events = [
                e for e in completed_events
                if e.timestamp >= cutoff_time
            ]

        metrics = TokenMetrics()
        for event in completed_events:
            metrics.total_requests += 1

            metrics.before_router_system_tokens += event.before_router_system_tokens
            metrics.before_router_tool_tokens += event.before_router_tool_tokens
            metrics.before_router_context_tokens += event.before_router_context_tokens
            metrics.before_router_overall_tokens += event.before_router_overall_tokens
            metrics.after_router_system_tokens += event.after_router_system_tokens
            metrics.after_router_tool_tokens += event.after_router_tool_tokens
            metrics.after_router_context_tokens += event.after_router_context_tokens
            metrics.after_router_overall_tokens += event.after_router_overall_tokens

            if event.total_latency_ms is not None:
                metrics.total_latency_ms += event.total_latency_ms
            if event.ttft_ms is not None:
                metrics.total_ttft_ms += event.ttft_ms
                metrics.ttft_count += 1
            if event.tpot_ms is not None:
                metrics.total_tpot_ms += event.tpot_ms
                metrics.tpot_count += 1

            # Composite bucket key: ``"<provider>/<model>"`` (openclaw/OpenRouter
            # style) so dashboards can tell which model handled the traffic when
            # one provider exposes multiple models, or two providers share a
            # model. Falls back to ``"<provider>"`` alone when the backend echoed
            # no model id. Provider names are sanitized to exclude ``/`` (see
            # ``src.config.loader.validate_name``), so the split stays unambiguous.
            provider_name = event.provider_name or "unknown"
            model_name = event.final_model or (event.models_used[0] if event.models_used else "")
            bucket_key = f"{provider_name}/{model_name}" if model_name else provider_name
            bucket = metrics.for_provider(bucket_key)
            bucket.requests += 1
            bucket.input_tokens += event.total_input_tokens
            bucket.output_tokens += event.total_output_tokens

            if event.total_latency_ms is not None:
                bucket.total_latency_ms += event.total_latency_ms
            if event.ttft_ms is not None:
                bucket.total_ttft_ms += event.ttft_ms
                bucket.ttft_count += 1
            if event.tpot_ms is not None:
                bucket.total_tpot_ms += event.tpot_ms
                bucket.tpot_count += 1

        return metrics

    def get_events(
        self,
        event_type: str | None = None,
        time_window: timedelta | None = None
    ) -> list[Event]:
        """Query events"""
        events = self.events

        if event_type:
            events = [e for e in events if e.event_type == event_type]

        if time_window:
            cutoff_time = datetime.now() - time_window
            events = [e for e in events if e.timestamp >= cutoff_time]

        return events

    def get_stats_by_route_path(self) -> dict[str, Any]:
        """Statistics grouped by route path"""
        route_stats = defaultdict(lambda: {
            "count": 0,
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        })

        completed_events = [
            e for e in self.events
            if isinstance(e, RequestCompletedEvent)
        ]

        for event in completed_events:
            stats = route_stats[event.route_path]
            stats["count"] += 1
            stats["total_tokens"] += event.total_tokens
            stats["input_tokens"] += event.total_input_tokens
            stats["output_tokens"] += event.total_output_tokens

        return {
            path: {
                "request_count": stats["count"],
                "total_tokens": f"{stats['total_tokens']:,}",
                "avg_tokens_per_request": f"{stats['total_tokens'] / stats['count']:.1f}",
                "input_tokens": f"{stats['input_tokens']:,}",
                "output_tokens": f"{stats['output_tokens']:,}",
            }
            for path, stats in route_stats.items()
        }

    def get_evaluation_stats(self) -> dict[str, Any]:
        """Evaluation statistics (newly added)"""
        eval_events = [
            e for e in self.events
            if isinstance(e, EvaluationEvent)
        ]

        if not eval_events:
            return {}

        eval_stats = defaultdict(lambda: {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "avg_score": 0.0,
            "scores": [],
        })

        for event in eval_events:
            stats = eval_stats[event.evaluator_name]
            stats["total"] += 1
            stats["scores"].append(event.score)
            if event.passed:
                stats["passed"] += 1
            else:
                stats["failed"] += 1

        return {
            evaluator: {
                "total_evaluations": stats["total"],
                "passed": stats["passed"],
                "failed": stats["failed"],
                "pass_rate": f"{stats['passed'] / stats['total']:.2%}",
                "avg_score": f"{sum(stats['scores']) / len(stats['scores']):.3f}",
            }
            for evaluator, stats in eval_stats.items()
        }

    def print_report(self, time_window: timedelta | None = None) -> None:
        """Print statistics report"""
        metrics = self.get_metrics(time_window)

        print("\n" + "="*70)
        print("🔍 Observability Report")
        print("="*70)

        period = f"last {time_window}" if time_window else "all time"
        print(f"\n📊 Period: {period}")
        print(f"   Total requests: {metrics.total_requests:,}")

        print(f"\n🔢 Token Usage by Provider:")
        for name, p in sorted(
            metrics.by_provider.items(), key=lambda x: x[1].total_tokens, reverse=True
        ):
            share = (p.requests / metrics.total_requests) if metrics.total_requests else 0.0
            print(f"   {name}: {p.requests:,} requests ({share:.2%})")
            print(f"      Input:  {p.input_tokens:>15,} tokens")
            print(f"      Output: {p.output_tokens:>15,} tokens")
            print(f"      Total:  {p.total_tokens:>15,} tokens")
            print(f"      Avg/request: {p.avg_tokens_per_request:.1f} tokens, "
                  f"latency: {p.avg_latency_ms:.1f}ms, "
                  f"ttft: {p.avg_ttft_ms:.1f}ms, "
                  f"tpot: {p.avg_tpot_ms:.4f}ms")

        print(f"\n   Overall:    {metrics.total_tokens:>15,} tokens")
        print(f"   Avg/request: {metrics.avg_tokens_per_request:.1f} tokens")

        # Route path statistics
        route_stats = self.get_stats_by_route_path()
        if route_stats:
            print(f"\n🛣️  Route Path Analysis:")
            for path, stats in route_stats.items():
                print(f"   {path}:")
                print(f"      Requests: {stats['request_count']}, "
                      f"Avg tokens: {stats['avg_tokens_per_request']}, "
                      f"Total: {stats['total_tokens']}")

        # Evaluation statistics
        eval_stats = self.get_evaluation_stats()
        if eval_stats:
            print(f"\n✅ Evaluation Analysis:")
            for evaluator, stats in eval_stats.items():
                print(f"   {evaluator}:")
                print(f"      Total: {stats['total_evaluations']}, "
                      f"Passed: {stats['passed']}, "
                      f"Pass rate: {stats['pass_rate']}, "
                      f"Avg score: {stats['avg_score']}")

        print("\n" + "="*70 + "\n")


# ==================== Serialization Helpers ====================

# Maps event_type string -> event dataclass
_EVENT_TYPE_MAP: dict[str, type[Event]] = {
    "route": RouteEvent,
    "inference": InferenceEvent,
    "evaluation": EvaluationEvent,
    "request_completed": RequestCompletedEvent,
}


def _event_to_dict(event: Event) -> dict:
    """Serialize an Event dataclass to a JSON-safe dict."""
    d = _dc.asdict(event)
    # Convert datetime to ISO-8601 string
    if isinstance(d.get("timestamp"), datetime):
        d["timestamp"] = d["timestamp"].isoformat()
    return d


def _event_from_dict(d: dict) -> Event:
    """Deserialize a dict back into the appropriate Event subclass."""
    event_type = d.get("event_type", "")
    cls = _EVENT_TYPE_MAP.get(event_type, Event)

    # Convert ISO-8601 string back to datetime
    ts_raw = d.get("timestamp")
    if isinstance(ts_raw, str):
        d["timestamp"] = datetime.fromisoformat(ts_raw)

    # Only pass fields that the dataclass actually accepts
    valid_fields = {f.name for f in _dc.fields(cls)}
    filtered = {k: v for k, v in d.items() if k in valid_fields}
    return cls(**filtered)


# ==================== File-Based Telemetry ====================


class FileBasedTelemetry(Telemetry):
    """
    File-Based Telemetry

    Persists events to a local JSONL file so telemetry data survives gateway
    restarts.  Uses ``fcntl`` file locking for safe concurrent access.

    Each line in the file is a JSON object representing one event, stored with
    a datetime timestamp for future data filtering.
    """

    def __init__(self, file_path: str | Path):
        self._path = Path(file_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Create the file if it doesn't exist
        if not self._path.exists():
            self._path.touch()

    # -- write ----------------------------------------------------------------

    def record_event(self, event: Event) -> None:
        """Append a single event to the JSONL file under an exclusive lock."""
        line = json.dumps(_event_to_dict(event), ensure_ascii=False) + "\n"
        try:
            with open(self._path, "a") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    f.write(line)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except Exception as e:
            logger.warning(f"Failed to write telemetry event: {e}")

    # -- read helpers ---------------------------------------------------------

    def _load_events(self, time_window: timedelta | None = None) -> list[Event]:
        """Read all events from the file under a shared lock.

        Optionally filters to events within ``time_window`` of now.
        """
        events: list[Event] = []
        cutoff = datetime.now() - time_window if time_window else None

        try:
            with open(self._path, "r") as f:
                fcntl.flock(f, fcntl.LOCK_SH)
                try:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            event = _event_from_dict(d)
                            if cutoff is not None and event.timestamp < cutoff:
                                continue
                            events.append(event)
                        except (json.JSONDecodeError, Exception) as parse_err:
                            logger.debug(f"Skipping malformed telemetry line: {parse_err}")
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(f"Failed to read telemetry file: {e}")

        return events

    def _as_in_memory(self, time_window: timedelta | None = None) -> InMemoryTelemetry:
        """Load events into a transient InMemoryTelemetry for computation."""
        t = InMemoryTelemetry()
        t.events = self._load_events(time_window)
        return t

    # -- Telemetry interface --------------------------------------------------

    def get_metrics(self, time_window: timedelta | None = None) -> TokenMetrics:
        return self._as_in_memory(time_window).get_metrics()

    def get_events(
        self,
        event_type: str | None = None,
        time_window: timedelta | None = None,
    ) -> list[Event]:
        return self._as_in_memory(time_window).get_events(event_type=event_type)

    def print_report(self, time_window: timedelta | None = None) -> None:
        self._as_in_memory(time_window).print_report()

    def reset(self) -> None:
        """Truncate the telemetry file."""
        try:
            with open(self._path, "w") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    f.truncate(0)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except Exception as e:
            logger.warning(f"Failed to reset telemetry file: {e}")
