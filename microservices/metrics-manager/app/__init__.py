# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Metrics Manager - Unified metrics collection, ingestion, and relay service.

A production-ready service that provides:
- System metrics collection via Telegraf
- REST API for custom metrics ingestion (JSON, InfluxDB, OpenTelemetry formats)
- Server-Sent Events (SSE) endpoint for real-time metrics streaming
- Prometheus-compatible metrics endpoint
"""

from importlib.metadata import PackageNotFoundError, version as _pkg_version
from pathlib import Path

from .main import app
from .models import Metric, MetricsBatch, MetricType, SimpleMetric
from .settings import Settings, get_settings
from .store import MetricsStore, get_metrics_store


def _resolve_version() -> str:
    """Resolve the package version.

    Resolution order:
    1. Installed distribution metadata via ``importlib.metadata`` — the
       canonical source for any wheel/sdist install (works in production
       containers where the package is ``pip install``-ed).
    2. Top-level ``VERSION`` file relative to this package — used during
       source checkouts where the package may not be installed (e.g.
       running ``pytest`` against the working tree without ``pip install -e .``).
    3. Literal ``"0.0.0"`` as a last-resort fallback so importing the
       package never raises.
    """
    try:
        return _pkg_version("metrics-manager")
    except PackageNotFoundError:
        pass
    version_file = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


__version__ = _resolve_version()
__all__ = [
    "app",
    "get_metrics_store",
    "get_settings",
    "Metric",
    "MetricsBatch",
    "MetricsStore",
    "MetricType",
    "Settings",
    "SimpleMetric",
]
