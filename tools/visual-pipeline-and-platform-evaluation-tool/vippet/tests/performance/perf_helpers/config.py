# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared configuration constants for VIPPET performance tests."""

import os
from pathlib import Path

METRICS_URL: str = os.environ.get(
    "VIPPET_METRICS_URL", "http://localhost/metrics/stream"
)

PERF_CONFIG: str = os.environ.get("PERF_CONFIG", "default")

_DEFAULT_RESULTS_DIR: str = str(Path(__file__).resolve().parents[1] / "results")

PERF_RESULTS_DIR: str = os.environ.get("PERF_RESULTS_DIR", _DEFAULT_RESULTS_DIR)

METRICS_SAMPLE_INTERVAL: float = float(os.environ.get("PERF_METRICS_INTERVAL", "2.0"))

CONFIG_DIR: Path = Path(__file__).resolve().parents[1] / "config"
