# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Metrics storage and management.

Provides in-memory storage for custom metrics with automatic expiration
and HTTP push to Telegraf for integration.

Features:
- Thread-safe async operations
- Debounced HTTP push to Telegraf input plugin
- Automatic metric expiration
- Memory limit protection
"""

import asyncio
import time
from asyncio import Lock
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore

from .logging_config import get_logger
from .models import Metric
from .settings import get_settings

logger = get_logger("store")


@dataclass
class StoredMetric:
    """Metric with expiration tracking."""

    metric: Metric
    retention_seconds: float
    expires_at: float = field(init=False)

    def __post_init__(self):
        self.expires_at = time.time() + self.retention_seconds

    def is_expired(self) -> bool:
        """Check if metric has expired."""
        return time.time() > self.expires_at


class MetricsStore:
    """
    Thread-safe in-memory metrics storage with async file persistence.

    Features:
    - In-memory storage for real-time access
    - Automatic metric expiration
    - Debounced file persistence for Telegraf integration
    - JSON and InfluxDB Line Protocol file formats
    - Memory limit protection
    """

    def __init__(self, metrics_dir: str | None = None, debounce_ms: int | None = None):
        settings = get_settings()
        self._metrics: dict[str, list[StoredMetric]] = defaultdict(list)
        self._lock = Lock()
        self._session_lock = Lock()

        # Debounce settings (allow override for testing)
        self._persist_debounce_ms = (
            debounce_ms
            if debounce_ms is not None
            else settings.file_persist_debounce_ms
        )
        self._last_persist_time: float = 0.0  # monotonic epoch
        self._pending_persist: bool = False
        self._persist_task: asyncio.Task | None = None

        # Pending metrics not yet pushed to Telegraf
        self._pending_for_push: list[Metric] = []

        # Memory limits
        self._max_metrics = settings.max_metrics_in_memory
        self._retention_seconds: float = settings.metrics_retention_seconds
        self._total_metrics_count: int = 0

        # HTTP session for pushing metrics to Telegraf
        self._http_session: Any | None = None

        logger.info(
            "MetricsStore initialized",
            extra={
                "max_metrics": self._max_metrics,
                "telegraf_endpoint": settings.telegraf_http_endpoint,
            },
        )

    async def add_metric(self, metric: Metric) -> None:
        """Add a single metric to the store."""
        async with self._lock:
            if self._total_metrics_count >= self._max_metrics:
                await self._evict_n(1)

            stored = StoredMetric(metric=metric, retention_seconds=self._retention_seconds)
            self._metrics[metric.name].append(stored)
            self._total_metrics_count += 1
            self._pending_for_push.append(metric)
            await self._cleanup_expired()
            await self._schedule_persist()
            logger.debug("Added metric", extra={"metric_name": metric.name})

    async def add_metrics(self, metrics: list[Metric]) -> int:
        """Add multiple metrics to the store. Returns count of added metrics."""
        async with self._lock:
            excess = (self._total_metrics_count + len(metrics)) - self._max_metrics
            if excess > 0:
                await self._evict_n(min(excess, self._total_metrics_count))

            for metric in metrics:
                stored = StoredMetric(metric=metric, retention_seconds=self._retention_seconds)
                self._metrics[metric.name].append(stored)
                self._total_metrics_count += 1

            self._pending_for_push.extend(metrics)
            await self._cleanup_expired()
            await self._schedule_persist()
            # DEBUG-level: under high-frequency push workloads (e.g. ViPPET
            # sending fps every second) per-call store logs would dominate
            # the INFO stream. Counts are exposed via service_metrics on the
            # Prometheus endpoint instead.
            logger.debug("Added metrics", extra={"count": len(metrics)})
            return len(metrics)

    async def get_metrics(self, name: str | None = None) -> list[Metric]:
        """Get metrics, optionally filtered by name."""
        async with self._lock:
            await self._cleanup_expired()

            if name:
                return [sm.metric for sm in self._metrics.get(name, []) if not sm.is_expired()]

            result = []
            for metrics_list in self._metrics.values():
                result.extend([sm.metric for sm in metrics_list if not sm.is_expired()])
            return result

    async def get_latest_metrics(self) -> dict[str, Metric]:
        """Get the latest metric for each metric name."""
        async with self._lock:
            await self._cleanup_expired()

            latest = {}
            for name, metrics_list in self._metrics.items():
                valid = [sm for sm in metrics_list if not sm.is_expired()]
                if valid:
                    # Get most recent by timestamp
                    latest[name] = max(valid, key=lambda sm: sm.metric.timestamp or 0).metric
            return latest

    async def get_metric_names(self) -> list[str]:
        """Get list of all metric names in store."""
        async with self._lock:
            await self._cleanup_expired()
            return list(self._metrics.keys())

    async def clear_metrics(self, name: str | None = None) -> int:
        """Clear metrics. If name is provided, clear only that metric. Returns count cleared."""
        async with self._lock:
            if name:
                self._pending_for_push = [m for m in self._pending_for_push if m.name != name]
                count = len(self._metrics.get(name, []))
                self._metrics.pop(name, None)
            else:
                self._pending_for_push.clear()
                count = sum(len(v) for v in self._metrics.values())
                self._metrics.clear()
            self._total_metrics_count = sum(len(v) for v in self._metrics.values())
            logger.info("Cleared metrics", extra={"count": count})
            return count

    async def get_stats(self) -> dict[str, Any]:
        """Get storage statistics."""
        settings = get_settings()
        async with self._lock:
            await self._cleanup_expired()

            total_metrics = sum(len(v) for v in self._metrics.values())
            metric_counts = {name: len(metrics) for name, metrics in self._metrics.items()}

            return {
                "total_metrics": total_metrics,
                "metric_names": list(self._metrics.keys()),
                "metric_counts": metric_counts,
                "retention_seconds": settings.metrics_retention_seconds,
                "max_metrics": self._max_metrics,
                "telegraf_endpoint": settings.telegraf_http_endpoint,
            }

    async def _cleanup_expired(self) -> None:
        """Remove expired metrics from storage."""
        expired_count = 0
        for name in list(self._metrics.keys()):
            original_len = len(self._metrics[name])
            self._metrics[name] = [sm for sm in self._metrics[name] if not sm.is_expired()]
            expired_count += original_len - len(self._metrics[name])
            if not self._metrics[name]:
                del self._metrics[name]

        if expired_count > 0:
            self._total_metrics_count -= expired_count
            logger.debug("Cleaned up expired metrics", extra={"count": expired_count})

    async def _evict_n(self, n: int) -> None:
        """Evict n oldest metrics in a single O(N log N) pass."""
        if n <= 0:
            return
        all_entries = [
            (sm.metric.timestamp or 0, name, i)
            for name, metrics_list in self._metrics.items()
            for i, sm in enumerate(metrics_list)
        ]
        all_entries.sort(key=lambda x: x[0])
        to_evict = all_entries[:n]

        evict_indices: dict[str, set] = defaultdict(set)
        for _, name, idx in to_evict:
            evict_indices[name].add(idx)

        evicted = 0
        for name, indices in evict_indices.items():
            before = len(self._metrics[name])
            self._metrics[name] = [
                sm for i, sm in enumerate(self._metrics[name]) if i not in indices
            ]
            evicted += before - len(self._metrics[name])
            if not self._metrics[name]:
                del self._metrics[name]

        self._total_metrics_count -= evicted

    async def _evict_oldest(self) -> None:
        await self._evict_n(1)

    async def _schedule_persist(self) -> None:
        """Schedule debounced HTTP push to Telegraf."""
        if self._persist_debounce_ms <= 0:
            try:
                await self._persist_to_files_async()
            except Exception as e:
                logger.error("Failed to persist metrics", extra={"error": str(e)})
            return

        self._pending_persist = True
        now = time.monotonic() * 1000  # milliseconds, clock-skew safe

        if now - self._last_persist_time >= self._persist_debounce_ms:
            await self._persist_to_files_async()
            self._last_persist_time = now
            self._pending_persist = False
        elif self._persist_task is None or self._persist_task.done():
            self._persist_task = asyncio.create_task(self._delayed_persist())

    async def _delayed_persist(self) -> None:
        await asyncio.sleep(self._persist_debounce_ms / 1000.0)
        async with self._lock:
            if self._pending_persist:
                await self._persist_to_files_async()
                self._last_persist_time = time.monotonic() * 1000
                self._pending_persist = False

    def _drain_pending(self) -> list[Metric]:
        """Drain all metrics accumulated since the last push. Must hold lock."""
        pending = self._pending_for_push[:]
        self._pending_for_push.clear()
        return pending

    async def _persist_to_files_async(self) -> None:
        """Push all pending metrics to Telegraf HTTP listener as a fire-and-forget task."""
        try:
            pending = self._drain_pending()
            if not pending:
                return

            influx_content = "\n".join(m.to_influx_line() for m in pending) + "\n"

            loop = asyncio.get_running_loop()
            task = loop.create_task(
                self._push_to_telegraf(influx_content, len(pending)),
                name="push-to-telegraf",
            )
            task.add_done_callback(self._handle_push_task_result)

        except Exception as e:
            logger.error("Failed to push metrics to Telegraf", extra={"error": str(e)})

    @staticmethod
    def _handle_push_task_result(task: asyncio.Task) -> None:
        """Callback for fire-and-forget Telegraf push tasks.

        Logs any unhandled exceptions so they are not silently swallowed.
        """
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Background Telegraf push failed", extra={"error": str(exc)})

    async def close(self) -> None:
        """Cancel pending persist task then close the HTTP session.

        Cancel order matters: _persist_task must be cancelled before the session
        is closed to prevent it from spawning a new ClientSession post-shutdown.
        """
        if self._persist_task and not self._persist_task.done():
            self._persist_task.cancel()
            try:
                await self._persist_task
            except asyncio.CancelledError:
                pass

        if self._http_session is not None and not self._http_session.closed:
            await self._http_session.close()
            self._http_session = None
            logger.info("HTTP session closed")

    async def _push_to_telegraf(self, influx_content: str, count: int) -> None:
        """Push metrics to Telegraf HTTP listener asynchronously."""
        if not aiohttp:
            logger.warning("aiohttp not installed, cannot push metrics to Telegraf")
            return

        try:
            async with self._session_lock:
                if self._http_session is None or self._http_session.closed:
                    self._http_session = aiohttp.ClientSession()
                session = self._http_session

            async with session.post(
                get_settings().telegraf_http_endpoint,
                data=influx_content,
                headers={"Content-Type": "text/plain"},
                timeout=aiohttp.ClientTimeout(total=5.0),
            ) as resp:
                if resp.status == 204:
                    logger.debug("Pushed metrics to Telegraf", extra={"count": count})
                else:
                    logger.warning(
                        "Telegraf returned non-204 status",
                        extra={"status": resp.status, "count": count},
                    )
        except Exception as e:
            logger.error("Failed to push metrics to Telegraf", extra={"error": str(e)})


# Global metrics store instance
_metrics_store: MetricsStore | None = None


def get_metrics_store() -> MetricsStore:
    """Get or create the global metrics store instance."""
    global _metrics_store
    if _metrics_store is None:
        _metrics_store = MetricsStore()
    return _metrics_store


def reset_metrics_store() -> None:
    """Reset the metrics store (for testing)."""
    global _metrics_store
    _metrics_store = None
