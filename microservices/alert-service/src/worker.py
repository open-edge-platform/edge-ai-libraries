"""Async background worker that processes alerts from the queue."""

from __future__ import annotations

import asyncio
import logging

from src.core.config import AppConfig
from src.core.models import AlertEnvelope
from src.dedup.engine import DedupEngine
from src.delivery.registry import get_handler

logger = logging.getLogger(__name__)


class AlertWorker:
    """Background worker: dedup -> route -> deliver."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._queue: asyncio.Queue[AlertEnvelope] = asyncio.Queue()
        self._dedup = DedupEngine()
        self._running = False
        self._task: asyncio.Task | None = None

    async def enqueue(self, envelope: AlertEnvelope) -> None:
        """Add an alert to the processing queue."""
        await self._queue.put(envelope)

    async def start(self) -> None:
        """Start the background worker loop."""
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Alert worker started")

    async def stop(self) -> None:
        """Gracefully stop the worker."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Alert worker stopped")

    async def _run(self) -> None:
        """Main worker loop."""
        while self._running:
            try:
                envelope = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                await self._process(envelope)
            except Exception:
                logger.exception(
                    "Unhandled error processing alert: alert_type=%s",
                    envelope.alert_type,
                )

    async def _process(self, envelope: AlertEnvelope) -> None:
        """Process a single alert: dedup -> route -> deliver."""
        subscription = self._config.get_subscription(envelope.alert_type)
        if subscription is None:
            logger.warning(
                "No subscription for alert_type=%s, dropping",
                envelope.alert_type,
            )
            return

        # Dedup check
        if await self._dedup.is_duplicate(envelope, subscription.dedup):
            logger.info(
                "Alert deduplicated: alert_type=%s", envelope.alert_type
            )
            return

        # Deliver to all configured targets
        for target in subscription.delivery:
            await self._deliver_with_retry(envelope, target)

    async def _deliver_with_retry(self, envelope: AlertEnvelope, target) -> None:
        """Deliver with configurable retry on failure."""
        retry_attempts = self._config.service.retry_attempts
        retry_interval = self._config.service.retry_interval_seconds

        handler = get_handler(target.type)

        for attempt in range(1, retry_attempts + 1):
            try:
                await handler.deliver(envelope, target)
                return
            except Exception:
                logger.warning(
                    "Delivery failed: type=%s alert_type=%s attempt=%d/%d",
                    target.type,
                    envelope.alert_type,
                    attempt,
                    retry_attempts,
                    exc_info=True,
                )
                if attempt < retry_attempts:
                    await asyncio.sleep(retry_interval)

        logger.error(
            "Delivery exhausted all retries: type=%s alert_type=%s",
            target.type,
            envelope.alert_type,
        )
