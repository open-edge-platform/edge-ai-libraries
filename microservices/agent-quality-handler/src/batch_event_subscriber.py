# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Receive terminal Detection Service batch events over MQTT."""

import json
import logging
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable

import paho.mqtt.client as mqtt

from .utility.runtime_config import load_runtime_settings

log = logging.getLogger(__name__)

_on_batch_callback: Callable[["BatchEvent", "BatchDelivery"], None] | None = None


class InvalidBatchEvent(ValueError):
    """Raised when an MQTT payload violates the batch event contract."""


def _required_text(
    payload: Mapping[str, Any], name: str, *, maximum: int = 512
) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise InvalidBatchEvent(f"{name} must be a non-empty string")
    value = value.strip()
    if len(value) > maximum or "\x00" in value:
        raise InvalidBatchEvent(f"{name} is invalid")
    return value


def _optional_text(
    payload: Mapping[str, Any], name: str, *, maximum: int = 4096
) -> str | None:
    value = payload.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
        raise InvalidBatchEvent(f"{name} must be a valid string or null")
    return value


def _optional_status(
    payload: Mapping[str, Any], name: str
) -> Mapping[str, Any] | str | None:
    """pipeline_status may be the raw DL Streamer status object, a string, or null."""
    value = payload.get(name)
    if value is None or isinstance(value, str) or isinstance(value, Mapping):
        return value
    raise InvalidBatchEvent(f"{name} must be a string, object, or null")


def _non_negative_integer(payload: Mapping[str, Any], name: str) -> int:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidBatchEvent(f"{name} must be a non-negative integer")
    return value


@dataclass(frozen=True)
class BatchEvent:
    """Validated terminal event emitted by the external Detection Service."""

    run_id: str
    status: str
    device: str
    video_filename: str | None
    start_id: int | None
    end_id: int | None
    pipeline_status: Mapping[str, Any] | str | None
    error: str | None
    schema_version: str = "1.0"

    @classmethod
    def from_payload(cls, payload: Any) -> "BatchEvent":
        if not isinstance(payload, Mapping):
            raise InvalidBatchEvent("batch event must be a JSON object")
        version = payload.get("schema_version", "1.0")
        if version not in {"1", "1.0"}:
            raise InvalidBatchEvent("schema_version must be '1.0'")
        status = _required_text(payload, "status", maximum=16)
        if status not in {"completed", "error"}:
            raise InvalidBatchEvent("status must be 'completed' or 'error'")
        if status == "completed":
            start_id = _non_negative_integer(payload, "start_id")
            end_id = _non_negative_integer(payload, "end_id")
            if start_id >= end_id:
                raise InvalidBatchEvent(
                    "completed batches require start_id to be less than end_id"
                )
        else:
            # Error events may legitimately omit start_id/end_id (e.g. the
            # detection pipeline failed before either watermark was resolved).
            start_id = payload.get("start_id")
            end_id = payload.get("end_id")
            start_id = _non_negative_integer(payload, "start_id") if start_id is not None else None
            end_id = _non_negative_integer(payload, "end_id") if end_id is not None else None
        return cls(
            run_id=_required_text(payload, "run_id", maximum=128),
            status=status,
            device=_required_text(payload, "device"),
            video_filename=_optional_text(payload, "video_filename", maximum=4096),
            start_id=start_id,
            end_id=end_id,
            pipeline_status=_optional_status(payload, "pipeline_status"),
            error=_optional_text(payload, "error"),
            schema_version="1.0",
        )

    def metadata(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "device": self.device,
            "video_filename": self.video_filename,
            "start_id": self.start_id,
            "end_id": self.end_id,
            "pipeline_status": self.pipeline_status,
            "error": self.error,
        }


@dataclass
class BatchDelivery:
    """A manually acknowledged MQTT delivery that may outlive its callback."""

    client: mqtt.Client
    mid: int
    qos: int
    _acked: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def acknowledge(self) -> bool:
        with self._lock:
            if self._acked or not self.qos:
                self._acked = True
                return True
            result = self.client.ack(self.mid, self.qos)
            if result != mqtt.MQTT_ERR_SUCCESS:
                log.error("Failed to acknowledge batch event %s: %s", self.mid, result)
                return False
            self._acked = True
            return True


def set_on_batch_callback(
    callback: Callable[[BatchEvent, BatchDelivery], None] | None,
) -> None:
    global _on_batch_callback
    _on_batch_callback = callback


def _on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code != 0:
        log.error("MQTT connection failed with reason code %s", reason_code)
        return
    result, _ = client.subscribe(userdata["topic"], qos=userdata["qos"])
    if result != mqtt.MQTT_ERR_SUCCESS:
        log.error(
            "MQTT batch subscription to %s failed with result %s",
            userdata["topic"],
            result,
        )
        return
    log.info(
        "MQTT connected; subscribed to %s at QoS %d",
        userdata["topic"],
        userdata["qos"],
    )


def _on_disconnect(client, userdata, disconnect_flags, reason_code, properties=None):
    if reason_code != 0:
        log.warning(
            "Unexpected MQTT disconnect (reason code %s); reconnecting",
            reason_code,
        )


def _on_message(client, userdata, msg):
    delivery = BatchDelivery(client=client, mid=msg.mid, qos=msg.qos)
    try:
        if len(msg.payload) > userdata.get("max_payload_bytes", 1_048_576):
            raise InvalidBatchEvent("payload exceeds configured size limit")
        payload = json.loads(msg.payload.decode("utf-8"))
        event = BatchEvent.from_payload(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, InvalidBatchEvent) as exc:
        log.warning("Discarding invalid batch event %s: %s", msg.mid, exc)
        delivery.acknowledge()
        return

    if _on_batch_callback is None:
        log.error("Batch event handler is not configured")
        return
    try:
        _on_batch_callback(event, delivery)
    except Exception:
        log.exception("Failed to accept batch event %s", msg.mid)


def start_subscriber(settings=None) -> mqtt.Client:
    """Start the batch event subscriber in a background daemon thread."""
    settings = settings or load_runtime_settings()
    if not settings.mqtt_enabled:
        raise RuntimeError("MQTT batch events are disabled")

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=settings.mqtt_batch_client_id,
        clean_session=False,
        userdata={
            "topic": settings.mqtt_batch_topic,
            "qos": settings.mqtt_qos,
            "max_payload_bytes": settings.mqtt_max_payload_bytes,
        },
        manual_ack=True,
    )
    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message = _on_message
    client.reconnect_delay_set(min_delay=1, max_delay=120)

    if settings.mqtt_username:
        client.username_pw_set(settings.mqtt_username, settings.mqtt_password)

    client.connect_async(
        settings.mqtt_host,
        settings.mqtt_port,
        keepalive=settings.mqtt_keepalive,
    )
    threading.Thread(
        target=client.loop_forever,
        kwargs={"retry_first_connection": True},
        daemon=True,
        name="batch-event-subscriber",
    ).start()
    log.info(
        "Batch subscriber started (host=%s port=%d topic=%s qos=%d)",
        settings.mqtt_host,
        settings.mqtt_port,
        settings.mqtt_batch_topic,
        settings.mqtt_qos,
    )
    return client
