# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""MQTT subscriber — listens to DL Streamer detection events and writes to storage-service."""

import json
import logging
import os
import threading

import paho.mqtt.client as mqtt

from .utility import storage_client

log = logging.getLogger(__name__)

_MQTT_HOST  = os.environ.get("MQTT_HOST", "mqtt-broker")
_MQTT_PORT  = int(os.environ.get("MQTT_PORT", "1883"))
_MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "dlstreamer/detections")

# Optional callback invoked after each batch write (used by main.py to trigger pipeline run)
_on_detection_callback = None


def set_on_detection_callback(fn):
    global _on_detection_callback
    _on_detection_callback = fn


def _on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        client.subscribe(_MQTT_TOPIC)
        log.info("MQTT connected; subscribed to %s", _MQTT_TOPIC)
    else:
        log.error("MQTT connection failed with rc=%s", rc)


def _on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))

        # DL Streamer wraps detections: {"metadata": {"objects": [...], "timestamp": ...}, "blob": ""}
        # Fall back to treating payload as a flat detection or list for other sources.
        if isinstance(payload, dict) and "metadata" in payload:
            meta = payload["metadata"]
            timestamp_ns = meta.get("timestamp", 0)
            frame_id = timestamp_ns // 33_333_333  # ~frame number at 30fps
            objects = meta.get("objects", [])
            detections = []
            for obj in objects:
                det = obj.get("detection", {})
                label = det.get("label") or obj.get("roi_type", "unknown")
                confidence = float(det.get("confidence", 0.0))
                detections.append({
                    "frame_id":   frame_id,
                    "label":      label,
                    "confidence": confidence,
                    "x":          int(obj.get("x", 0)),
                    "y":          int(obj.get("y", 0)),
                    "width":      int(obj.get("w", obj.get("width", 0))),
                    "height":     int(obj.get("h", obj.get("height", 0))),
                    "metadata":   json.dumps(det.get("bounding_box", {})),
                })
        elif isinstance(payload, list):
            detections = payload
        else:
            detections = [payload]

        for det in detections:
            storage_client.post_detection({
                "frame_id":   det.get("frame_id", 0),
                "label":      det.get("label", "unknown"),
                "confidence": float(det.get("confidence", 0.0)),
                "x":          int(det.get("x", 0)),
                "y":          int(det.get("y", 0)),
                "width":      int(det.get("width", 0)),
                "height":     int(det.get("height", 0)),
                "metadata":   det.get("metadata", json.dumps({})),
            })

        if _on_detection_callback:
            _on_detection_callback(len(detections))

    except Exception as exc:
        log.error("Error processing MQTT message: %s", exc)


def start_subscriber() -> mqtt.Client:
    """Start the MQTT subscriber in a background daemon thread.

    Returns the mqtt.Client so callers can access it if needed.
    """
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = _on_connect
    client.on_message = _on_message

    client.connect(_MQTT_HOST, _MQTT_PORT, keepalive=60)

    thread = threading.Thread(target=client.loop_forever, daemon=True)
    thread.start()
    log.info("MQTT subscriber started (host=%s port=%d topic=%s)", _MQTT_HOST, _MQTT_PORT, _MQTT_TOPIC)
    return client
