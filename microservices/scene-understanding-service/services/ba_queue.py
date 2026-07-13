# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
MQTT-based queue for Behavioral Analysis requests/results.

Publisher:  scene-understanding-service → ba/requests
Consumer:   ba/results → scene-understanding-service

Uses the existing MQTTService's broker connection settings.
"""

import json
import logging
from typing import Callable, Awaitable, Optional

import structlog

logger = structlog.get_logger(__name__)

# Default topics (overridable via the `mqtt` config block).
DEFAULT_BA_REQUEST_TOPIC = "ba/requests"
DEFAULT_BA_RESULT_TOPIC = "ba/results"


class BAQueuePublisher:
    """
    Publishes BA frame-arrival events to MQTT topic ba/requests.

    scene-understanding-service emits one ba/requests message every time a fresh frame for
    a HIGH_VALUE-zone person has been written to the SeaweedFS
    ``behavioral-frames`` bucket. The behavioural-analysis service consumes
    each message, fetches the latest K frames for that visit, runs pose +
    VLM, and publishes a single ``ba/results`` message in response. There
    is no start/exit lifecycle and no polling loop on the BA side.
    """

    def __init__(self, mqtt_service, request_topic: str = DEFAULT_BA_REQUEST_TOPIC) -> None:
        self._mqtt = mqtt_service
        self._request_topic = request_topic

    def publish_request(
        self, person_id: str, region_id: str, entry_timestamp: str,
        scene_id: str = "", last_frame_ts: str = "",
    ) -> None:
        """Publish one ba/requests message for a freshly stored frame."""
        payload = {
            "person_id": person_id,
            "region_id": region_id,
            "entry_timestamp": entry_timestamp,
            "scene_id": scene_id,
            "last_frame_ts": last_frame_ts,
        }
        self._mqtt.publish(self._request_topic, payload)
        logger.debug(
            "Published BA request",
            person_id=person_id,
            region_id=region_id,
            scene_id=scene_id,
            last_frame_ts=last_frame_ts,
        )


class BAQueueConsumer:
    """
    Subscribes to ba/results and dispatches to a handler callback.

    Subscribes via the existing MQTTService's paho client so we reuse the
    same broker connection — no second MQTT client needed.
    """

    def __init__(self, mqtt_service, result_topic: str = DEFAULT_BA_RESULT_TOPIC) -> None:
        self._mqtt = mqtt_service
        self._result_topic = result_topic
        self._handler: Optional[Callable[[dict], Awaitable[None]]] = None

    def register_result_handler(
        self, handler: Callable[[dict], Awaitable[None]]
    ) -> None:
        """Register async callback for BA results."""
        self._handler = handler

    def subscribe(self) -> None:
        """
        Subscribe to ba/results using the paho client from MQTTService.

        Must be called AFTER MQTTService has connected (on_connect fired).
        """
        if self._mqtt.client and self._mqtt.connected:
            self._mqtt.client.subscribe(self._result_topic, qos=1)
            self._mqtt.client.message_callback_add(
                self._result_topic, self._on_message
            )
            logger.info("Subscribed to BA results topic", topic=self._result_topic)
        else:
            # If not connected yet, hook into the existing on_connect
            original_on_connect = self._mqtt.client.on_connect

            def _patched_on_connect(client, userdata, flags, rc):
                original_on_connect(client, userdata, flags, rc)
                if rc == 0:
                    client.subscribe(self._result_topic, qos=1)
                    client.message_callback_add(
                        self._result_topic, self._on_message
                    )
                    logger.info(
                        "Subscribed to BA results topic (on connect)",
                        topic=self._result_topic,
                    )

            self._mqtt.client.on_connect = _patched_on_connect
            logger.info(
                "Will subscribe to BA results on MQTT connect",
                topic=self._result_topic,
            )

    def _on_message(self, client, userdata, msg) -> None:
        """Handle incoming ba/results messages."""
        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            logger.error("Invalid JSON in BA result message")
            return

        if not self._handler or not self._mqtt.loop:
            return

        import asyncio
        asyncio.run_coroutine_threadsafe(
            self._handler(payload), self._mqtt.loop
        )
