# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""WARNING: Legacy feature, may be removed in future releases.  Use with caution.
MQTT publisher GStreamer BaseSink element.

Extracts GVA metadata (and optionally the raw video frame) from each buffer
and publishes a JSON message to an MQTT broker.

GStreamer element name: ``mqttsinkpy``

Properties
----------
topic (str)           MQTT topic to publish to.
                      Default: ``dlstreamer_pipeline_results``.
publish-frame (bool)  Include base-64 encoded raw frame bytes in the message.
                      Default: ``False``.
qos (int)             MQTT QoS level (0 / 1 / 2).  Default: ``0``.

Environment variables
---------------------
MQTT_HOST   Broker hostname or IP address (required).
MQTT_PORT   Broker port.  Default: ``1883``.

Message format
--------------
Each published message is a JSON object::

    {
        "metadata": {
            "regions": [...],   // GVA detection regions
            "messages": [...]   // GVA messages attached to the buffer
        },
        "blob": "<base64>"      // raw frame bytes, or "" when publish-frame=false
    }
"""
from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
from collections import deque

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstBase", "1.0")
from gi.repository import GObject, Gst, GstBase  # noqa: E402

import paho.mqtt.client as mqtt  # noqa: E402
from gstgva import VideoFrame  # noqa: E402

logger = logging.getLogger(__name__)


def _tensor_to_dict(t) -> dict:
    """Best-effort conversion of a ``gstgva.Tensor`` to a JSON-serializable dict.

    Note: ``gstgva.Tensor`` has no ``as_dict()`` method, and calling ``label()``
    on a detection tensor raises ``RuntimeError`` -- fields must be read
    defensively.
    """
    d: dict = {"name": t.name()}
    for key, getter in (("layer_name", t.layer_name), ("model_name", t.model_name),
                        ("confidence", t.confidence)):
        try:
            d[key] = getter()
        except Exception:  # pylint: disable=broad-except
            pass
    if not t.is_detection():
        try:
            d["label"] = t.label()
        except Exception:  # pylint: disable=broad-except
            pass
    return d


def _extract_gva_meta(buf: Gst.Buffer, caps: Gst.Caps | None) -> dict:
    """Return a dict with ``regions`` and ``messages`` extracted from *buf*."""
    result: dict = {"regions": [], "messages": []}
    if caps is None:
        return result
    try:
        # Note: gstgva.VideoFrame does not support the context manager protocol
        # (no __enter__/__exit__) -- do not use it in a `with` statement, as that
        # always raises TypeError and silently drops all metadata via the except
        # clause below.
        vf = VideoFrame(buf, caps=caps)
        result["regions"] = [
            {
                "label": r.label(),
                "confidence": r.confidence(),
                "rect": {"x": r.rect().x, "y": r.rect().y,
                         "w": r.rect().w, "h": r.rect().h},
                "tensors": [_tensor_to_dict(t) for t in r.tensors()],
            }
            for r in vf.regions()
        ]
        # gstgva.util.GVAJSONMetaStr is a plain JSON-encoded str subclass, not an
        # object with as_dict() -- parse it into a dict instead.
        result["messages"] = [json.loads(str(m)) for m in vf.messages()]
    except Exception as exc:  # pylint: disable=broad-except
        logger.debug("GVA meta extraction failed: %s", exc)
    return result


class MqttSinkPy(GstBase.BaseSink):
    """GStreamer sink that publishes GVA metadata (and optionally frames) via MQTT."""

    __gstmetadata__ = (
        "MqttSinkPy",
        "Sink",
        "Publishes GVA metadata (and optionally raw frames) to an MQTT broker",
        "Intel",
    )
    __gsttemplates__ = Gst.PadTemplate.new(
        "sink",
        Gst.PadDirection.SINK,
        Gst.PadPresence.ALWAYS,
        Gst.Caps.new_any(),
    )
    __gproperties__ = {
        "topic": (
            GObject.TYPE_STRING,
            "MQTT topic",
            "Topic to publish messages to",
            "dlstreamer_pipeline_results",
            GObject.ParamFlags.READWRITE,
        ),
        "publish-frame": (
            GObject.TYPE_BOOLEAN,
            "Publish frame",
            "Include base-64 encoded raw frame bytes in the published message",
            False,
            GObject.ParamFlags.READWRITE,
        ),
        "qos": (
            GObject.TYPE_INT,
            "QoS",
            "MQTT Quality of Service level (0, 1, or 2)",
            0,
            2,
            0,
            GObject.ParamFlags.READWRITE,
        ),
    }

    def __init__(self):
        super().__init__()
        self._topic: str = "dlstreamer_pipeline_results"
        self._publish_frame: bool = False
        self._qos: int = 0
        self._queue: deque = deque(maxlen=1000)
        self._stop: threading.Event = threading.Event()
        self._thread: threading.Thread | None = None
        self._client: mqtt.Client | None = None

    # ------------------------------------------------------------------
    # GObject property accessors
    # ------------------------------------------------------------------

    def do_get_property(self, prop):
        if prop.name == "topic":
            return self._topic
        if prop.name == "publish-frame":
            return self._publish_frame
        if prop.name == "qos":
            return self._qos
        raise AttributeError(f"Unknown property: {prop.name}")

    def do_set_property(self, prop, value):
        if prop.name == "topic":
            self._topic = value
        elif prop.name == "publish-frame":
            self._publish_frame = value
        elif prop.name == "qos":
            self._qos = value
        else:
            raise AttributeError(f"Unknown property: {prop.name}")

    # ------------------------------------------------------------------
    # GstBaseSink lifecycle
    # ------------------------------------------------------------------

    def do_start(self) -> bool:
        host = os.environ.get("MQTT_HOST", "")
        port_str = os.environ.get("MQTT_PORT", "1883")
        if not host:
            logger.error("MQTT_HOST is not set — mqttsinkpy will drop all frames")
            # Return True so the pipeline still starts; frames are silently dropped.
            self._start_worker()
            return True

        try:
            port = int(port_str)
        except ValueError:
            logger.error("MQTT_PORT is not a valid integer: %r", port_str)
            self._start_worker()
            return True

        self._client = mqtt.Client()
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.on_connect = lambda _c, _u, _f, rc: (
            logger.info("mqttsinkpy connected to %s:%d (rc=%d)", host, port, rc)
        )
        self._client.on_disconnect = lambda _c, _u, rc: (
            logger.info("mqttsinkpy disconnected (rc=%d)", rc)
        )
        try:
            self._client.connect_async(host, port)
            self._client.loop_start()
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("mqttsinkpy connect_async failed: %s", exc)

        self._start_worker()
        return True

    def do_stop(self) -> bool:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:  # pylint: disable=broad-except
                pass
            self._client = None
        return True

    def do_render(self, buf: Gst.Buffer) -> Gst.FlowReturn:
        caps = self.get_static_pad("sink").get_current_caps()
        meta = _extract_gva_meta(buf, caps)

        frame_bytes: bytes | None = None
        if self._publish_frame:
            try:
                frame_bytes = buf.extract_dup(0, buf.get_size())
            except Exception as exc:  # pylint: disable=broad-except
                logger.debug("Frame extraction failed: %s", exc)

        self._queue.append((frame_bytes, meta))
        return Gst.FlowReturn.OK

    # ------------------------------------------------------------------
    # Worker thread
    # ------------------------------------------------------------------

    def _start_worker(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="mqttsinkpy-worker"
        )
        self._thread.start()

    def _worker(self) -> None:
        logger.info("mqttsinkpy worker started (topic=%s)", self._topic)
        while not self._stop.is_set():
            try:
                item = self._queue.popleft()
                self._publish(item)
            except IndexError:
                time.sleep(0.005)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("mqttsinkpy publish error: %s", exc)

    def _publish(self, item: tuple) -> None:
        if self._client is None:
            return
        frame_bytes, meta = item
        msg: dict = {"metadata": meta}
        if self._publish_frame and frame_bytes:
            msg["blob"] = base64.b64encode(frame_bytes).decode("utf-8")
        else:
            msg["blob"] = ""
        try:
            self._client.publish(
                self._topic, payload=json.dumps(msg), qos=self._qos
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("mqttsinkpy MQTT publish failed: %s", exc)


# ------------------------------------------------------------------
# GStreamer plugin registration  (runs at import time, after Gst.init())
# ------------------------------------------------------------------


def plugin_init(plugin) -> bool:
    GObject.type_register(MqttSinkPy)
    return Gst.Element.register(plugin, "mqttsinkpy", Gst.Rank.NONE, MqttSinkPy)


Gst.Plugin.register_static(
    1,
    0,
    "mqttsinkpyplugin",
    "MQTT metadata/frame publisher sink",
    plugin_init,
    "1.0",
    "Apache-2.0",
    "dlsps2",
    "dlsps2",
    "",
)
