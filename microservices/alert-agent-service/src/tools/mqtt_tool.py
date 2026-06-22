# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
publish_mqtt tool — publishes alert notifications to an MQTT broker.

Configuration (environment variables):
    MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD, MQTT_BASE_TOPIC

Published topic: {MQTT_BASE_TOPIC}/{source_id}/{alert_name}

Uses a persistent MQTT client with auto-reconnect to avoid the overhead
of creating a new TCP connection per publish.
"""

import asyncio
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import paho.mqtt.client as mqtt

from src.config import settings

logger = logging.getLogger(__name__)


class _MqttClientPool:
    """Singleton persistent MQTT client with lazy initialisation and auto-reconnect."""

    def __init__(self) -> None:
        self._client: Optional[mqtt.Client] = None
        self._connected = False
        self._lock = threading.Lock()

    def _ensure_connected(self) -> mqtt.Client:
        """Return a connected MQTT client, creating or reconnecting as needed."""
        with self._lock:
            if self._client is not None and self._connected:
                return self._client

            if self._client is None:
                self._client = mqtt.Client(
                    client_id=f"alert-agent-persistent",
                    protocol=mqtt.MQTTv5,
                )
                if settings.MQTT_USERNAME:
                    self._client.username_pw_set(
                        settings.MQTT_USERNAME, settings.MQTT_PASSWORD
                    )
                self._client.on_connect = self._on_connect
                self._client.on_disconnect = self._on_disconnect
                self._client.loop_start()

            if not self._connected:
                self._client.connect(
                    settings.MQTT_BROKER,
                    settings.MQTT_PORT,
                    keepalive=60,
                )
                # Wait briefly for the connection callback
                for _ in range(20):
                    if self._connected:
                        break
                    time.sleep(0.1)

            return self._client

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self._connected = True
            logger.info("MQTT persistent client connected")
        else:
            logger.warning(f"MQTT connect returned rc={rc}")

    def _on_disconnect(self, client, userdata, rc, properties=None):
        self._connected = False
        if rc != 0:
            logger.warning(f"MQTT unexpected disconnect (rc={rc}), will auto-reconnect")

    def publish(self, topic: str, payload: str, qos: int = 1) -> int:
        """Publish a message. Returns MQTT rc (0 = success)."""
        client = self._ensure_connected()
        result = client.publish(topic, payload, qos=qos)
        result.wait_for_publish(timeout=5)
        return result.rc

    def shutdown(self):
        """Gracefully disconnect and stop the network loop."""
        with self._lock:
            if self._client is not None:
                try:
                    self._client.disconnect()
                    self._client.loop_stop()
                except Exception:
                    pass
                self._client = None
                self._connected = False


_mqtt_pool = _MqttClientPool()


def shutdown_mqtt():
    """Call during application shutdown to cleanly close the MQTT connection."""
    _mqtt_pool.shutdown()


async def publish_mqtt(
    source_id: str,
    alert_name: str,
    answer: str,
    reason: str,
    topic_override: Optional[str] = None,
    metadata: Optional[dict] = None,
    payload: Optional[dict] = None,
    timestamp: Optional[str] = None,
) -> dict:
    """Publish an alert event to an MQTT broker.

    The published payload is compatible with the alert-service AlertEnvelope
    format so downstream consumers (UI, dashboards) receive the expected
    ``alert_type``, ``metadata``, ``payload``, and ``timestamp`` fields.
    """
    broker = settings.MQTT_BROKER
    if not broker:
        logger.warning("publish_mqtt: MQTT_BROKER not configured — skipping")
        return {"status": "skipped", "reason": "MQTT_BROKER not configured"}

    topic = topic_override or f"{settings.MQTT_BASE_TOPIC}/{alert_name.lower()}"

    ts = timestamp or datetime.now(tz=timezone.utc).isoformat()
    merged_metadata = dict(metadata) if metadata else {}
    merged_metadata.setdefault("source_id", source_id)
    merged_metadata.setdefault("reason", reason)

    message: dict = {
        # alert-service AlertEnvelope compatible fields
        "alert_type": alert_name,
        "metadata": merged_metadata,
        "timestamp": ts,
        # extended fields for richer consumers
        "source_id": source_id,
        "alert_name": alert_name,
        "answer": answer,
        "reason": reason,
    }
    if payload:
        message["payload"] = payload

    mqtt_payload = json.dumps(message)

    try:
        rc = await asyncio.to_thread(_mqtt_pool.publish, topic, mqtt_payload)
        if rc == 0:
            logger.info(f"MQTT published | topic={topic} | alert={alert_name}")
            return {"status": "published", "topic": topic, "rc": rc}
        else:
            logger.error(f"MQTT publish failed | rc={rc}")
            return {"status": "error", "topic": topic, "rc": rc}
    except Exception as exc:
        logger.error(f"publish_mqtt error: {exc}")
        return {"status": "error", "reason": str(exc)}
