"""WebSocket delivery handler — broadcasts alerts to connected WS clients."""

from __future__ import annotations

import json
import logging

from src.core.config import DeliveryTarget
from src.core.models import AlertEnvelope
from src.delivery.base import DeliveryHandler
from src.delivery.ws_manager import ws_manager

logger = logging.getLogger(__name__)


class WebSocketHandler(DeliveryHandler):
    """Delivers alerts by broadcasting to all connected WebSocket clients."""

    async def deliver(
        self, envelope: AlertEnvelope, target: DeliveryTarget
    ) -> None:
        if ws_manager.active_count == 0:
            logger.debug("No WebSocket clients connected, skipping broadcast")
            return

        message = json.dumps(envelope.to_dict())
        await ws_manager.broadcast(message)

        logger.info(
            "WebSocket broadcast: alert_type=%s clients=%d",
            envelope.alert_type,
            ws_manager.active_count,
        )
