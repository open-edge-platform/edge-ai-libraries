# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared configuration constants for VIPPET performance tests."""

import os
from pathlib import Path
from typing import Any

import yaml

METRICS_URL: str = os.environ.get(
    "VIPPET_METRICS_URL", "http://localhost/metrics/stream"
)

PERF_CONFIG: str = os.environ.get("PERF_CONFIG", "default")

_DEFAULT_RESULTS_DIR: str = str(Path(__file__).resolve().parents[1] / "results")

PERF_RESULTS_DIR: str = os.environ.get("PERF_RESULTS_DIR", _DEFAULT_RESULTS_DIR)

METRICS_SAMPLE_INTERVAL: float = float(os.environ.get("PERF_METRICS_INTERVAL", "2.0"))

CONFIG_DIR: Path = Path(__file__).resolve().parents[1] / "config"


def _load_perf_config() -> dict[str, Any]:
    """Load the performance config YAML selected by PERF_CONFIG env var."""
    config_path = CONFIG_DIR / f"{PERF_CONFIG}.yaml"
    if not config_path.exists():
        config_path = CONFIG_DIR / "default.yaml"
    with config_path.open() as f:
        return yaml.safe_load(f)


_PERF_YAML: dict[str, Any] = _load_perf_config()
_BENCHMARK_CFG: dict[str, Any] = _PERF_YAML.get("benchmark", {})
_EXECUTION_CFG: dict[str, Any] = _BENCHMARK_CFG.get("execution", {})
_RESULTS_CFG: dict[str, Any] = _PERF_YAML.get("results", {})

STREAM_COUNTS: list[int] = _BENCHMARK_CFG.get("stream_counts", [1, 3])
RETRY_DELAY_SECONDS: float = float(_EXECUTION_CFG.get("retry_delay_seconds", 5.0))
OUTPUT_MODE: str = _EXECUTION_CFG.get("output_mode", "disabled")
MAX_RUNTIME: float = float(_EXECUTION_CFG.get("max_runtime", 0))
RESULT_FORMATS: list[str] = _RESULTS_CFG.get("formats", ["json", "csv"])
CREATE_LATEST_LINK: bool = _RESULTS_CFG.get("create_latest_link", True)
