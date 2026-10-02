# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared configuration constants for VIPPET performance tests.
Values are resolved once at import time through
:func:`perf_helpers.settings.resolve_settings` (defaults -> YAML -> env).
The CLI (``python -m perf_helpers.cli``) layers CLI flags on top and hands
the fully resolved YAML to pytest through ``PERF_CONFIG_FILE``, so direct
``pytest`` runs and CLI runs read settings the same way.
"""

import os
from .settings import ResolvedSettings, resolve_settings

PERF_CONFIG: str = os.environ.get("PERF_CONFIG", "default")
SETTINGS: ResolvedSettings = resolve_settings(env=os.environ)
# --- vippet section (connection settings) ---
BASE_URL: str = SETTINGS["vippet.base_url"]
REQUEST_TIMEOUT: float = SETTINGS["vippet.timeout"]
READINESS_TIMEOUT_SECONDS: float = SETTINGS["vippet.readiness_timeout_seconds"]
POLL_INTERVAL: float = SETTINGS["vippet.poll_interval"]
POLL_TIMEOUT: int = SETTINGS["vippet.max_job_duration"]

# --- metrics section ---
METRICS_URL: str = SETTINGS["metrics.metrics_url"]
METRICS_SAMPLE_INTERVAL: float = SETTINGS["metrics.sample_interval_seconds"]

# --- benchmark section ---
PIPELINE_FILTER: str | list[str] = SETTINGS["benchmark.pipelines"]
VARIANT_FILTER: list[str] = SETTINGS["benchmark.variants"]
STREAM_COUNTS: list[int] = SETTINGS["benchmark.stream_counts"]
MAX_RETRIES: int = SETTINGS["benchmark.execution.max_retries"]
RETRY_DELAY_SECONDS: float = SETTINGS["benchmark.execution.retry_delay_seconds"]
OUTPUT_MODE: str = SETTINGS["benchmark.execution.output_mode"]
MAX_RUNTIME: float = SETTINGS["benchmark.execution.max_runtime"]
SKIP_PIPELINES: list[str] = SETTINGS["benchmark.filters.skip_pipelines"]
SKIP_VARIANTS: list[str] = SETTINGS["benchmark.filters.skip_variants"]
REQUIRE_MODELS: bool = SETTINGS["benchmark.filters.require_models"]
ON_UNKNOWN_FILTER_ID: str = SETTINGS["benchmark.filters.on_unknown_id"]

# --- results section ---
PERF_RESULTS_DIR: str = SETTINGS["results.output_dir"]
RESULT_FORMATS: list[str] = SETTINGS["results.formats"]
CREATE_LATEST_LINK: bool = SETTINGS["results.create_latest_link"]
