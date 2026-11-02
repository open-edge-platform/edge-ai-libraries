# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Python GStreamer publisher sink elements for DLSPS 2.0.

Each sub-module registers a GStreamer element via
``Gst.Plugin.register_static()`` when imported.  Registration must happen
**after** ``Gst.init()`` has been called, which is why imports are deferred
inside ``register_all()``.

Elements are discovered automatically: ``register_all()`` scans this
directory for Python modules and imports each one.  There is no manual
registration list to maintain — dropping a new ``*_sink.py`` module in this
package (with its own ``Gst.Plugin.register_static()`` call at import time)
is enough for it to be picked up.  Modules whose name starts with ``_`` are
skipped (treated as private helpers, not elements).

Elements currently provided
----------------------------
mqttsinkpy    - Publishes GVA metadata (and optional raw frames) to MQTT.
opcuasinkpy   - Writes GVA metadata JSON to an OPC-UA node variable.
influxsinkpy  - Writes GVA metadata fields as InfluxDB data points.
s3sinkpy      - Encodes frames as JPEG and uploads them to S3 / MinIO.
"""

import importlib
import logging
import pkgutil

logger = logging.getLogger(__name__)


def register_all() -> None:
    """Discover and import every module in this package to register its
    GStreamer publisher sink element(s).

    Must be called after ``Gst.init()`` has been invoked.  Missing optional
    dependencies (e.g. ``paho-mqtt``) cause a warning rather than a hard
    failure so that pipelines without those destinations continue to work.
    """
    for module_info in pkgutil.iter_modules(__path__):
        name = module_info.name
        if name.startswith("_"):
            continue
        try:
            importlib.import_module(f".{name}", package=__name__)
            logger.debug("Registered GStreamer publisher element(s) from: %s", name)
        except ImportError as exc:
            logger.warning("Skipping %s — missing dependency: %s", name, exc)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to register elements from %s: %s", name, exc)
