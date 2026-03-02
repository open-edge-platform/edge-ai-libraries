"""Integration test covering pipeline optimization flows.

Run with Python 3.12+ and pytest while the VIPPET API is available locally:

    python3.12 -m pytest integration/test_pipeline_optimize_flow.py
"""

import logging
import time
from typing import Any

import pytest
import requests

from config import BASE_URL, POLL_INTERVAL_SECONDS, POLL_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


PIPELINE_NAME = "Simple Video Structurization (D-T-C) [CPU]"
OPTIMIZATION_CASES = [
    (
        "preprocess",
        {
            "type": "preprocess",
            "parameters": {"search_duration": 30, "sample_duration": 5},
        },
    ),
    (
        "optimize",
        {
            "type": "optimize",
            "parameters": {"search_duration": 30, "sample_duration": 5},
        },
    ),
]


def _fetch_pipeline_id(session: requests.Session, pipeline_name: str) -> str:
    logger.info("Fetching pipeline id for '%s'", pipeline_name)
    response = session.get(f"{BASE_URL}/pipelines", timeout=30)
    response.raise_for_status()
    pipelines: list[dict[str, Any]] = response.json()
    matching = next((p for p in pipelines if p.get("name") == pipeline_name), None)
    assert matching is not None, (
        f"Pipeline named '{pipeline_name}' not found in /pipelines response"
    )
    pipeline_id = matching.get("id")
    assert pipeline_id, "Matching pipeline missing 'id' field"
    logger.info("Using pipeline id %s for '%s'", pipeline_id, pipeline_name)
    return str(pipeline_id)


def _start_optimization_job(
    session: requests.Session,
    pipeline_id: str,
    payload: dict[str, Any],
) -> str:
    logger.info(
        "Starting pipeline optimization for id=%s case=%s",
        pipeline_id,
        payload.get("type"),
    )
    response = session.post(
        f"{BASE_URL}/pipelines/{pipeline_id}/optimize",
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    job_id = response.json().get("job_id")
    assert job_id, "Optimization response missing 'job_id'"
    logger.info("Optimization job started: %s", job_id)
    return str(job_id)


def _get_job_status(session: requests.Session, job_id: str) -> dict[str, Any]:
    response = session.get(
        f"{BASE_URL}/jobs/optimization/{job_id}/status",
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _wait_for_completion(session: requests.Session, job_id: str) -> dict[str, Any]:
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    first_status = _get_job_status(session, job_id)
    assert first_status.get("state") in {"RUNNING", "COMPLETED"}, (
        "Unexpected initial job state "
        f"{first_status.get('state')} for optimization job {job_id}"
    )
    logger.info(
        "Job %s initial state %s (elapsed=%sms)",
        job_id,
        first_status.get("state"),
        first_status.get("elapsed_time"),
    )
    if first_status.get("state") == "COMPLETED":
        logger.info("Job %s completed before polling loop", job_id)
        return first_status

    last_status = first_status

    while time.time() < deadline:
        if last_status.get("state") == "COMPLETED":
            logger.info("Job %s finished with COMPLETED state", job_id)
            return last_status
        time.sleep(POLL_INTERVAL_SECONDS)
        last_status = _get_job_status(session, job_id)
        logger.info(
            "Job %s polled state=%s error=%s",
            job_id,
            last_status.get("state"),
            last_status.get("error_message"),
        )

    pytest.fail(
        f"Optimization job {job_id} did not reach COMPLETED within {POLL_TIMEOUT_SECONDS} seconds"
    )


@pytest.mark.parametrize(
    "case_id,payload", OPTIMIZATION_CASES, ids=[c[0] for c in OPTIMIZATION_CASES]
)
def test_pipeline_optimize_flow(
    http_client: requests.Session,
    case_id: str,
    payload: dict[str, Any],
) -> None:
    logger.info("Running pipeline optimize flow case '%s'", case_id)
    pipeline_id = _fetch_pipeline_id(http_client, PIPELINE_NAME)
    job_id = _start_optimization_job(http_client, pipeline_id, payload)
    final_status = _wait_for_completion(http_client, job_id)

    assert final_status.get("state") == "COMPLETED", (
        f"Job {job_id} finished in unexpected state {final_status.get('state')}"
    )
    assert final_status.get("error_message") is None, (
        f"Job {job_id} returned error message: {final_status.get('error_message')}"
    )
