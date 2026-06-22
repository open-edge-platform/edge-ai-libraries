"""Tests for delivery handlers."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import DeliveryTarget
from src.core.models import AlertEnvelope
from src.delivery.log import LogHandler
from src.delivery.mqtt import MqttHandler
from src.delivery.registry import get_handler
from src.delivery.websocket import WebSocketHandler
from src.delivery.ws_manager import ConnectionManager


class TestLogHandler:
    async def test_deliver_logs(self, sample_concealment_alert, caplog):
        """LogHandler writes ALERT DELIVERED to the application log."""
        handler = LogHandler()
        envelope = AlertEnvelope.from_raw(sample_concealment_alert)
        target = DeliveryTarget(type="log")

        with caplog.at_level("INFO"):
            await handler.deliver(envelope, target)

        assert "ALERT DELIVERED" in caplog.text
        assert "CONCEALMENT" in caplog.text


class TestWebSocketHandler:
    async def test_deliver_broadcasts(self, sample_concealment_alert):
        """WebSocketHandler broadcasts JSON to connected clients."""
        handler = WebSocketHandler()
        envelope = AlertEnvelope.from_raw(sample_concealment_alert)
        target = DeliveryTarget(type="websocket")

        with patch("src.delivery.websocket.ws_manager") as mock_mgr:
            mock_mgr.active_count = 2
            mock_mgr.broadcast = AsyncMock()

            await handler.deliver(envelope, target)

            mock_mgr.broadcast.assert_called_once()
            payload = json.loads(mock_mgr.broadcast.call_args[0][0])
            assert payload["alert_type"] == "CONCEALMENT"

    async def test_deliver_skips_when_no_clients(self, sample_concealment_alert):
        """WebSocketHandler skips broadcast when no clients are connected."""
        handler = WebSocketHandler()
        envelope = AlertEnvelope.from_raw(sample_concealment_alert)
        target = DeliveryTarget(type="websocket")

        with patch("src.delivery.websocket.ws_manager") as mock_mgr:
            mock_mgr.active_count = 0
            mock_mgr.broadcast = AsyncMock()

            await handler.deliver(envelope, target)

            mock_mgr.broadcast.assert_not_called()


class TestMqttHandler:
    async def test_deliver_publishes(self, sample_concealment_alert):
        """MqttHandler publishes to the specified topic."""
        handler = MqttHandler()
        envelope = AlertEnvelope.from_raw(sample_concealment_alert)
        target = DeliveryTarget(type="mqtt", topic="alerts/concealment")

        mock_client = AsyncMock()
        mock_client.publish = AsyncMock()

        with patch("src.delivery.mqtt.aiomqtt.Client") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            await handler.deliver(envelope, target)

            MockClient.assert_called_once()
            call_kwargs = MockClient.call_args[1]
            assert "hostname" in call_kwargs
            assert call_kwargs["port"] == 1883

            mock_client.publish.assert_called_once()
            topic_arg = mock_client.publish.call_args[0][0]
            assert topic_arg == "alerts/concealment"

    async def test_deliver_default_topic(self, sample_concealment_alert):
        """MqttHandler defaults topic to alerts/{alert_type}."""
        handler = MqttHandler()
        envelope = AlertEnvelope.from_raw(sample_concealment_alert)
        target = DeliveryTarget(type="mqtt")  # no topic set

        mock_client = AsyncMock()
        mock_client.publish = AsyncMock()

        with patch("src.delivery.mqtt.aiomqtt.Client") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            await handler.deliver(envelope, target)

            topic_arg = mock_client.publish.call_args[0][0]
            assert topic_arg == "alerts/concealment"

    async def test_deliver_with_auth(self, sample_concealment_alert):
        """MqttHandler passes username and password when configured."""
        handler = MqttHandler()
        envelope = AlertEnvelope.from_raw(sample_concealment_alert)
        target = DeliveryTarget(type="mqtt")

        mock_client = AsyncMock()
        mock_client.publish = AsyncMock()

        with patch("src.delivery.mqtt.aiomqtt.Client") as MockClient, \
             patch("src.delivery.mqtt.settings") as mock_settings:
            mock_settings.mqtt_broker = "broker.example.com"
            mock_settings.MQTT_PORT = 1883
            mock_settings.MQTT_USERNAME = "user"
            mock_settings.MQTT_PASSWORD = "pass"

            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            await handler.deliver(envelope, target)

            call_kwargs = MockClient.call_args[1]
            assert call_kwargs["hostname"] == "broker.example.com"
            assert call_kwargs["username"] == "user"
            assert call_kwargs["password"] == "pass"


class TestDeliveryRegistry:
    def test_get_log_handler(self):
        """Registry returns a LogHandler for type 'log'."""
        handler = get_handler("log")
        assert isinstance(handler, LogHandler)

    def test_get_websocket_handler(self):
        """Registry returns a WebSocketHandler for type 'websocket'."""
        handler = get_handler("websocket")
        assert isinstance(handler, WebSocketHandler)

    def test_unknown_handler_raises(self):
        """Registry raises ValueError for an unknown handler type."""
        with pytest.raises(ValueError, match="Unknown delivery type"):
            get_handler("carrier_pigeon")


class TestConnectionManager:
    async def test_connect_and_active_count(self):
        """ConnectionManager increments active_count on connect."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws)
        assert mgr.active_count == 1
        ws.accept.assert_called_once()

    async def test_disconnect(self):
        """ConnectionManager decrements active_count on disconnect."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws)
        mgr.disconnect(ws)
        assert mgr.active_count == 0

    async def test_broadcast_sends_to_all(self):
        """ConnectionManager sends message to all connected clients."""
        mgr = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await mgr.connect(ws1)
        await mgr.connect(ws2)

        await mgr.broadcast("hello")

        ws1.send_text.assert_called_once_with("hello")
        ws2.send_text.assert_called_once_with("hello")

    async def test_broadcast_removes_dead_connections(self):
        """ConnectionManager removes clients that raise on send."""
        mgr = ConnectionManager()
        ws_good = AsyncMock()
        ws_dead = AsyncMock()
        ws_dead.send_text.side_effect = RuntimeError("closed")

        await mgr.connect(ws_good)
        await mgr.connect(ws_dead)
        assert mgr.active_count == 2

        await mgr.broadcast("test")

        assert mgr.active_count == 1
        ws_good.send_text.assert_called_once_with("test")
