# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""WARNING: Legacy feature, may be removed in future releases.  Use with caution.
OPC-UA publisher GStreamer BaseSink element.

Extracts GVA metadata from each buffer and writes a JSON string to a
configurable OPC-UA node variable.

GStreamer element name: ``opcuasinkpy``

Properties
----------
variable (str)  OPC-UA node ID to write to.  Default: ``ns=2;s=0``.

Environment variables
---------------------
OPCUA_SERVER_IP        Server hostname or IP address (required).
OPCUA_SERVER_PORT      Server port.  Default: ``4840``.
OPCUA_SERVER_USERNAME  Username for authenticated sessions (optional).
OPCUA_SERVER_PASSWORD  Password for authenticated sessions (optional).

Each buffer triggers a synchronous write of a JSON string (see format below)
to the configured OPC-UA node.  The write is handled in a background worker
thread so the GStreamer streaming thread is not blocked.

Message format
--------------
JSON string written to the OPC-UA variable::

    {
        "regions": [...],   // GVA detection regions
        "messages": [...]   // GVA messages attached to the buffer
    }
"""
from __future__ import annotations

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

from gstgva import VideoFrame  # noqa: E402
from asyncua.sync import Client, ua  # noqa: E402

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
    result: dict = {"regions": [], "messages": []}
    if caps is None:
        return result
    try:
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


class OpcuaSinkPy(GstBase.BaseSink):
    """GStreamer sink that writes GVA metadata as JSON to an OPC-UA node."""

    __gstmetadata__ = (
        "OpcuaSinkPy",
        "Sink",
        "Writes GVA metadata as a JSON string to an OPC-UA node variable",
        "Intel",
    )
    __gsttemplates__ = Gst.PadTemplate.new(
        "sink",
        Gst.PadDirection.SINK,
        Gst.PadPresence.ALWAYS,
        Gst.Caps.new_any(),
    )
    __gproperties__ = {
        "variable": (
            GObject.TYPE_STRING,
            "OPC-UA node ID",
            "Node variable to write metadata to (e.g. ns=2;s=MyVar)",
            "ns=2;s=0",
            GObject.ParamFlags.READWRITE,
        ),
    }

    def __init__(self):
        super().__init__()
        self._variable: str = "ns=2;s=0"
        self._queue: deque = deque(maxlen=1000)
        self._stop: threading.Event = threading.Event()
        self._thread: threading.Thread | None = None
        self._client = None  # asyncua.sync.Client

    # ------------------------------------------------------------------
    # GObject property accessors
    # ------------------------------------------------------------------

    def do_get_property(self, prop):
        if prop.name == "variable":
            return self._variable
        raise AttributeError(f"Unknown property: {prop.name}")

    def do_set_property(self, prop, value):
        if prop.name == "variable":
            self._variable = value
        else:
            raise AttributeError(f"Unknown property: {prop.name}")

    # ------------------------------------------------------------------
    # GstBaseSink lifecycle
    # ------------------------------------------------------------------

    def do_start(self) -> bool:
        server_ip = os.environ.get("OPCUA_SERVER_IP", "")
        server_port = os.environ.get("OPCUA_SERVER_PORT", "4840")
        username = os.environ.get("OPCUA_SERVER_USERNAME", "")
        password = os.environ.get("OPCUA_SERVER_PASSWORD", "")

        if not server_ip:
            logger.error("OPCUA_SERVER_IP is not set — opcuasinkpy will drop all frames")
        else:
            try:
                url = f"opc.tcp://{server_ip}:{server_port}"
                self._client = Client(url=url)
                if username:
                    self._client.set_user(username)
                    self._client.set_password(password)
                self._client.connect()
                logger.info("opcuasinkpy connected to %s", url)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("OPC-UA connect failed: %s", exc)
                self._client = None

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="opcuasinkpy-worker"
        )
        self._thread.start()
        return True

    def do_stop(self) -> bool:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        if self._client:
            try:
                self._client.disconnect()
            except Exception:  # pylint: disable=broad-except
                pass
            self._client = None
        return True

    def do_render(self, buf: Gst.Buffer) -> Gst.FlowReturn:
        caps = self.get_static_pad("sink").get_current_caps()
        meta = _extract_gva_meta(buf, caps)
        self._queue.append(meta)
        return Gst.FlowReturn.OK

    # ------------------------------------------------------------------
    # Worker thread
    # ------------------------------------------------------------------

    def _worker(self) -> None:
        logger.info("opcuasinkpy worker started (variable=%s)", self._variable)
        while not self._stop.is_set():
            try:
                meta = self._queue.popleft()
                self._publish(meta)
            except IndexError:
                time.sleep(0.005)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("opcuasinkpy publish error: %s", exc)

    def _publish(self, meta: dict) -> None:
        if self._client is None:
            return
        try:
            node = self._client.get_node(self._variable)
            node.set_value(
                ua.DataValue(ua.Variant(json.dumps(meta), ua.VariantType.String))
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("OPC-UA write failed: %s", exc)


# ------------------------------------------------------------------
# GStreamer plugin registration  (runs at import time, after Gst.init())
# ------------------------------------------------------------------


def plugin_init(plugin) -> bool:
    GObject.type_register(OpcuaSinkPy)
    return Gst.Element.register(plugin, "opcuasinkpy", Gst.Rank.NONE, OpcuaSinkPy)


Gst.Plugin.register_static(
    1,
    0,
    "opcuasinkpyplugin",
    "OPC-UA metadata publisher sink",
    plugin_init,
    "1.0",
    "Apache-2.0",
    "dlsps2",
    "dlsps2",
    "",
)
