# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Performance benchmark tests for VIPPET pipelines.

Each test case runs a single (pipeline, variant, stream_count) combination,
collects hardware metrics during execution, and appends results to the
session-scoped results_collector for report generation on teardown.
"""

import logging
import time
from typing import Any

import pytest
import requests

from helpers.api_helpers import (
    run_job_with_retry,
    start_performance_job,
    wait_for_job_completion,
)
from helpers.config import BASE_URL
from helpers.pipeline_case_helpers import PipelineCase

from perf_helpers.config import MAX_RUNTIME, OUTPUT_MODE, RETRY_DELAY_SECONDS
from perf_helpers.hw_monitor import HardwareMonitor

logger = logging.getLogger(__name__)


def _build_performance_payload(case: PipelineCase, streams: int) -> dict[str, Any]:
    """Construct the POST /tests/performance request body."""
    return {
        "pipeline_performance_specs": [
            {
                "pipeline": {
                    "source": "variant",
                    "pipeline_id": case.pipeline_id,
                    "variant_id": case.variant_id,
                },
                "streams": streams,
            }
        ],
        "execution_config": {
            "output_mode": OUTPUT_MODE,
            "max_runtime": MAX_RUNTIME,
        },
    }


def _attempt_performance_job(
    session: requests.Session, payload: dict[str, Any]
) -> dict[str, Any]:
    """Submit a performance job and wait for it to finish."""
    job_id = start_performance_job(session, payload)
    status_url = f"{BASE_URL}/jobs/tests/performance/{job_id}/status"
    return wait_for_job_completion(session, status_url)


@pytest.mark.perf
def test_pipeline_performance(
    http_client: requests.Session,
    pipeline_case: PipelineCase | None,
    stream_count: int,
    hw_monitor: HardwareMonitor,
    results_collector: list[dict[str, Any]],
) -> None:
    """Run a performance benchmark for a single (pipeline, variant, stream_count) combination."""
    assert pipeline_case is not None
    logger.info(
        "Running performance benchmark: pipeline='%s' variant=%s streams=%d",
        pipeline_case.pipeline_name,
        pipeline_case.device_family,
        stream_count,
    )

    payload = _build_performance_payload(pipeline_case, stream_count)

    start_time = time.time()
    hw_monitor.start()

    try:
        final_status = run_job_with_retry(
            lambda: _attempt_performance_job(http_client, payload),
            retry_delay_seconds=RETRY_DELAY_SECONDS,
        )
    finally:
        hw_stats = hw_monitor.stop()

    duration = time.time() - start_time
    is_success = final_status.get("state") == "COMPLETED"

    total_fps = final_status.get("total_fps") if is_success else None
    per_stream_fps = final_status.get("per_stream_fps") if is_success else None

    results_collector.append(
        {
            "pipeline_name": pipeline_case.pipeline_name,
            "pipeline_id": pipeline_case.pipeline_id,
            "variant_name": pipeline_case.device_family,
            "variant_id": pipeline_case.variant_id,
            "streams": stream_count,
            "status": "success" if is_success else "failed",
            "total_fps": total_fps,
            "per_stream_fps": per_stream_fps,
            "result": final_status,
            "hw_metrics": hw_stats,
            "duration_seconds": duration,
            "job_id": final_status.get("job_id", ""),
            "error": final_status.get("error_message"),
        }
    )

    pipeline_label = (
        f"pipeline_id={pipeline_case.pipeline_id} "
        f"variant_id={pipeline_case.variant_id} "
        f"streams={stream_count}"
    )
    assert final_status.get("state") == "COMPLETED", (
        f"{pipeline_label} finished in unexpected state {final_status.get('state')}"
    )
    assert (final_status.get("total_fps") or 0) > 0, (
        f"{pipeline_label} total_fps must be greater than zero"
    )
    assert (final_status.get("per_stream_fps") or 0) > 0, (
        f"{pipeline_label} per_stream_fps must be greater than zero"
    )
