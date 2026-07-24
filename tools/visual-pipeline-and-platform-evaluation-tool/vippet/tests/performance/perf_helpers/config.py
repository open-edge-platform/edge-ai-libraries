# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared configuration constants for VIPPET performance tests."""

import os
from pathlib import Path
from typing import Any

import yaml

PERF_CONFIG: str = os.environ.get("PERF_CONFIG", "default")

CONFIG_DIR: Path = Path(__file__).resolve().parents[1] / "config"


def _load_perf_config() -> dict[str, Any]:
    """Load the performance config YAML selected by PERF_CONFIG env var."""
    config_path = CONFIG_DIR / f"{PERF_CONFIG}.yaml"
    if not config_path.exists():
        config_path = CONFIG_DIR / "default.yaml"
    with config_path.open() as f:
        return yaml.safe_load(f)


_PERF_YAML: dict[str, Any] = _load_perf_config()

# --- vippet section (connection settings) ---
_VIPPET_CFG: dict[str, Any] = _PERF_YAML.get("vippet", {})

BASE_URL: str = os.environ.get("VIPPET_BASE_URL") or str(
    _VIPPET_CFG.get("base_url", "http://localhost/api/v1")
)
REQUEST_TIMEOUT: float = float(_VIPPET_CFG.get("timeout", 600))
POLL_INTERVAL: float = float(_VIPPET_CFG.get("poll_interval", 2))
POLL_TIMEOUT: float = float(_VIPPET_CFG.get("max_job_duration", 600))

# --- metrics section ---
_METRICS_CFG: dict[str, Any] = _PERF_YAML.get("metrics", {})

METRICS_URL: str = os.environ.get("VIPPET_METRICS_URL") or str(
    _METRICS_CFG.get("metrics_url", "http://localhost/metrics/stream")
)
METRICS_SAMPLE_INTERVAL: float = float(
    os.environ.get(
        "PERF_METRICS_INTERVAL", str(_METRICS_CFG.get("sample_interval_seconds", 2.0))
    )
)

# --- benchmark section ---
_BENCHMARK_CFG: dict[str, Any] = _PERF_YAML.get("benchmark", {})
_EXECUTION_CFG: dict[str, Any] = _BENCHMARK_CFG.get("execution", {})
_FILTERS_CFG: dict[str, Any] = _BENCHMARK_CFG.get("filters", {})

PIPELINE_FILTER: str | list[str] = _BENCHMARK_CFG.get("pipelines", "*")
VARIANT_FILTER: list[str] = _BENCHMARK_CFG.get("variants", ["cpu", "gpu", "npu"])
STREAM_COUNTS: list[int] = _BENCHMARK_CFG.get("stream_counts", [1, 3])

MAX_RETRIES: int = int(_EXECUTION_CFG.get("max_retries", 2))
RETRY_DELAY_SECONDS: float = float(_EXECUTION_CFG.get("retry_delay_seconds", 5.0))
OUTPUT_MODE: str = _EXECUTION_CFG.get("output_mode", "disabled")
MAX_RUNTIME: float = float(_EXECUTION_CFG.get("max_runtime", 0))

SKIP_PIPELINES: list[str] = _FILTERS_CFG.get("skip_pipelines", [])
SKIP_VARIANTS: list[str] = _FILTERS_CFG.get("skip_variants", [])
REQUIRE_MODELS: bool = _FILTERS_CFG.get("require_models", True)

# --- results section ---
_RESULTS_CFG: dict[str, Any] = _PERF_YAML.get("results", {})

_DEFAULT_RESULTS_DIR: str = str(Path(__file__).resolve().parents[1] / "results")
PERF_RESULTS_DIR: str = os.environ.get("PERF_RESULTS_DIR") or str(
    _RESULTS_CFG.get("output_dir", _DEFAULT_RESULTS_DIR)
)
RESULT_FORMATS: list[str] = _RESULTS_CFG.get("formats", ["json", "csv"])
CREATE_LATEST_LINK: bool = _RESULTS_CFG.get("create_latest_link", True)
