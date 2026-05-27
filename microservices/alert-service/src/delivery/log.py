"""Log delivery handler."""

from __future__ import annotations

import logging

from src.core.config import DeliveryTarget
from src.core.models import AlertEnvelope
from src.delivery.base import DeliveryHandler

logger = logging.getLogger(__name__)


class LogHandler(DeliveryHandler):
    """Delivers alerts by logging them."""

    async def deliver(
        self, envelope: AlertEnvelope, target: DeliveryTarget
    ) -> None:
        logger.info(
            "ALERT DELIVERED [%s]: metadata=%s timestamp=%s",
            envelope.alert_type,
            envelope.metadata,
            envelope.timestamp,
        )
