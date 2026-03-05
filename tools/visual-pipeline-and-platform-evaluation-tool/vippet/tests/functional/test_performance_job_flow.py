"""Functional test covering the performance job happy path."""

import logging
import time
from collections.abc import Generator
from typing import Any

import pytest
import requests

from helpers.api_helpers import run_job_with_retry, wait_for_job_completion
from config import BASE_URL
from helpers.pipeline_case_helpers import PipelineCase, discover_pipeline_cases_for_pytest

logger = logging.getLogger(__name__)

type JsonDict = dict[str, Any]

# Seconds to wait before retrying a failed job
RETRY_DELAY_SECONDS: float = 5.0

# Number of parallel streams requested for each pipeline in the test
STREAMS_PER_PIPELINE: int = 3


PIPELINE_CASES, CASE_IDS = discover_pipeline_cases_for_pytest()


# Brief pause between tests
@pytest.fixture(autouse=True)
def _inter_test_pause() -> Generator[None, None, None]:
    yield
    time.sleep(0.5)


def _build_performance_payload(case: PipelineCase) -> JsonDict:
    """Construct the POST /tests/performance request body for *case*."""
    return {
        "pipeline_performance_specs": [
            {
                "pipeline": {
                    "source": "variant",
                    "pipeline_id": case.pipeline_id,
                    "variant_id": case.variant_id,
                },
                "streams": STREAMS_PER_PIPELINE,
            }
        ],
        "execution_config": {
            "output_mode": "disabled",
        },
    }


def _start_performance_job(session: requests.Session, payload: JsonDict) -> str:
    """Submit a performance test job and return the assigned job ID."""
    logger.info(
        "Starting performance job – pipeline_id=%s variant_id=%s streams=%d",
        payload["pipeline_performance_specs"][0]["pipeline"]["pipeline_id"],
        payload["pipeline_performance_specs"][0]["pipeline"]["variant_id"],
        payload["pipeline_performance_specs"][0]["streams"],
    )
    response = session.post(f"{BASE_URL}/tests/performance", json=payload, timeout=30)
    response.raise_for_status()
    job_id: str = response.json().get("job_id", "")
    assert job_id, "Performance test response missing 'job_id'"
    logger.info("Performance job started: %s", job_id)
    return job_id


def _attempt_performance_job(session: requests.Session, payload: JsonDict) -> JsonDict:
    """Submit a performance job and wait for it to finish.

    Returns the final status dict regardless of whether the job succeeded or
    failed, so the caller can decide whether to retry.
    """
    job_id = _start_performance_job(session, payload)
    status_url = f"{BASE_URL}/jobs/tests/performance/{job_id}/status"
    return wait_for_job_completion(session, status_url)


@pytest.mark.full
@pytest.mark.parametrize("case", PIPELINE_CASES, ids=CASE_IDS)
def test_performance_job_completes_successfully(
    http_client: requests.Session,
    case: PipelineCase | None,
) -> None:
    """Verify that a performance test job for *case* reaches COMPLETED state.

    Pipeline variants are discovered dynamically at collection time by querying
    ``GET /pipelines`` and ``GET /devices``.  Only (pipeline, variant) pairs
    whose variant name matches one of the device families reported by the
    devices endpoint (CPU / GPU / NPU) are included in the parametrize set.
    """
    assert case is not None
    logger.info(
        "Running performance test for pipeline='%s' variant=%s",
        case.pipeline_name,
        case.device_family,
    )

    payload = _build_performance_payload(case)
    final_status = run_job_with_retry(
        lambda: _attempt_performance_job(http_client, payload),
        retry_delay_seconds=RETRY_DELAY_SECONDS,
    )

    pipeline_label = f"pipeline_id={case.pipeline_id} variant_id={case.variant_id}"
    assert final_status.get("state") == "COMPLETED", (
        f"{pipeline_label} finished in unexpected state {final_status.get('state')}"
    )
    assert final_status.get("total_fps") is not None, (
        f"{pipeline_label} missing total_fps in response"
    )
    assert (final_status.get("per_stream_fps") or 0) > 0, (
        f"{pipeline_label} per_stream_fps must be greater than zero"
    )
    assert final_status.get("total_streams") == STREAMS_PER_PIPELINE, (
        f"{pipeline_label} total_streams is {final_status.get('total_streams')}, expected {STREAMS_PER_PIPELINE}"
    )
    assert final_status.get("error_message") is None, (
        f"{pipeline_label} returned error message: {final_status.get('error_message')}"
    )
