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
import httpx

from helpers.api_helpers import (
    start_performance_job,
    stop_performance_job,
    wait_for_job_completion,
)
from helpers.pipeline_case_helpers import PipelineCase

from perf_helpers.config import (
    BASE_URL,
    MAX_RETRIES,
    MAX_RUNTIME,
    OUTPUT_MODE,
    POLL_INTERVAL,
    RETRY_DELAY_SECONDS,
)
from perf_helpers.hw_monitor import HardwareMonitor

logger = logging.getLogger(__name__)

# How long to wait, after cancelling a timed-out job, for the backend to release 
# its single-job execution lease before the next attempt submits a new job.
STOP_POLL_TIMEOUT_SECONDS = 10.0


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


def _confirm_job_stopped(
    session: httpx.Client,
    status_url: str,
    timeout: float = STOP_POLL_TIMEOUT_SECONDS,
) -> None:
    """Best-effort poll of *status_url* until the job leaves ``RUNNING``.

    A 200 from ``stop_performance_job`` only means cancellation was
    *requested*; the backend releases its single-job execution lease
    asynchronously afterwards. Polling here narrows the race window before
    the next attempt submits a new job, without turning polling failures
    into a hard error – ``_attempt_performance_job`` already tolerates a
    409 on the next submission as a retryable outcome.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = session.get(status_url, timeout=30)
            response.raise_for_status()
            state = response.json().get("state")
        except Exception:
            logger.warning(
                "Failed to poll %s while confirming job stop", status_url, exc_info=True
            )
            return
        if state != "RUNNING":
            logger.info("Confirmed job at %s stopped with state=%s", status_url, state)
            return
        time.sleep(POLL_INTERVAL)
    logger.warning(
        "Job at %s still RUNNING after %.1fs waiting for stop confirmation – "
        "proceeding anyway; next submission may hit a 409",
        status_url,
        timeout,
    )


def _attempt_performance_job(
    session: httpx.Client, payload: dict[str, Any]
) -> dict[str, Any]:
    """Submit a performance job and wait for it to finish.

    Timeouts are reported as a synthetic ``TIMEOUT`` state (see
    :func:`wait_for_job_completion`'s ``fail_on_timeout`` parameter) rather
    than raising, so the caller's retry loop can treat it like any other
    non-``COMPLETED`` outcome. When a timeout occurs, the still-running job
    is stopped on a best-effort basis and we poll briefly for confirmation
    (:func:`_confirm_job_stopped`) so the backend's single job slot is
    freed before the next attempt is submitted. Because that confirmation
    is best-effort, a 409 from submitting the next attempt is still
    possible; it is caught here and reported as a synthetic ``CONFLICT``
    state so the retry loop can treat it the same way, instead of letting
    the exception abort the test.
    """
    try:
        job_id = start_performance_job(session, payload)  # type: ignore[arg-type]
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 409:
            message = f"Job submission conflicted with a still-active job (409): {exc}"
            logger.warning(message)
            return {"state": "CONFLICT", "error_message": message}
        raise

    status_url = f"{BASE_URL}/jobs/tests/performance/{job_id}/status"
    status = wait_for_job_completion(session, status_url, fail_on_timeout=False)  # type: ignore[arg-type]

    if status.get("state") == "TIMEOUT":
        try:
            stop_performance_job(session, job_id)  # type: ignore[arg-type]
        except Exception:
            logger.warning(
                "Failed to stop timed-out job_id=%s – it may still be running "
                "and could cause a 409 on the next job submission",
                job_id,
                exc_info=True,
            )
        else:
            _confirm_job_stopped(session, status_url)  # type: ignore[arg-type]

    return status


@pytest.mark.perf
def test_pipeline_performance(
    http_client: httpx.Client,
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
        final_status = _attempt_performance_job(http_client, payload)
        retries = 0
        while final_status.get("state") != "COMPLETED" and retries < MAX_RETRIES:
            retries += 1
            logger.warning(
                "Attempt %d/%d failed (state=%s, error=%s) – retrying after %.1fs",
                retries,
                MAX_RETRIES + 1,
                final_status.get("state"),
                final_status.get("error_message"),
                RETRY_DELAY_SECONDS,
            )
            time.sleep(RETRY_DELAY_SECONDS)
            final_status = _attempt_performance_job(http_client, payload)
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
