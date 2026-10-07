# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""WARNING: Legacy feature, may be removed in future releases.  Use with caution.
S3 / MinIO publisher GStreamer BaseSink element.

Encodes each incoming video frame as JPEG and uploads it to an S3-compatible
object store (MinIO, AWS S3, etc.) using the ``boto3`` library.

GStreamer element name: ``s3sinkpy``

Properties
----------
bucket (str)         S3 bucket to upload frames to.  Default: ``""``.
folder-prefix (str)  Key prefix (folder path) for uploaded objects.
                     Default: ``frames``.

Environment variables
---------------------
S3_STORAGE_HOST  Server hostname or IP address.  Default: ``localhost``.
S3_STORAGE_PORT  Server port.  Default: ``9000``.
S3_STORAGE_USER  Access key / username (required).
S3_STORAGE_PASS  Secret key / password (required).

Upload behaviour
----------------
Each buffer is JPEG-encoded using OpenCV (BGR / BGRA / RGB formats are
handled; unknown formats are uploaded as raw bytes).  The object key is::

    <folder-prefix>/<uuid>.jpg

A warning is logged and the frame is dropped if the S3 client is not
connected or if the bucket name is not configured.
"""
from __future__ import annotations

import io
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

import boto3  # noqa: E402
import cv2  # noqa: E402
import numpy as np  # noqa: E402

logger = logging.getLogger(__name__)

# Number of bytes per pixel / channels for common GStreamer raw video formats.
_FORMAT_CHANNELS: dict[str, int] = {
    "BGR": 3,
    "RGB": 3,
    "GRAY8": 1,
    "BGRA": 4,
    "RGBA": 4,
    "BGRx": 4,
    "RGBx": 4,
}


def _encode_frame(
    frame_bytes: bytes, width: int, height: int, fmt: str
) -> bytes:
    """Return JPEG-encoded bytes for the given raw video frame.

    Falls back to returning the raw bytes unchanged for unsupported formats
    or when OpenCV is not available.
    """
    if not width or not height:
        return frame_bytes

    channels = _FORMAT_CHANNELS.get(fmt, 0)
    if channels == 0:
        logger.debug("s3sinkpy: unsupported format %r — uploading raw bytes", fmt)
        return frame_bytes

    try:
        arr = np.frombuffer(frame_bytes, dtype=np.uint8)
        arr = arr.reshape(height, width, channels)

        # Normalise to BGR for cv2.imencode
        if fmt in ("RGB",):
            arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        elif fmt in ("RGBA", "RGBx"):
            arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
        elif fmt in ("BGRA", "BGRx"):
            arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
        elif fmt == "GRAY8":
            arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)

        success, encoded = cv2.imencode(".jpg", arr)
        if not success:
            logger.warning("s3sinkpy: cv2.imencode failed — uploading raw bytes")
            return frame_bytes
        return encoded.tobytes()
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("s3sinkpy: JPEG encode error (%s) — uploading raw bytes", exc)
        return frame_bytes


class S3SinkPy(GstBase.BaseSink):
    """GStreamer sink that JPEG-encodes frames and uploads them to S3."""

    __gstmetadata__ = (
        "S3SinkPy",
        "Sink",
        "Encodes video frames as JPEG and uploads them to an S3-compatible store",
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
            "S3 bucket",
            "Bucket name to upload JPEG frames to",
            "",
            GObject.ParamFlags.READWRITE,
        ),
        "folder-prefix": (
            GObject.TYPE_STRING,
            "Folder prefix",
            "Key prefix (folder path) used when naming uploaded objects",
            "frames",
            GObject.ParamFlags.READWRITE,
        ),
    }

    def __init__(self):
        super().__init__()
        self._bucket: str = ""
        self._folder_prefix: str = "frames"
        self._queue: deque = deque(maxlen=500)
        self._stop: threading.Event = threading.Event()
        self._thread: threading.Thread | None = None
        self._s3 = None  # boto3 S3 client

    # ------------------------------------------------------------------
    # GObject property accessors
    # ------------------------------------------------------------------

    def do_get_property(self, prop):
        if prop.name == "bucket":
            return self._bucket
        if prop.name == "folder-prefix":
            return self._folder_prefix
        raise AttributeError(f"Unknown property: {prop.name}")

    def do_set_property(self, prop, value):
        if prop.name == "bucket":
            self._bucket = value
        elif prop.name == "folder-prefix":
            self._folder_prefix = value
        else:
            raise AttributeError(f"Unknown property: {prop.name}")

    # ------------------------------------------------------------------
    # GstBaseSink lifecycle
    # ------------------------------------------------------------------

    def do_start(self) -> bool:
        host = os.environ.get("S3_STORAGE_HOST", "localhost")
        port = os.environ.get("S3_STORAGE_PORT", "9000")
        user = os.environ.get("S3_STORAGE_USER", "")
        password = os.environ.get("S3_STORAGE_PASS", "")

        if not user or not password:
            logger.error(
                "S3_STORAGE_USER / S3_STORAGE_PASS not set — s3sinkpy will drop all frames"
            )
        else:
            try:
                self._s3 = boto3.client(
                    "s3",
                    endpoint_url=f"http://{host}:{port}",
                    aws_access_key_id=user,
                    aws_secret_access_key=password,
                )
                logger.info("s3sinkpy connected to %s:%s", host, port)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("S3 client init failed: %s", exc)
                self._s3 = None

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="s3sinkpy-worker"
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

        width, height, fmt = 0, 0, ""
        if caps is not None:
            try:
                s = caps.get_structure(0)
                width = s.get_value("width") or 0
                height = s.get_value("height") or 0
                fmt = s.get_value("format") or ""
            except Exception:  # pylint: disable=broad-except
                pass

        try:
            frame_bytes = buf.extract_dup(0, buf.get_size())
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("Frame extraction failed: %s", exc)
            return Gst.FlowReturn.OK

        self._queue.append((frame_bytes, width, height, fmt))
        return Gst.FlowReturn.OK

    # ------------------------------------------------------------------
    # Worker thread
    # ------------------------------------------------------------------

    def _worker(self) -> None:
        logger.info(
            "s3sinkpy worker started (bucket=%s, prefix=%s)",
            self._bucket,
            self._folder_prefix,
        )
        while not self._stop.is_set():
            try:
                item = self._queue.popleft()
                self._upload(*item)
            except IndexError:
                time.sleep(0.005)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("s3sinkpy upload error: %s", exc)

    def _upload(
        self, frame_bytes: bytes, width: int, height: int, fmt: str
    ) -> None:
        if self._s3 is None or not self._bucket:
            return

        jpeg_bytes = _encode_frame(frame_bytes, width, height, fmt)
        prefix = self._folder_prefix.rstrip("/")
        key = f"{prefix}/{uuid.uuid4()}.jpg"

        try:
            resp = self._s3.put_object(
                Bucket=self._bucket, Key=key, Body=jpeg_bytes
            )
            status = resp.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
            if status != 200:
                logger.warning(
                    "s3sinkpy: unexpected HTTP status %d for key %s", status, key
                )
            else:
                logger.debug("s3sinkpy: uploaded s3://%s/%s", self._bucket, key)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("s3sinkpy: put_object failed for key %s: %s", key, exc)


# ------------------------------------------------------------------
# GStreamer plugin registration  (runs at import time, after Gst.init())
# ------------------------------------------------------------------


def plugin_init(plugin) -> bool:
    GObject.type_register(S3SinkPy)
    return Gst.Element.register(plugin, "s3sinkpy", Gst.Rank.NONE, S3SinkPy)


Gst.Plugin.register_static(
    1,
    0,
    "s3sinkpyplugin",
    "S3/MinIO JPEG frame upload sink",
    plugin_init,
    "1.0",
    "Apache-2.0",
    "dlsps2",
    "dlsps2",
    "",
)
