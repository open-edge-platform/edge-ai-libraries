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
    CompressionEvent,
    RequestCompletedEvent,
)

logger = logging.getLogger("telemetry")


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


@dataclass
class CompressionMetrics:
    """Aggregate compression statistics (mirrors analyze_compression._compute_aggregates)."""
    total_compressions: int = 0

    # System prompt aggregate
    total_original_system_tokens: int = 0
    total_compressed_system_tokens: int = 0

    # Tool schema aggregate
    total_original_tool_schema_tokens: int = 0
    total_compressed_tool_schema_tokens: int = 0

    # Message aggregate (all roles combined)
    total_original_message_tokens: int = 0
    total_compressed_message_tokens: int = 0

    # Per-role aggregates
    total_original_user_tokens: int = 0
    total_compressed_user_tokens: int = 0
    total_original_assistant_tokens: int = 0
    total_compressed_assistant_tokens: int = 0
    total_original_tool_result_tokens: int = 0
    total_compressed_tool_result_tokens: int = 0

    # Full input aggregate
    total_original_tokens: int = 0
    total_compressed_tokens: int = 0

    # Per-heading section aggregate: heading_name -> {original_tokens, compressed_tokens, count}
    section_stats: dict[str, dict[str, int]] = field(default_factory=dict)

    # Timing (total = token counting + compression)
    total_duration_ms: float = 0.0
    first_request_duration_ms: float = 0.0
    durations: list[float] = field(default_factory=list)
    # Timing (compression only)
    total_compress_duration_ms: float = 0.0
    compress_durations: list[float] = field(default_factory=list)
    # Per-strategy timing: strategy_name -> list of durations
    strategy_durations: dict[str, list[float]] = field(default_factory=dict)

    # -- derived properties --------------------------------------------------

    @property
    def system_tokens_saved(self) -> int:
        return self.total_original_system_tokens - self.total_compressed_system_tokens

    @property
    def system_save_pct(self) -> float:
        if self.total_original_system_tokens == 0:
            return 0.0
        return (self.system_tokens_saved / self.total_original_system_tokens) * 100

    @property
    def system_rest_pct(self) -> float:
        if self.total_original_system_tokens == 0:
            return 100.0
        return (self.total_compressed_system_tokens / self.total_original_system_tokens) * 100

    @property
    def tool_schema_rest_pct(self) -> float:
        if self.total_original_tool_schema_tokens == 0:
            return 100.0
        return (self.total_compressed_tool_schema_tokens / self.total_original_tool_schema_tokens) * 100

    @property
    def message_rest_pct(self) -> float:
        if self.total_original_message_tokens == 0:
            return 100.0
        return (self.total_compressed_message_tokens / self.total_original_message_tokens) * 100

    @property
    def user_rest_pct(self) -> float:
        if self.total_original_user_tokens == 0:
            return 100.0
        return (self.total_compressed_user_tokens / self.total_original_user_tokens) * 100

    @property
    def assistant_rest_pct(self) -> float:
        if self.total_original_assistant_tokens == 0:
            return 100.0
        return (self.total_compressed_assistant_tokens / self.total_original_assistant_tokens) * 100

    @property
    def tool_result_rest_pct(self) -> float:
        if self.total_original_tool_result_tokens == 0:
            return 100.0
        return (self.total_compressed_tool_result_tokens / self.total_original_tool_result_tokens) * 100

    @property
    def total_original_conversation_tokens(self) -> int:
        """user + assistant + tool_result (excludes system_prompt)."""
        return (self.total_original_user_tokens
                + self.total_original_assistant_tokens
                + self.total_original_tool_result_tokens)

    @property
    def total_compressed_conversation_tokens(self) -> int:
        return (self.total_compressed_user_tokens
                + self.total_compressed_assistant_tokens
                + self.total_compressed_tool_result_tokens)

    @property
    def conversation_rest_pct(self) -> float:
        if self.total_original_conversation_tokens == 0:
            return 100.0
        return (self.total_compressed_conversation_tokens / self.total_original_conversation_tokens) * 100

    @property
    def total_original_static_tokens(self) -> int:
        """system_prompt + tool_schema (static context sent every request)."""
        return self.total_original_system_tokens + self.total_original_tool_schema_tokens

    @property
    def total_compressed_static_tokens(self) -> int:
        return self.total_compressed_system_tokens + self.total_compressed_tool_schema_tokens

    @property
    def static_rest_pct(self) -> float:
        if self.total_original_static_tokens == 0:
            return 100.0
        return (self.total_compressed_static_tokens / self.total_original_static_tokens) * 100

    @property
    def avg_static_tokens_per_request(self) -> tuple[float, float]:
        if self.total_compressions == 0:
            return (0.0, 0.0)
        n = self.total_compressions
        return (
            self.total_original_static_tokens / n,
            self.total_compressed_static_tokens / n,
        )

    @property
    def total_save_pct(self) -> float:
        if self.total_original_tokens == 0:
            return 0.0
        return ((self.total_original_tokens - self.total_compressed_tokens) / self.total_original_tokens) * 100

    @property
    def total_rest_pct(self) -> float:
        if self.total_original_tokens == 0:
            return 100.0
        return (self.total_compressed_tokens / self.total_original_tokens) * 100

    @property
    def avg_system_tokens_per_request(self) -> tuple[float, float, float]:
        """(avg_original, avg_compressed, avg_saved) per request."""
        if self.total_compressions == 0:
            return (0.0, 0.0, 0.0)
        n = self.total_compressions
        return (
            self.total_original_system_tokens / n,
            self.total_compressed_system_tokens / n,
            self.system_tokens_saved / n,
        )

    @property
    def avg_tool_schema_tokens_per_request(self) -> tuple[float, float]:
        """(avg_original, avg_compressed) per request."""
        if self.total_compressions == 0:
            return (0.0, 0.0)
        n = self.total_compressions
        return (
            self.total_original_tool_schema_tokens / n,
            self.total_compressed_tool_schema_tokens / n,
        )

    @property
    def avg_message_tokens_per_request(self) -> tuple[float, float]:
        """(avg_original, avg_compressed) per request — all roles combined."""
        if self.total_compressions == 0:
            return (0.0, 0.0)
        n = self.total_compressions
        return (
            self.total_original_message_tokens / n,
            self.total_compressed_message_tokens / n,
        )

    @property
    def avg_user_tokens_per_request(self) -> tuple[float, float]:
        if self.total_compressions == 0:
            return (0.0, 0.0)
        n = self.total_compressions
        return (
            self.total_original_user_tokens / n,
            self.total_compressed_user_tokens / n,
        )

    @property
    def avg_assistant_tokens_per_request(self) -> tuple[float, float]:
        if self.total_compressions == 0:
            return (0.0, 0.0)
        n = self.total_compressions
        return (
            self.total_original_assistant_tokens / n,
            self.total_compressed_assistant_tokens / n,
        )

    @property
    def avg_tool_result_tokens_per_request(self) -> tuple[float, float]:
        if self.total_compressions == 0:
            return (0.0, 0.0)
        n = self.total_compressions
        return (
            self.total_original_tool_result_tokens / n,
            self.total_compressed_tool_result_tokens / n,
        )

    @property
    def avg_conversation_tokens_per_request(self) -> tuple[float, float]:
        """(avg_original, avg_compressed) per request — user+assistant+tool_result."""
        if self.total_compressions == 0:
            return (0.0, 0.0)
        n = self.total_compressions
        return (
            self.total_original_conversation_tokens / n,
            self.total_compressed_conversation_tokens / n,
        )

    @property
    def avg_total_tokens_per_request(self) -> tuple[float, float, float]:
        """(avg_original, avg_compressed, avg_saved) per request."""
        if self.total_compressions == 0:
            return (0.0, 0.0, 0.0)
        n = self.total_compressions
        saved = self.total_original_tokens - self.total_compressed_tokens
        return (
            self.total_original_tokens / n,
            self.total_compressed_tokens / n,
            saved / n,
        )

    @property
    def avg_duration_ms(self) -> float:
        if not self.durations:
            return 0.0
        return sum(self.durations) / len(self.durations)

    @property
    def avg_duration_excluding_first_ms(self) -> float:
        if len(self.durations) <= 1:
            return 0.0
        return sum(self.durations[1:]) / len(self.durations[1:])

    @property
    def avg_compress_duration_ms(self) -> float:
        if not self.compress_durations:
            return 0.0
        return sum(self.compress_durations) / len(self.compress_durations)

    @property
    def avg_compress_duration_excluding_first_ms(self) -> float:
        if len(self.compress_durations) <= 1:
            return 0.0
        return sum(self.compress_durations[1:]) / len(self.compress_durations[1:])

    def get_strategy_timing(self, strategy_name: str) -> dict:
        """Get timing statistics for a specific compression strategy.

        Returns:
            dict with keys: total_ms, avg_ms, first_request_ms, avg_excluding_first_ms
        """
        durations = self.strategy_durations.get(strategy_name, [])
        if not durations:
            return {
                "total_ms": 0.0,
                "avg_ms": 0.0,
                "first_request_ms": 0.0,
                "avg_excluding_first_ms": 0.0,
            }

        return {
            "total_ms": sum(durations),
            "avg_ms": sum(durations) / len(durations),
            "first_request_ms": durations[0],
            "avg_excluding_first_ms": sum(durations[1:]) / len(durations[1:]) if len(durations) > 1 else 0.0,
        }


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
    def get_compression_metrics(self, time_window: timedelta | None = None) -> CompressionMetrics:
        """Get aggregate compression metrics."""
        pass

    @abstractmethod
    def get_compression_events(self, time_window: timedelta | None = None) -> list[CompressionEvent]:
        """Get compression events (per-request detail)."""
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

            if event.total_latency_ms is not None:
                metrics.total_latency_ms += event.total_latency_ms
            if event.ttft_ms is not None:
                metrics.total_ttft_ms += event.ttft_ms
                metrics.ttft_count += 1
            if event.tpot_ms is not None:
                metrics.total_tpot_ms += event.tpot_ms
                metrics.tpot_count += 1

            # Composite bucket key: ``"<model>@<provider>"`` so dashboards can
            # tell which model handled the traffic when one provider exposes
            # multiple models, or two providers share a model. Falls back to
            # ``"<provider>"`` alone when the backend echoed no model id.
            provider_name = event.provider_name or "unknown"
            model_name = event.final_model or (event.models_used[0] if event.models_used else "")
            bucket_key = f"{model_name}@{provider_name}" if model_name else provider_name
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

    def get_compression_events(self, time_window: timedelta | None = None) -> list[CompressionEvent]:
        """Get compression events within optional time window."""
        events: list[CompressionEvent] = [
            e for e in self.events if isinstance(e, CompressionEvent)
        ]
        if time_window:
            cutoff = datetime.now() - time_window
            events = [e for e in events if e.timestamp >= cutoff]
        return events

    def get_compression_metrics(self, time_window: timedelta | None = None, model_filter: str | None = None) -> CompressionMetrics:
        """Aggregate all CompressionEvents into CompressionMetrics.

        Args:
            time_window: Optional time window to filter events
            model_filter: Optional model name to filter events (e.g., "auto", "Qwen/...", etc.)
        """
        events = self.get_compression_events(time_window)

        # Filter by model if specified
        if model_filter:
            events = [e for e in events if e.details.get("model") == model_filter]

        metrics = CompressionMetrics(total_compressions=len(events))

        for e in events:
            metrics.total_original_system_tokens += e.original_system_tokens
            metrics.total_compressed_system_tokens += e.compressed_system_tokens
            metrics.total_original_tool_schema_tokens += e.original_tool_schema_tokens
            metrics.total_compressed_tool_schema_tokens += e.compressed_tool_schema_tokens
            metrics.total_original_tokens += e.original_total_tokens
            metrics.total_compressed_tokens += e.compressed_total_tokens

            ori_msg = sum(e.original_role_tokens.values()) if e.original_role_tokens else 0
            comp_msg = sum(e.compressed_role_tokens.values()) if e.compressed_role_tokens else 0
            metrics.total_original_message_tokens += ori_msg
            metrics.total_compressed_message_tokens += comp_msg

            if e.original_role_tokens:
                metrics.total_original_user_tokens += e.original_role_tokens.get("user", 0)
                metrics.total_original_assistant_tokens += e.original_role_tokens.get("assistant", 0)
                metrics.total_original_tool_result_tokens += e.original_role_tokens.get("tool_result", 0)
            if e.compressed_role_tokens:
                metrics.total_compressed_user_tokens += e.compressed_role_tokens.get("user", 0)
                metrics.total_compressed_assistant_tokens += e.compressed_role_tokens.get("assistant", 0)
                metrics.total_compressed_tool_result_tokens += e.compressed_role_tokens.get("tool_result", 0)

            # Aggregate per-heading section stats from lingua details
            lingua_meta = e.details.get("lingua", {}) if e.details else {}
            for sd in lingua_meta.get("section_details", []):
                name = sd.get("name", "unknown")
                if name not in metrics.section_stats:
                    metrics.section_stats[name] = {
                        "original_tokens": 0,
                        "compressed_tokens": 0,
                        "count": 0,
                    }
                entry = metrics.section_stats[name]
                entry["original_tokens"] += sd.get("original_tokens", 0)
                entry["compressed_tokens"] += sd.get("compressed_tokens", 0)
                entry["count"] += 1

            metrics.durations.append(e.duration_ms)
            metrics.compress_durations.append(e.compress_duration_ms)

            # Extract per-strategy durations from details
            if e.details:
                for strategy_name, strategy_meta in e.details.items():
                    if strategy_name == "model":  # Skip model metadata
                        continue
                    if isinstance(strategy_meta, dict):
                        strategy_duration = strategy_meta.get("duration_ms")
                        if strategy_duration is not None:
                            if strategy_name not in metrics.strategy_durations:
                                metrics.strategy_durations[strategy_name] = []
                            metrics.strategy_durations[strategy_name].append(strategy_duration)

        if metrics.durations:
            metrics.total_duration_ms = sum(metrics.durations)
            metrics.first_request_duration_ms = metrics.durations[0]
        if metrics.compress_durations:
            metrics.total_compress_duration_ms = sum(metrics.compress_durations)

        return metrics

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

        # Compression statistics
        comp_metrics = self.get_compression_metrics(time_window)
        if comp_metrics.total_compressions > 0:
            cm = comp_metrics
            avg_ori, avg_comp, avg_saved = cm.avg_system_tokens_per_request
            print(f"\n📦 Compression Analysis:")
            print(f"   Requests:                {cm.total_compressions}")
            print(f"   System prompt tokens:    {cm.total_original_system_tokens:,} -> "
                  f"{cm.total_compressed_system_tokens:,} "
                  f"(saved {cm.system_tokens_saved:,}, {cm.system_save_pct:.1f}%, "
                  f"rest {cm.system_rest_pct:.1f}%)")
            if cm.total_original_tool_schema_tokens > 0:
                print(f"   Tool schema tokens:      {cm.total_original_tool_schema_tokens:,} -> "
                      f"{cm.total_compressed_tool_schema_tokens:,} "
                      f"(rest {cm.tool_schema_rest_pct:.1f}%)")
            if cm.total_original_message_tokens > 0:
                print(f"   Message tokens:          {cm.total_original_message_tokens:,} -> "
                      f"{cm.total_compressed_message_tokens:,} "
                      f"(rest {cm.message_rest_pct:.1f}%)")
            if cm.total_original_user_tokens > 0:
                print(f"     User tokens:           {cm.total_original_user_tokens:,} -> "
                      f"{cm.total_compressed_user_tokens:,} "
                      f"(rest {cm.user_rest_pct:.1f}%)")
            if cm.total_original_assistant_tokens > 0:
                print(f"     Assistant tokens:       {cm.total_original_assistant_tokens:,} -> "
                      f"{cm.total_compressed_assistant_tokens:,} "
                      f"(rest {cm.assistant_rest_pct:.1f}%)")
            if cm.total_original_tool_result_tokens > 0:
                print(f"     Tool result tokens:     {cm.total_original_tool_result_tokens:,} -> "
                      f"{cm.total_compressed_tool_result_tokens:,} "
                      f"(rest {cm.tool_result_rest_pct:.1f}%)")
            if cm.total_original_conversation_tokens > 0:
                print(f"   Conversation tokens:     {cm.total_original_conversation_tokens:,} -> "
                      f"{cm.total_compressed_conversation_tokens:,} "
                      f"(rest {cm.conversation_rest_pct:.1f}%)")
            print(f"   Total input tokens:      {cm.total_original_tokens:,} -> "
                  f"{cm.total_compressed_tokens:,} "
                  f"(saved {cm.total_original_tokens - cm.total_compressed_tokens:,}, "
                  f"{cm.total_save_pct:.1f}%, rest {cm.total_rest_pct:.1f}%)")
            print(f"   Avg sys tokens/request:  {avg_ori:.0f} -> {avg_comp:.0f} (saved {avg_saved:.0f})")
            if cm.durations:
                print(f"   Compression time (total):          {cm.total_duration_ms:.0f} ms")
                print(f"   Compression time (avg/req):        {cm.avg_duration_ms:.1f} ms")
                print(f"   Compression time (1st req):        {cm.first_request_duration_ms:.1f} ms")
                if cm.avg_duration_excluding_first_ms > 0:
                    print(f"   Compression time (avg excl. 1st):  {cm.avg_duration_excluding_first_ms:.1f} ms")
            if cm.section_stats:
                print(f"\n   Per-section breakdown (by original tokens):")
                for name, stats in sorted(
                    cm.section_stats.items(),
                    key=lambda x: x[1]["original_tokens"],
                    reverse=True,
                ):
                    ori = stats["original_tokens"]
                    comp = stats["compressed_tokens"]
                    saved = ori - comp
                    rest_pct = comp / ori * 100 if ori else 0.0
                    avg_ori = ori // stats["count"]
                    avg_comp = comp // stats["count"]
                    print(f"     {name:40s}  {ori:>7,} -> {comp:>7,}  "
                          f"(saved {saved:>6,}, rest {rest_pct:5.1f}%, "
                          f"avg {avg_ori:,}->{avg_comp:,}, n={stats['count']})")

        print("\n" + "="*70 + "\n")


# ==================== Serialization Helpers ====================

# Maps event_type string -> event dataclass
_EVENT_TYPE_MAP: dict[str, type[Event]] = {
    "route": RouteEvent,
    "inference": InferenceEvent,
    "evaluation": EvaluationEvent,
    "compression": CompressionEvent,
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

    def get_compression_metrics(
        self, time_window: timedelta | None = None, model_filter: str | None = None,
    ) -> CompressionMetrics:
        return self._as_in_memory(time_window).get_compression_metrics(model_filter=model_filter)

    def get_compression_events(
        self, time_window: timedelta | None = None,
    ) -> list[CompressionEvent]:
        return self._as_in_memory(time_window).get_compression_events()

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
