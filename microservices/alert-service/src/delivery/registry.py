"""Delivery handler registry — maps type names to handler instances."""

from __future__ import annotations

from src.delivery.base import DeliveryHandler
from src.delivery.log import LogHandler
from src.delivery.mqtt import MqttHandler
from src.delivery.websocket import WebSocketHandler

_HANDLERS: dict[str, type[DeliveryHandler]] = {
    "websocket": WebSocketHandler,
    "mqtt": MqttHandler,
    "log": LogHandler,
}


def get_handler(delivery_type: str) -> DeliveryHandler:
    """Get a delivery handler instance by type name."""
    cls = _HANDLERS.get(delivery_type)
    if cls is None:
        raise ValueError(f"Unknown delivery type: {delivery_type}")
    return cls()
