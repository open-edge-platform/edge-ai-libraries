"""MQTT delivery handler."""

from __future__ import annotations

import json
import logging

import aiomqtt

from src.core.config import DeliveryTarget
from src.core.models import AlertEnvelope
from src.core.settings import settings
from src.delivery.base import DeliveryHandler

logger = logging.getLogger(__name__)


class MqttHandler(DeliveryHandler):
    """Delivers alerts via MQTT publish."""

    async def deliver(
        self, envelope: AlertEnvelope, target: DeliveryTarget
    ) -> None:
        topic = target.topic or f"alerts/{envelope.alert_type.lower()}"
        payload = json.dumps(envelope.to_dict())

        kwargs: dict = {
            "hostname": settings.mqtt_broker,
            "port": settings.MQTT_PORT,
        }
        if settings.MQTT_USERNAME:
            kwargs["username"] = settings.MQTT_USERNAME
        if settings.MQTT_PASSWORD:
            kwargs["password"] = settings.MQTT_PASSWORD

        async with aiomqtt.Client(**kwargs) as client:
            await client.publish(topic, payload.encode())

        logger.info(
            "MQTT published: alert_type=%s topic=%s",
            envelope.alert_type,
            topic,
        )
