# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared configuration constants for VIPPET performance tests.
Values are resolved once at import time through
:func:`perf_helpers.settings.resolve_settings` (defaults -> YAML -> env).
The CLI (``python -m perf_helpers.cli``) passes its ``--config`` and flags
through ``PERF_CLI_LAYER``, so pytest resolves the same values with the
same sources as the CLI did.
"""

import os
from .settings import ResolvedSettings, read_cli_layer, resolve_settings

SETTINGS: ResolvedSettings = resolve_settings(
    env=os.environ, **read_cli_layer(os.environ)
)
# --- vippet section (connection settings) ---
BASE_URL: str = SETTINGS["vippet.base_url"]
REQUEST_TIMEOUT: float = SETTINGS["vippet.timeout"]
READINESS_TIMEOUT_SECONDS: float = SETTINGS["vippet.readiness_timeout_seconds"]
POLL_INTERVAL: float = SETTINGS["vippet.poll_interval"]
POLL_TIMEOUT: int = SETTINGS["vippet.max_job_duration"]

# --- metrics section ---
METRICS_URL: str = SETTINGS["metrics.metrics_url"]
CAPABILITIES_URL: str = SETTINGS["metrics.capabilities_url"]
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
SKIP_MISSING_MODELS: bool = SETTINGS["benchmark.filters.skip_missing_models"]
ON_UNKNOWN_FILTER_ID: str = SETTINGS["benchmark.filters.on_unknown_id"]

# --- results section ---
PERF_RESULTS_DIR: str = SETTINGS["results.output_dir"]
RESULT_FORMATS: list[str] = SETTINGS["results.formats"]
CREATE_LATEST_LINK: bool = SETTINGS["results.create_latest_link"]
SAVE_LOG: bool = SETTINGS["results.save_log"]
