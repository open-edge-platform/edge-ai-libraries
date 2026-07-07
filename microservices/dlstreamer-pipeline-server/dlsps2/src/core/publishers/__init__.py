# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Python GStreamer publisher sink elements for DLSPS 2.0.

Each sub-module registers a GStreamer element via
``Gst.Plugin.register_static()`` when imported.  Registration must happen
**after** ``Gst.init()`` has been called, which is why imports are deferred
inside ``register_all()``.

Elements registered
-------------------
mqttsinkpy    – Publishes GVA metadata (and optional raw frames) to MQTT.
opcuasinkpy   – Writes GVA metadata JSON to an OPC-UA node variable.
influxsinkpy  – Writes GVA metadata fields as InfluxDB data points.
s3sinkpy      – Encodes frames as JPEG and uploads them to S3 / MinIO.
"""

import importlib
import logging

logger = logging.getLogger(__name__)

_PUBLISHERS = [
    ("mqttsinkpy", ".mqtt_sink"),
    ("opcuasinkpy", ".opcua_sink"),
    ("influxsinkpy", ".influx_sink"),
    ("s3sinkpy", ".s3_sink"),
]


def register_all() -> None:
    """Import and register all publisher sink GStreamer elements.

    Must be called after ``Gst.init()`` has been invoked.  Missing optional
    dependencies (e.g. ``paho-mqtt``) cause a warning rather than a hard
    failure so that pipelines without those destinations continue to work.
    """
    for element_name, module_suffix in _PUBLISHERS:
        try:
            importlib.import_module(module_suffix, package=__name__)
            logger.debug("Registered GStreamer publisher element: %s", element_name)
        except ImportError as exc:
            logger.warning(
                "Skipping %s — missing dependency: %s", element_name, exc
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to register %s: %s", element_name, exc)
