# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Non-blocking publication of DataPrep throughput to Metrics Manager."""

from __future__ import annotations

import asyncio
import math
import time
from typing import Any

import httpx

from src.common import logger, settings

METRIC_NAME = "dataprep_embeddings_per_second"
METRIC_TAGS = {"service": "multimodal-dataprep", "stage": "embedding"}
SIMPLE_METRIC_PATH = "/api/v1/metrics/simple"


class MetricsManagerPublisher:
    """Publish only the latest completed-pipeline metric without blocking ingestion."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        *,
        client: httpx.AsyncClient | None = None,
        initial_retry_seconds: float = 0.25,
        max_retry_seconds: float = 10.0,
        warning_interval_seconds: float = 30.0,
    ) -> None:
        self._base_url = base_url.strip().rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._client = client
        self._owns_client = client is None
        self._initial_retry_seconds = initial_retry_seconds
        self._max_retry_seconds = max_retry_seconds
        self._warning_interval_seconds = warning_interval_seconds
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[dict[str, Any]] | None = None
        self._worker: asyncio.Task[None] | None = None
        self._last_warning_at = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self._base_url)

    async def start(self) -> None:
        """Create the HTTP client and background worker when publishing is enabled."""

        if not self.enabled or self._worker is not None:
            return

        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue(maxsize=1)
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout_seconds)
        self._worker = asyncio.create_task(
            self._run(),
            name="metrics-manager-publisher",
        )
        logger.info("Metrics Manager publishing enabled at %s", self._base_url)

    async def stop(self) -> None:
        """Stop immediately; queued values are intentionally not replayed on restart."""

        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass

        if self._client is not None and self._owns_client:
            await self._client.aclose()

        self._client = None
        self._queue = None
        self._loop = None

    def publish(self, value: object, timestamp: object) -> bool:
        """Schedule a metric and return immediately.

        This method is safe to call from either the application event-loop
        thread or a pipeline worker thread.
        """

        try:
            metric_value = float(value)
            metric_timestamp = float(timestamp)
        except (TypeError, ValueError):
            return False

        if (
            not math.isfinite(metric_value)
            or metric_value < 0
            or not math.isfinite(metric_timestamp)
            or metric_timestamp < 0
        ):
            return False

        loop = self._loop
        if not self.enabled or loop is None or self._worker is None:
            return False

        payload = {
            "name": METRIC_NAME,
            "value": metric_value,
            "timestamp": metric_timestamp,
            "tags": dict(METRIC_TAGS),
        }
        try:
            loop.call_soon_threadsafe(self._put_latest, payload)
        except RuntimeError:
            # The application event loop may close between the lifecycle check
            # above and a worker-thread publication during shutdown.
            return False
        return True

    def _put_latest(self, payload: dict[str, Any]) -> None:
        queue = self._queue
        if queue is None:
            return
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:  # pragma: no cover - same-loop defensive guard
                pass
        queue.put_nowait(payload)

    async def _run(self) -> None:
        queue = self._queue
        client = self._client
        if queue is None or client is None:  # pragma: no cover - guarded by start()
            return

        while True:
            payload = await queue.get()
            retry_seconds = self._initial_retry_seconds

            while payload is not None:
                try:
                    response = await client.post(
                        f"{self._base_url}{SIMPLE_METRIC_PATH}",
                        json=payload,
                        timeout=self._timeout_seconds,
                    )
                    response.raise_for_status()
                    payload = None
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._warn_rate_limited(exc)
                    try:
                        payload = await asyncio.wait_for(
                            queue.get(),
                            timeout=retry_seconds,
                        )
                        retry_seconds = self._initial_retry_seconds
                    except asyncio.TimeoutError:
                        retry_seconds = min(
                            retry_seconds * 2,
                            self._max_retry_seconds,
                        )

    def _warn_rate_limited(self, exc: Exception) -> None:
        now = time.monotonic()
        if now - self._last_warning_at < self._warning_interval_seconds:
            return
        self._last_warning_at = now
        logger.warning("Unable to publish throughput to Metrics Manager: %s", exc)


_publisher = MetricsManagerPublisher(
    settings.METRICS_MANAGER_URL,
    settings.METRICS_MANAGER_TIMEOUT_SECONDS,
)


async def start_metrics_publisher() -> None:
    """Start the process-wide publisher."""

    await _publisher.start()


async def stop_metrics_publisher() -> None:
    """Stop the process-wide publisher."""

    await _publisher.stop()


def publish_embeddings_throughput(value: object, timestamp: object) -> bool:
    """Enqueue one completed-pipeline throughput sample."""

    return _publisher.publish(value, timestamp)


__all__ = [
    "METRIC_NAME",
    "METRIC_TAGS",
    "MetricsManagerPublisher",
    "publish_embeddings_throughput",
    "start_metrics_publisher",
    "stop_metrics_publisher",
]
