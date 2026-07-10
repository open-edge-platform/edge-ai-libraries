# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""MQTT service – subscribes to SceneScape topics and dispatches callbacks."""

import asyncio
import json
import os
import ssl
import re
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable

import paho.mqtt.client as mqtt
import structlog

from .config import ConfigService

logger = structlog.get_logger(__name__)


class MQTTService:
    """
    Connects to the SceneScape MQTT broker, subscribes to scene-data
    and camera-image topics, and forwards payloads to registered handlers.
    """

    def __init__(self, config: ConfigService) -> None:
        self.config = config
        mqtt_cfg = config.get_mqtt_config()

        self.host = mqtt_cfg.get("host", "localhost")
        self.port = mqtt_cfg.get("port", 1883)
        self.use_tls = mqtt_cfg.get("use_tls", False)
        self.ca_cert_path = mqtt_cfg.get("ca_cert_path", "secrets/certs/scenescape-ca.pem")
        self.cert_required = mqtt_cfg.get("cert_required", False)
        self.verify_hostname = mqtt_cfg.get("verify_hostname", False)
        self.username = mqtt_cfg.get("username")
        self.password = mqtt_cfg.get("password")

        self.scene_data_topic = config.get_scene_data_topic()
        self.region_event_topic = config.get_region_event_topic()
        self.image_topic_pattern = config.get_image_topic_pattern()
        self.alert_topic_prefix = config.get_alert_topic_prefix()

        self.client: Optional[mqtt.Client] = None
        self.connected = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._shutdown = asyncio.Event()

        # Scene data pattern: scenescape/data/scene/{scene_id}/{object_type}
        self._scene_pattern = re.compile(r"scenescape/data/scene/([^/]+)/([^/]+)")
        # Region data pattern: scenescape/data/region/{scene_id}/{region_id}
        self._region_data_pattern = re.compile(r"scenescape/data/region/([^/]+)/([^/]+)")
        # Region event pattern: scenescape/event/region/{scene_id}/{region_id}/{suffix}
        self._region_event_pattern = re.compile(r"scenescape/event/region/([^/]+)/([^/]+)/([^/]+)")
        # Image pattern: scenescape/image/camera/{camera_name}
        self._image_pattern = re.compile(r"scenescape/image/camera/([^/]+)")

        # Callbacks set by the application layer
        self._on_scene_data: Optional[Callable] = None
        self._on_region_data: Optional[Callable] = None
        self._on_region_event: Optional[Callable] = None
        self._on_camera_image: Optional[Callable] = None

        logger.info(
            "MQTTService initialized",
            host=self.host,
            port=self.port,
            use_tls=self.use_tls,
            scene_topic=self.scene_data_topic,
            region_event_topic=self.region_event_topic,
            image_topic=self.image_topic_pattern,
        )

    # ---- public registration ------------------------------------------------
    def register_scene_data_handler(self, handler: Callable) -> None:
        self._on_scene_data = handler

    def register_region_data_handler(self, handler: Callable) -> None:
        self._on_region_data = handler

    def register_region_event_handler(self, handler: Callable) -> None:
        self._on_region_event = handler

    def register_camera_image_handler(self, handler: Callable) -> None:
        self._on_camera_image = handler

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    # ---- lifecycle -----------------------------------------------------------
    async def initialize(self) -> None:
        self.client = mqtt.Client()

        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)

        if self.use_tls:
            ca_path = self._resolve_cert_path(self.ca_cert_path)
            cert_reqs = ssl.CERT_REQUIRED if self.cert_required else ssl.CERT_NONE
            self.client.tls_set(
                ca_certs=ca_path,
                cert_reqs=cert_reqs,
            )
            self.client.tls_insecure_set(not self.verify_hostname)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        logger.info("MQTT client created")

    async def start(self) -> None:
        logger.info("Connecting to MQTT broker", host=self.host, port=self.port)
        self.client.connect_async(self.host, self.port, keepalive=60)
        self.client.loop_start()
        await self._shutdown.wait()

    async def stop(self) -> None:
        self._shutdown.set()
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
        logger.info("MQTT service stopped")

    def publish(self, topic: str, payload: dict) -> None:
        """Publish a JSON payload to a topic."""
        if self.client and self.connected:
            self.client.publish(topic, json.dumps(payload), qos=1)

    def publish_raw(self, topic: str, payload: str) -> None:
        """Publish a raw string payload to a topic."""
        if self.client and self.connected:
            self.client.publish(topic, payload, qos=1)

    # ---- paho callbacks ------------------------------------------------------
    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            self.connected = True
            logger.info("MQTT connected, subscribing to topics")
            client.subscribe(self.scene_data_topic, qos=1)
            client.subscribe("scenescape/data/region/+/+/+", qos=1)
            client.subscribe(self.region_event_topic, qos=1)
            client.subscribe(self.image_topic_pattern, qos=1)
        else:
            logger.error("MQTT connect failed", rc=rc)

    def _on_disconnect(self, client, userdata, rc) -> None:
        self.connected = False
        logger.warning("MQTT disconnected", rc=rc)

    def _on_message(self, client, userdata, msg: mqtt.MQTTMessage) -> None:
        topic = msg.topic

        # Region events take priority (most specific pattern)
        region_match = self._region_event_pattern.match(topic)
        if region_match:
            self._dispatch_region_event(
                region_match.group(1), region_match.group(2),
                region_match.group(3), msg.payload,
            )
            return

        # Region data (continuous feed with objects in each region)
        region_data_match = self._region_data_pattern.match(topic)
        if region_data_match:
            logger.info("MATCHED region data topic", topic=topic)
            self._dispatch_region_data(
                region_data_match.group(1), region_data_match.group(2), msg.payload,
            )
            return

        scene_match = self._scene_pattern.match(topic)
        if scene_match:
            self._dispatch_scene(scene_match.group(1), scene_match.group(2), msg.payload)
            return

        image_match = self._image_pattern.match(topic)
        if image_match:
            self._dispatch_image(image_match.group(1), msg.payload)
            return

    # ---- dispatch helpers ----------------------------------------------------
    def _dispatch_scene(self, scene_id: str, object_type: str, payload: bytes) -> None:
        if not self._on_scene_data or not self.loop:
            return
        try:
            data = json.loads(payload)
            asyncio.run_coroutine_threadsafe(
                self._on_scene_data(scene_id, object_type, data), self.loop
            )
        except json.JSONDecodeError:
            logger.error("Invalid JSON in scene message")

    def _dispatch_region_data(
        self, scene_id: str, region_id: str, payload: bytes
    ) -> None:
        if not self._on_region_data or not self.loop:
            return
        try:
            data = json.loads(payload)
            asyncio.run_coroutine_threadsafe(
                self._on_region_data(scene_id, region_id, data), self.loop
            )
        except json.JSONDecodeError:
            logger.error("Invalid JSON in region data message")

    def _dispatch_region_event(
        self, scene_id: str, region_id: str, suffix: str, payload: bytes
    ) -> None:
        if not self._on_region_event or not self.loop:
            return
        try:
            data = json.loads(payload)
            asyncio.run_coroutine_threadsafe(
                self._on_region_event(scene_id, region_id, data), self.loop
            )
        except json.JSONDecodeError:
            logger.error("Invalid JSON in region event message")

    def _dispatch_image(self, camera_name: str, payload: bytes) -> None:
        if not self._on_camera_image or not self.loop:
            return
        # Camera image payloads are 1-4 MB (base64 frame in JSON).
        # Parsing in paho's network thread blocks all other topic dispatch.
        # Submit the raw payload to the event loop; parse in a thread there.
        asyncio.run_coroutine_threadsafe(
            self._parse_and_dispatch_image(camera_name, payload), self.loop
        )

    async def _parse_and_dispatch_image(self, camera_name: str, payload: bytes) -> None:
        """Parse large image JSON off the main thread, then dispatch."""
        try:
            data = await asyncio.to_thread(json.loads, payload)
        except (json.JSONDecodeError, Exception):
            logger.error("Invalid JSON in image message")
            return
        await self._on_camera_image(camera_name, data)

    # ---- helpers -------------------------------------------------------------
    def _resolve_cert_path(self, rel_path: str) -> str:
        app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full = os.path.join(app_root, rel_path)
        if os.path.exists(full):
            return full
        return rel_path
