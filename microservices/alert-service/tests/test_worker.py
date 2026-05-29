"""Tests for the alert worker."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import (
    AppConfig,
    DedupConfig,
    DeliveryTarget,
    HashConfig,
    ServiceConfig,
    SubscriptionConfig,
)
from src.core.models import AlertEnvelope
from src.worker import AlertWorker


@pytest.fixture
def worker_config():
    return AppConfig(
        service=ServiceConfig(retry_attempts=2, retry_interval_seconds=0),
        subscriptions=[
            SubscriptionConfig(
                alert_type="TEST",
                dedup=DedupConfig(enabled=False),
                delivery=[DeliveryTarget(type="log")],
            )
        ],
    )


class TestAlertWorker:
    async def test_worker_processes_alert(self, worker_config):
        """Worker dequeues and processes a matching alert."""
        worker = AlertWorker(worker_config)
        await worker.start()

        envelope = AlertEnvelope.from_raw({
            "alert_type": "TEST",
            "metadata": {"key": "value"},
        })
        await worker.enqueue(envelope)

        # Give the worker time to process
        await asyncio.sleep(0.2)
        await worker.stop()

    async def test_worker_drops_unsubscribed_alert(self, worker_config):
        """Worker drops alerts with no matching subscription."""
        worker = AlertWorker(worker_config)
        await worker.start()

        envelope = AlertEnvelope.from_raw({
            "alert_type": "NONEXISTENT",
            "metadata": {},
        })
        await worker.enqueue(envelope)

        await asyncio.sleep(0.2)
        await worker.stop()

    async def test_worker_retry_on_failure(self):
        """Worker retries delivery when the handler raises an exception."""
        config = AppConfig(
            service=ServiceConfig(retry_attempts=2, retry_interval_seconds=0),
            subscriptions=[
                SubscriptionConfig(
                    alert_type="RETRY_TEST",
                    dedup=DedupConfig(enabled=False),
                    delivery=[
                        DeliveryTarget(type="webhook", url="http://fail.test")
                    ],
                )
            ],
        )
        worker = AlertWorker(config)
        await worker.start()

        envelope = AlertEnvelope.from_raw({
            "alert_type": "RETRY_TEST",
            "metadata": {},
        })

        with patch(
            "src.delivery.webhook.WebhookHandler.deliver",
            new_callable=AsyncMock,
            side_effect=Exception("connection refused"),
        ):
            await worker.enqueue(envelope)
            await asyncio.sleep(0.5)

        await worker.stop()

    async def test_worker_start_stop(self, worker_config):
        """Worker starts and stops cleanly with _running flag."""
        worker = AlertWorker(worker_config)
        await worker.start()
        assert worker._running is True
        await worker.stop()
        assert worker._running is False
