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

      The chain added is::

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

      The chain added is::

          videoconvert ! [gvawatermark !] openh264enc name=h264enc \
              bitrate=<bitrate> ! video/x-h264,profile=baseline ! \
              whipclientsink name=webrtc_sink \
              signaller::whip-endpoint=<WEBRTC_SIGNALING_SERVER>/<peer-id>/whip

      A WHIP-compatible signaling/relay server (e.g. MediaMTX) must be
      reachable at that address.  View the stream at
      ``<WEBRTC_SIGNALING_SERVER>/<peer-id>``.

  ``destination.frame`` may be a single object, or a list of objects to
  request more than one frame destination at once (e.g. a WebRTC preview
  *and* an S3 archive of the same stream).

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

Fanning out to multiple destinations
-------------------------------------
``mqtt``/``opcua``/``influx_write`` metadata destinations and
``rtsp``/``webrtc``/``s3_write`` frame destinations are all, ultimately,
terminal GStreamer sink elements that replace the single ``appsink`` in the
pipeline template — they cannot simply be chained with ``!``. When more than
one such destination is requested in the same call (e.g. an MQTT metadata
destination *and* a WebRTC frame destination, or two frame destinations in a
``destination.frame`` list), :func:`apply_destination` replaces ``appsink``
with a ``tee`` instead, giving each requested sink its own ``queue``-buffered
branch so a slow/stalled destination cannot block the others or the shared
upstream pipeline::

    ... ! tee name=dest_tee ! queue ! <sink 1>
    dest_tee. ! queue ! <sink 2>
    dest_tee. ! queue ! <sink 3>

When only one such destination is requested, ``appsink`` is still replaced
in-place with no ``tee`` involved, exactly as before.

``file``/``kafka`` metadata destinations inject properties into the existing
``gvametapublish name=destination`` element instead, and are therefore
completely independent of the ``appsink``/``tee`` fan-out above — they can be
freely combined with any frame/Python-element metadata destination.
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


def _rtsp_chain(path: str) -> str:
    """Build the encode + rtspclientsink chain for an RTSP frame destination."""
    mount = path.lstrip("/")
    rtsp_url = f"rtsp://{_RTSP_HOST}:{_RTSP_PORT}/{mount}"
    return (
        f"videoconvert ! openh264enc ! "
        f"h264parse ! "
        f"rtspclientsink name=rtsp_sink location={rtsp_url}"
    )


def _webrtc_chain(peer_id: str, *, overlay: bool = True, bitrate: int = 2048) -> str:
    """Build the encode + whipclientsink chain for a WebRTC frame destination.

    ``gvawatermark`` is included only when ``overlay`` is true.  A
    WHIP-compatible signaling/relay server (e.g. MediaMTX) must be reachable at
    the resulting endpoint.
    """
    mount = peer_id.strip("/")
    whip_url = f"{_WEBRTC_SIGNALING_SERVER}/{mount}/whip"
    overlay_element = "gvawatermark ! " if overlay else ""
    return (
        f"videoconvert ! {overlay_element}"
        f"openh264enc complexity=low name=h264enc ! "
        f"video/x-h264,profile=baseline ! "
        f"whipclientsink name=webrtc_sink signaller::whip-endpoint={whip_url}"
    )


def _replace_appsink_with_chains(pipeline: str, chains: list[str]) -> str:
    """Replace the pipeline's single ``appsink`` with one or more sink chains.

    - Zero chains: no-op, pipeline is returned unchanged.
    - One chain: ``appsink`` is replaced in-place, exactly as in the
      single-destination implementation this replaces -- no ``tee`` is
      introduced, so single-destination pipelines are unaffected.
    - Two or more chains: ``appsink`` is replaced with a ``tee`` and each
      chain is attached to its own ``queue``-buffered branch, e.g.::

          tee name=dest_tee ! queue ! <chains[0]>
          dest_tee. ! queue ! <chains[1]>
          dest_tee. ! queue ! <chains[2]>

      The per-branch ``queue`` means a slow or stalled destination applies
      backpressure only to its own branch, not to the other destinations or
      the shared upstream pipeline.

    If no ``appsink`` element is found in the pipeline, the original string is
    returned unchanged and a warning is logged.
    """
    if not chains:
        return pipeline

    if len(chains) == 1:
        replacement = chains[0]
    else:
        tee_name = "dest_tee"
        branches = [f"tee name={tee_name} ! queue ! {chains[0]}"]
        branches.extend(f"{tee_name}. ! queue ! {chain}" for chain in chains[1:])
        replacement = " ".join(branches)

    replaced, n = _APPSINK_RE.subn(replacement, pipeline, count=1)
    if n == 0:
        logger.warning(
            "No 'appsink' found in pipeline — cannot add %d destination(s).",
            len(chains),
        )
        return pipeline

    if len(chains) == 1:
        logger.debug("Replaced appsink with: %s", chains[0])
    else:
        logger.info(
            "Replaced appsink with a %d-way tee fan-out (%s)",
            len(chains),
            ", ".join(chain.split()[0] for chain in chains),
        )
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


def _as_list(value):
    """Normalize a value that may be ``None``, a single item, or a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def apply_destination(pipeline: str, destination: DestinationConfig | None) -> str:
    """Configure destination elements already present in the pipeline template.

    ``file``/``kafka`` metadata destinations inject properties directly into
    the ``gvametapublish name=destination`` element already present in the
    pipeline template.

    Every other destination type (``mqtt``/``opcua``/``influx_write``
    metadata, and ``rtsp``/``webrtc``/``s3_write`` frame — one or more, via
    ``destination.frame`` being a single object or a list) is a terminal sink
    element that replaces the pipeline's ``appsink``. These are collected
    first and applied together via :func:`_replace_appsink_with_chains`: a
    single requested sink replaces ``appsink`` in-place as before, and two or
    more are fanned out through a ``tee`` so, for example, an MQTT metadata
    destination and a WebRTC frame preview can both run concurrently from the
    same pipeline.

    Args:
        pipeline:    GStreamer pipeline description string.
        destination: Destination configuration from the request body.

    Returns:
        Pipeline string with destination element properties/sinks injected.
    """
    if destination is None:
        return pipeline

    sink_chains: list[str] = []

    # ------------------------------------------------------------------
    # Metadata destination
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
            sink_chains.append(f"mqttsinkpy topic={topic} publish-frame={publish_frame} qos=0")

        elif dest_type == "kafka":
            kafka_address = meta.topic
            pipeline = _inject_element_property(pipeline, _METAPUBLISH_ELEMENT, "method", "kafka")
            if kafka_address:
                pipeline = _inject_element_property(pipeline, _METAPUBLISH_ELEMENT, "kafka-address", kafka_address)

        elif dest_type == "opcua":
            # OPC-UA node variable; connection from OPCUA_SERVER_* env vars.
            variable = meta.path or "ns=2;s=0"
            sink_chains.append(f"opcuasinkpy variable={variable}")

        elif dest_type in ("influx_write", "influxdb"):
            # InfluxDB bucket from meta.path, measurement from meta.format.
            bucket = meta.path or ""
            measurement = meta.format or "dlstreamer_metadata"
            if not bucket:
                logger.warning(
                    "influx_write destination: no bucket specified (set destination.path)"
                )
            sink_chains.append(f"influxsinkpy bucket={bucket} measurement={measurement}")

        else:
            logger.warning("Unsupported metadata destination type %r — skipping", dest_type)

    # ------------------------------------------------------------------
    # Frame destination(s) — destination.frame may be a single object or a list
    # ------------------------------------------------------------------
    for frame in _as_list(destination.frame):
        frame_type = (frame.type or "").lower()

        if frame_type == "rtsp":
            sink_chains.append(_rtsp_chain(frame.path or "stream"))

        elif frame_type == "webrtc":
            peer_id = frame.peer_id or frame.path or "dlstreamer"
            sink_chains.append(_webrtc_chain(peer_id, overlay=frame.overlay, bitrate=frame.bitrate))

        elif frame_type in ("s3_write", "s3"):
            # S3 bucket from frame.path; connection from S3_STORAGE_* env vars.
            bucket = frame.path or ""
            if not bucket:
                logger.warning(
                    "s3_write destination: no bucket specified (set destination.frame.path)"
                )
            sink_chains.append(f"s3sinkpy bucket={bucket}")

        else:
            logger.warning("Unsupported frame destination type %r — skipping", frame_type)

    return _replace_appsink_with_chains(pipeline, sink_chains)
