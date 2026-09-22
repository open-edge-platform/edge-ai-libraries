# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""DL Streamer Pipeline Server client — manages pipeline lifecycle."""

import logging
import os
import threading
import time

import requests

log = logging.getLogger(__name__)

_DLSTREAMER_URL      = os.environ.get("DLSTREAMER_URL", "http://dlstreamer-pipeline-server:8554")
_PIPELINE_NAME       = os.environ.get("DLSTREAMER_PIPELINE_NAME", "pipeline_defect_detection")
_PIPELINE_GROUP      = os.environ.get("DLSTREAMER_PIPELINE_GROUP", "user_defined_pipelines")
_MQTT_TOPIC          = os.environ.get("MQTT_TOPIC", "apm/detections")
_WATCHDOG_INTERVAL = int(os.environ.get("DLSTREAMER_WATCHDOG_INTERVAL", "15"))
_TIMEOUT = 5

_PIPELINE_START_PAYLOAD = {
    "destination": {
        "metadata": {
            "type": "mqtt",
            "topic": _MQTT_TOPIC,
        }
    }
}


_NO_PROXY_HOSTS = {"no_proxy": "dlstreamer-pipeline-server,localhost,127.0.0.1"}


def _is_pipeline_running() -> bool:
    """Return True if at least one instance of the configured pipeline is RUNNING."""
    try:
        r = requests.get(f"{_DLSTREAMER_URL}/pipelines/status", timeout=_TIMEOUT, proxies=_NO_PROXY_HOSTS)
        if r.status_code == 200:
            return any(
                p.get("state") == "RUNNING"
                for p in r.json()
            )
    except Exception:
        pass
    return False


def _start_pipeline() -> bool:
    """Start the default pipeline with MQTT destination. Returns True on success."""
    try:
        r = requests.post(
            f"{_DLSTREAMER_URL}/pipelines/{_PIPELINE_GROUP}/{_PIPELINE_NAME}",
            json=_PIPELINE_START_PAYLOAD,
            timeout=_TIMEOUT,
            proxies=_NO_PROXY_HOSTS,
        )
        if r.status_code in (200, 201):
            log.info("DL Streamer pipeline '%s' started (instance: %s)", _PIPELINE_NAME, r.text.strip())
            return True
        log.warning("Failed to start pipeline '%s': %s %s", _PIPELINE_NAME, r.status_code, r.text)
    except Exception as exc:
        log.warning("Could not reach DL Streamer Pipeline Server: %s", exc)
    return False


def _watchdog_loop():
    """Background thread: ensures the DL Streamer pipeline is always running."""
    # Initial delay — wait for DL Streamer to be ready
    time.sleep(10)
    log.info("DL Streamer watchdog started (pipeline=%s, interval=%ds)", _PIPELINE_NAME, _WATCHDOG_INTERVAL)
    while True:
        try:
            if not _is_pipeline_running():
                log.info("DL Streamer pipeline not running — starting...")
                _start_pipeline()
        except Exception as exc:
            log.error("Watchdog error: %s", exc)
        time.sleep(_WATCHDOG_INTERVAL)


def start_watchdog():
    """Start the pipeline watchdog in a background daemon thread."""
    t = threading.Thread(target=_watchdog_loop, daemon=True, name="dlstreamer-watchdog")
    t.start()
    return t
