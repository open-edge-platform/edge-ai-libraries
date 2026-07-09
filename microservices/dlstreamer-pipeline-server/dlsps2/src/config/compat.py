# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Compatibility layer that translates the legacy DL Streamer Pipeline Server
request body (source / destination / parameters) into a concrete GStreamer
pipeline string.

Supported translations
----------------------
Source
  ``type=uri``
      Replaces the ``{auto_source}`` placeholder in the pipeline template with
      ``urisourcebin uri=<uri>``.  Works for ``file://``, ``rtsp://``,
      ``http://`` and any other URI scheme supported by GStreamer.

Destination - metadata
  ``type=file``
      Injects ``method=file file-path=<path> [file-format=<format>]`` into the
      ``gvametapublish name=destination`` element already present in the
      pipeline template.
  ``type=mqtt``
      Injects ``method=mqtt mqtt-address=<topic>``.
  ``type=kafka``
      Injects ``method=kafka kafka-address=<topic-or-path>``.

Destination - frame
  ``type=rtsp``
      Replaces ``appsink name=appsink`` in the pipeline template with an
      encode + ``rtspclientsink`` chain that pushes to an RTSP server at
      ``rtsp://<RTSP_HOST>:<RTSP_PORT>/<path>``.  The RTSP server host and
      port are read from the ``RTSP_HOST`` (default ``localhost``) and
      ``RTSP_PORT`` (default ``8554``) environment variables.

      The replacement sink chain added is::

          videoconvert ! openh264enc ! rtph264pay pt=96 \
              config-interval=1 ! rtspclientsink name=rtsp_sink \
              location=rtsp://<host>:<port>/<path>

      A compatible RTSP server (e.g. MediaMTX) must be reachable at that
      address to accept the push stream.
  ``type=webrtc``
      Replaces ``appsink name=appsink`` in the pipeline template with an
      encode + ``whipclientsink`` chain that publishes to a WHIP signaling
      server at ``<WEBRTC_SIGNALING_SERVER>/<peer-id>/whip``.  The signaling
      server base URL is read from the ``WEBRTC_SIGNALING_SERVER`` environment
      variable (default ``http://mediamtx-server:8889``), matching the legacy
      DLSPS ``server/arguments.py`` convention.

      The replacement sink chain added is::

          videoconvert ! [gvawatermark !] openh264enc name=h264enc \
              bitrate=<bitrate> ! video/x-h264,profile=baseline ! \
              whipclientsink name=webrtc_sink \
              signaller::whip-endpoint=<WEBRTC_SIGNALING_SERVER>/<peer-id>/whip

      A WHIP-compatible signaling/relay server (e.g. MediaMTX) must be
      reachable at that address.  View the stream at
      ``<WEBRTC_SIGNALING_SERVER>/<peer-id>``.

Destination - metadata (Python elements)
  ``type=mqtt``
      Replaces ``appsink name=appsink`` with ``mqttsinkpy topic=<topic>``.
      ``topic`` is the MQTT topic . The MQTT broker is read from
      ``MQTT_HOST`` / ``MQTT_PORT`` env vars. Frames are included in the MQTT message when
      ``publish_frame`` is true.
  ``type=opcua``
      Replaces ``appsink name=appsink`` with ``opcuasinkpy variable=<path>``.
      OPC-UA connection details come from ``OPCUA_SERVER_*`` env vars.
  ``type=influx_write``
      Replaces ``appsink name=appsink`` with
      ``influxsinkpy bucket=<path> measurement=<format>``.
      InfluxDB connection details come from ``INFLUXDB_*`` env vars.

Destination - frame (Python elements)
  ``type=s3_write``
      Replaces ``appsink name=appsink`` with
      ``s3sinkpy bucket=<path>``.
      S3 connection details come from ``S3_STORAGE_*`` env vars.
"""

from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING

from config.converter import _inject_element_property

if TYPE_CHECKING:
    from api.schema import DestinationConfig, SourceConfig

logger = logging.getLogger(__name__)

# Name of the gvametapublish element used in DLSPS pipeline templates.
_METAPUBLISH_ELEMENT = "destination"

# Matches the appsink element block including any trailing properties,
# e.g. "appsink name=appsink" or "appsink name=appsink sync=false".
_APPSINK_RE = re.compile(r"appsink\b[^!]*", re.IGNORECASE)

# RTSP server coordinates — override via environment variables.
_RTSP_HOST = os.environ.get("RTSP_HOST", "localhost")
_RTSP_PORT = os.environ.get("RTSP_PORT", "8554")

_WEBRTC_SIGNALING_SERVER = os.environ.get("WEBRTC_SIGNALING_SERVER", "http://mediamtx-server:8889").rstrip("/")


def _replace_appsink_with_rtsp(pipeline: str, path: str) -> str:
    """Replace ``appsink`` with an encode + rtspclientsink chain.

    The replacement chain is::

        videoconvert ! openh264enc ! rtph264pay pt=96 \
            config-interval=1 ! rtspclientsink name=rtsp_sink \
            location=rtsp://<RTSP_HOST>:<RTSP_PORT>/<path>

    If no ``appsink`` element is found the original string is returned
    unchanged and a warning is logged.
    """
    mount = path.lstrip("/")
    rtsp_url = f"rtsp://{_RTSP_HOST}:{_RTSP_PORT}/{mount}"
    rtsp_chain = (
        f"videoconvert ! openh264enc ! "
        f"h264parse ! "
        f"rtspclientsink name=rtsp_sink location={rtsp_url}"
    )
    replaced, n = _APPSINK_RE.subn(rtsp_chain, pipeline, count=1)
    if n == 0:
        logger.warning(
            "RTSP frame destination requested but no 'appsink' element found "
            "in pipeline — RTSP sink not added."
        )
        return pipeline
    logger.debug("Replaced appsink with rtspclientsink at %s", rtsp_url)
    return replaced


def _replace_appsink_with_webrtc(
    pipeline: str,
    peer_id: str,
    *,
    overlay: bool = True,
    bitrate: int = 2048,
) -> str:
    """Replace ``appsink`` with an encode + whipclientsink chain.

    The replacement chain is::

        videoconvert ! [gvawatermark !] openh264enc name=h264enc \
            bitrate=<bitrate> ! video/x-h264,profile=baseline ! \
            whipclientsink name=webrtc_sink \
            signaller::whip-endpoint=<WEBRTC_SIGNALING_SERVER>/<peer_id>/whip

    ``gvawatermark`` is included only when ``overlay`` is true.  A
    WHIP-compatible signaling/relay server (e.g. MediaMTX) must be reachable at
    the endpoint.  If no ``appsink`` element is found the original string is
    returned unchanged and a warning is logged.
    """
    mount = peer_id.strip("/")
    whip_url = f"{_WEBRTC_SIGNALING_SERVER}/{mount}/whip"
    overlay_element = "gvawatermark ! " if overlay else ""
    webrtc_chain = (
        f"videoconvert ! {overlay_element}"
        f"openh264enc name=h264enc bitrate={bitrate} ! "
        f"video/x-h264,profile=baseline ! "
        f"whipclientsink name=webrtc_sink signaller::whip-endpoint={whip_url}"
    )
    replaced, n = _APPSINK_RE.subn(webrtc_chain, pipeline, count=1)
    if n == 0:
        logger.warning(
            "WebRTC frame destination requested but no 'appsink' element found "
            "in pipeline — WebRTC sink not added."
        )
        return pipeline
    logger.debug("Replaced appsink with whipclientsink at %s", whip_url)
    return replaced


def _replace_appsink_with_py_sink(pipeline: str, element_str: str) -> str:
    """Replace ``appsink`` with a custom Python GStreamer sink element string.

    If no ``appsink`` element is found the original string is returned
    unchanged and a warning is logged.
    """
    sink_name = element_str.split()[0] if element_str else "(unknown)"
    replaced, n = _APPSINK_RE.subn(element_str, pipeline, count=1)
    if n == 0:
        logger.warning(
            "No 'appsink' found in pipeline — cannot add %s sink.", sink_name
        )
    else:
        logger.debug("Replaced appsink with: %s", element_str)
    return replaced


def apply_source(pipeline: str, source: SourceConfig | None) -> str:
    """Replace the ``{auto_source}`` placeholder with the appropriate GStreamer source.

    If the pipeline template does not contain ``{auto_source}`` this function
    is a no-op and returns the pipeline unchanged.

    Args:
        pipeline: GStreamer pipeline description string (may contain
                  ``{auto_source}``).
        source:   Source configuration from the request body.

    Returns:
        Pipeline string with ``{auto_source}`` substituted.

    Raises:
        ValueError: If the template requires a source but none was provided, or
                    the requested source type is not supported.
    """
    if "{auto_source}" not in pipeline:
        return pipeline

    if source is None:
        raise ValueError(
            "Pipeline template contains {auto_source} but no source was provided in the request."
        )

    src_type = (source.type or "uri").lower()

    if src_type == "uri":
        if not source.uri:
            raise ValueError("source.type='uri' requires source.uri to be set.")
        src_element = f"urisourcebin uri={source.uri}"
    else:
        raise ValueError(
            f"Unsupported source type {src_type!r}. "
            "Currently supported: 'uri'."
        )

    logger.debug("Substituting {auto_source} with: %s", src_element)
    return pipeline.replace("{auto_source}", src_element)


def apply_destination(pipeline: str, destination: DestinationConfig | None) -> str:
    """Configure destination elements already present in the pipeline template.

    Injects properties into ``gvametapublish name=destination`` for metadata
    destinations and into ``rtspclientsink name=rtsp_sink`` for RTSP frame
    destinations.

    Args:
        pipeline:    GStreamer pipeline description string.
        destination: Destination configuration from the request body.

    Returns:
        Pipeline string with destination element properties injected.
    """
    if destination is None:
        return pipeline

    # ------------------------------------------------------------------
    # Metadata destination → gvametapublish name=destination
    # ------------------------------------------------------------------
    if destination.metadata is not None:
        meta = destination.metadata
        dest_type = (meta.type or "").lower()

        if dest_type == "file":
            pipeline = _inject_element_property(pipeline, _METAPUBLISH_ELEMENT, "method", "file")
            if meta.path:
                pipeline = _inject_element_property(pipeline, _METAPUBLISH_ELEMENT, "file-path", meta.path)
            fmt = meta.format or "json-lines"
            pipeline = _inject_element_property(pipeline, _METAPUBLISH_ELEMENT, "file-format", fmt)

        elif dest_type == "mqtt":
            # Use Python mqttsinkpy element so frames can be included.
            # meta.topic is the MQTT topic.
            # Broker comes from env vars.
            topic = meta.topic or "dlstreamer_pipeline_results"
            publish_frame = "true" if meta.publish_frame else "false"
            pipeline = _replace_appsink_with_py_sink(
                pipeline, f"mqttsinkpy topic={topic} publish-frame={publish_frame} qos=0"
            )

        elif dest_type == "kafka":
            kafka_address = meta.topic
            pipeline = _inject_element_property(pipeline, _METAPUBLISH_ELEMENT, "method", "kafka")
            if kafka_address:
                pipeline = _inject_element_property(pipeline, _METAPUBLISH_ELEMENT, "kafka-address", kafka_address)

        elif dest_type == "opcua":
            # OPC-UA node variable; connection from OPCUA_SERVER_* env vars.
            variable = meta.path or "ns=2;s=0"
            pipeline = _replace_appsink_with_py_sink(
                pipeline, f"opcuasinkpy variable={variable}"
            )

        elif dest_type in ("influx_write", "influxdb"):
            # InfluxDB bucket from meta.path, measurement from meta.format.
            bucket = meta.path or ""
            measurement = meta.format or "dlstreamer_metadata"
            element = f"influxsinkpy bucket={bucket} measurement={measurement}"
            if not bucket:
                logger.warning(
                    "influx_write destination: no bucket specified (set destination.path)"
                )
            pipeline = _replace_appsink_with_py_sink(pipeline, element)

        else:
            logger.warning("Unsupported metadata destination type %r — skipping", dest_type)

    # ------------------------------------------------------------------
    # Frame destination → rtspclientsink name=rtsp_sink
    # ------------------------------------------------------------------
    if destination.frame is not None:
        frame = destination.frame
        frame_type = (frame.type or "").lower()

        if frame_type == "rtsp":
            path = frame.path or "stream"
            pipeline = _replace_appsink_with_rtsp(pipeline, path)

        elif frame_type == "webrtc":
            peer_id = frame.peer_id or frame.path or "dlstreamer"
            pipeline = _replace_appsink_with_webrtc(
                pipeline,
                peer_id,
                overlay=frame.overlay,
                bitrate=frame.bitrate,
            )

        elif frame_type in ("s3_write", "s3"):
            # S3 bucket from frame.path; connection from S3_STORAGE_* env vars.
            bucket = frame.path or ""
            element = f"s3sinkpy bucket={bucket}"
            if not bucket:
                logger.warning(
                    "s3_write destination: no bucket specified (set destination.frame.path)"
                )
            pipeline = _replace_appsink_with_py_sink(pipeline, element)

        else:
            logger.warning("Unsupported frame destination type %r — skipping", frame_type)

    return pipeline
