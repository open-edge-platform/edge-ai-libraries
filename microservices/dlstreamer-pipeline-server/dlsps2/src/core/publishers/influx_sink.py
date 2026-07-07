# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""WARNING: Legacy feature, may be removed in future releases.  Use with caution.
InfluxDB publisher GStreamer BaseSink element.

Extracts GVA metadata and frame-level information from each buffer and writes
them as an InfluxDB data point using the ``influxdb-client`` library.

GStreamer element name: ``influxsinkpy``

Properties
----------
bucket (str)       InfluxDB bucket to write to.  Default: ``""``.
org (str)          InfluxDB organisation.  Default: ``""``.
measurement (str)  Measurement name.  Default: ``dlstreamer_metadata``.

Environment variables
---------------------
INFLUXDB_HOST   Server hostname or IP address.  Default: ``localhost``.
INFLUXDB_PORT   Server port.  Default: ``8086``.
INFLUXDB_USER   Username for basic-auth.
INFLUXDB_PASS   Password for basic-auth.

Data point fields
-----------------
Each buffer produces one InfluxDB Point with:

* tag  ``img_handle``  – UUID generated per frame
* fields ``height``, ``width``, ``channels``, ``caps``, ``img_format``,
  ``frame_id``, ``gva_meta`` (JSON string), ``resolution`` (JSON string),
  ``objects`` (JSON string), ``pipeline`` (JSON string)
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections import deque

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstBase", "1.0")
from gi.repository import GObject, Gst, GstBase  # noqa: E402

from gstgva import VideoFrame  # noqa: E402
from influxdb_client import InfluxDBClient, Point  # noqa: E402
from influxdb_client.client.write_api import SYNCHRONOUS  # noqa: E402

logger = logging.getLogger(__name__)

# Number of bytes per pixel for common GStreamer raw video formats.
_FORMAT_CHANNELS: dict[str, int] = {
    "BGR": 3,
    "RGB": 3,
    "GRAY8": 1,
    "BGRA": 4,
    "RGBA": 4,
    "BGRx": 4,
    "RGBx": 4,
}


def _extract_gva_meta(buf: Gst.Buffer, caps: Gst.Caps | None) -> dict:
    result: dict = {"regions": [], "messages": []}
    if caps is None:
        return result
    try:
        with VideoFrame(buf, caps=caps) as vf:
            result["regions"] = [
                {
                    "label": r.label(),
                    "confidence": r.confidence(),
                    "rect": {"x": r.rect().x, "y": r.rect().y,
                             "w": r.rect().w, "h": r.rect().h},
                    "tensors": [t.as_dict() for t in r.tensors()],
                }
                for r in vf.regions()
            ]
            result["messages"] = [m.as_dict() for m in vf.messages()]
    except Exception as exc:  # pylint: disable=broad-except
        logger.debug("GVA meta extraction failed: %s", exc)
    return result


def _caps_info(caps: Gst.Caps | None) -> tuple[int, int, int, str, str]:
    """Return (width, height, channels, img_format, caps_string) from *caps*."""
    if caps is None:
        return 0, 0, 0, "", ""
    try:
        s = caps.get_structure(0)
        width: int = s.get_value("width") or 0
        height: int = s.get_value("height") or 0
        fmt: str = s.get_value("format") or ""
        channels: int = _FORMAT_CHANNELS.get(fmt, 3)
        caps_str: str = caps.to_string()
        return width, height, channels, fmt, caps_str
    except Exception:  # pylint: disable=broad-except
        return 0, 0, 0, "", ""


class InfluxSinkPy(GstBase.BaseSink):
    """GStreamer sink that writes GVA metadata as InfluxDB data points."""

    __gstmetadata__ = (
        "InfluxSinkPy",
        "Sink",
        "Writes GVA metadata fields as InfluxDB data points",
        "Intel",
    )
    __gsttemplates__ = Gst.PadTemplate.new(
        "sink",
        Gst.PadDirection.SINK,
        Gst.PadPresence.ALWAYS,
        Gst.Caps.new_any(),
    )
    __gproperties__ = {
        "bucket": (
            GObject.TYPE_STRING,
            "InfluxDB bucket",
            "Bucket name to write data points to",
            "",
            GObject.ParamFlags.READWRITE,
        ),
        "org": (
            GObject.TYPE_STRING,
            "InfluxDB organisation",
            "Organisation name for the InfluxDB write endpoint",
            "",
            GObject.ParamFlags.READWRITE,
        ),
        "measurement": (
            GObject.TYPE_STRING,
            "Measurement name",
            "InfluxDB measurement (table) name",
            "dlstreamer_metadata",
            GObject.ParamFlags.READWRITE,
        ),
    }

    def __init__(self):
        super().__init__()
        self._bucket: str = ""
        self._org: str = ""
        self._measurement: str = "dlstreamer_metadata"
        self._queue: deque = deque(maxlen=1000)
        self._stop: threading.Event = threading.Event()
        self._thread: threading.Thread | None = None
        self._write_api = None

    # ------------------------------------------------------------------
    # GObject property accessors
    # ------------------------------------------------------------------

    def do_get_property(self, prop):
        if prop.name == "bucket":
            return self._bucket
        if prop.name == "org":
            return self._org
        if prop.name == "measurement":
            return self._measurement
        raise AttributeError(f"Unknown property: {prop.name}")

    def do_set_property(self, prop, value):
        if prop.name == "bucket":
            self._bucket = value
        elif prop.name == "org":
            self._org = value
        elif prop.name == "measurement":
            self._measurement = value
        else:
            raise AttributeError(f"Unknown property: {prop.name}")

    # ------------------------------------------------------------------
    # GstBaseSink lifecycle
    # ------------------------------------------------------------------

    def do_start(self) -> bool:
        host = os.environ.get("INFLUXDB_HOST", "localhost")
        port = os.environ.get("INFLUXDB_PORT", "8086")
        user = os.environ.get("INFLUXDB_USER", "")
        password = os.environ.get("INFLUXDB_PASS", "")

        if not user or not password:
            logger.error(
                "INFLUXDB_USER / INFLUXDB_PASS not set — influxsinkpy will drop all frames"
            )
        else:
            try:
                client = InfluxDBClient(
                    url=f"http://{host}:{port}",
                    username=user,
                    password=password,
                    org=self._org,
                )
                self._write_api = client.write_api(write_options=SYNCHRONOUS)
                logger.info("influxsinkpy connected to %s:%s", host, port)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("InfluxDB connect failed: %s", exc)
                self._write_api = None

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="influxsinkpy-worker"
        )
        self._thread.start()
        return True

    def do_stop(self) -> bool:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        return True

    def do_render(self, buf: Gst.Buffer) -> Gst.FlowReturn:
        caps = self.get_static_pad("sink").get_current_caps()
        width, height, channels, fmt, caps_str = _caps_info(caps)
        meta = _extract_gva_meta(buf, caps)

        frame_data = {
            "img_handle": str(uuid.uuid4()),
            "height": height,
            "width": width,
            "channels": channels,
            "img_format": fmt,
            "caps": caps_str,
            "frame_id": buf.pts,
            "time": int(time.time() * 1_000_000_000),
            "gva_meta": meta.get("regions", []),
            "resolution": {"width": width, "height": height},
            "pipeline": {},
            "objects": [],
        }
        self._queue.append(frame_data)
        return Gst.FlowReturn.OK

    # ------------------------------------------------------------------
    # Worker thread
    # ------------------------------------------------------------------

    def _worker(self) -> None:
        logger.info(
            "influxsinkpy worker started (bucket=%s, measurement=%s)",
            self._bucket,
            self._measurement,
        )
        while not self._stop.is_set():
            try:
                item = self._queue.popleft()
                self._publish(item)
            except IndexError:
                time.sleep(0.005)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("influxsinkpy publish error: %s", exc)

    def _publish(self, frame_data: dict) -> None:
        if self._write_api is None or not self._bucket:
            return
        try:
            img_handle = frame_data.get("img_handle", "na")
            point = Point(self._measurement).tag("img_handle", img_handle)
            for key in ("height", "width", "channels", "frame_id"):
                val = frame_data.get(key)
                if val is not None:
                    point = point.field(key, val)
            for key in ("caps", "img_format"):
                val = frame_data.get(key)
                if val:
                    point = point.field(key, val)
            for key in ("gva_meta", "resolution", "pipeline", "objects"):
                val = frame_data.get(key)
                if val is not None:
                    point = point.field(key, json.dumps(val))
            self._write_api.write(
                bucket=self._bucket, org=self._org, record=point
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("InfluxDB write failed: %s", exc)


# ------------------------------------------------------------------
# GStreamer plugin registration  (runs at import time, after Gst.init())
# ------------------------------------------------------------------


def plugin_init(plugin) -> bool:
    GObject.type_register(InfluxSinkPy)
    return Gst.Element.register(plugin, "influxsinkpy", Gst.Rank.NONE, InfluxSinkPy)


Gst.Plugin.register_static(
    1,
    0,
    "influxsinkpyplugin",
    "InfluxDB metadata publisher sink",
    plugin_init,
    "1.0",
    "Apache-2.0",
    "dlsps2",
    "dlsps2",
    "",
)
