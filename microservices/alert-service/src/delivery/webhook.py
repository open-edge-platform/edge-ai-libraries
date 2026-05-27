"""Webhook delivery handler."""

from __future__ import annotations

import json
import logging

import httpx

from src.core.config import DeliveryTarget
from src.core.models import AlertEnvelope
from src.delivery.base import DeliveryHandler

logger = logging.getLogger(__name__)


class WebhookHandler(DeliveryHandler):
    """Delivers alerts via HTTP POST to a webhook URL."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def deliver(
        self, envelope: AlertEnvelope, target: DeliveryTarget
    ) -> None:
        if not target.url:
            raise ValueError("Webhook URL not configured")

        client = await self._get_client()
        payload = json.dumps(envelope.to_dict())

        response = await client.post(
            target.url,
            content=payload,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        logger.info(
            "Webhook delivered: alert_type=%s url=%s status=%d",
            envelope.alert_type,
            target.url,
            response.status_code,
        )
