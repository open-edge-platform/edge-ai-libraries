"""Functional test covering pipeline optimization flows."""

import logging

import pytest
import requests

from helpers.api_helpers import JsonDict, wait_for_job_completion
from config import BASE_URL

logger = logging.getLogger(__name__)


PIPELINE_ID = "license-plate-recognition"
PIPELINE_VARIANT = "cpu"

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


def _start_optimization_job(
    session: requests.Session,
    payload: JsonDict,
) -> str:
    logger.info(
        "Starting pipeline optimization for pipeline_id=%s variant_id=%s type=%s",
        PIPELINE_ID,
        PIPELINE_VARIANT,
        payload["type"],
    )
    response = session.post(
        f"{BASE_URL}/pipelines/{PIPELINE_ID}/variants/{PIPELINE_VARIANT}/optimize",
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    job_id = response.json().get("job_id")
    assert job_id, "Optimization response missing 'job_id'"
    logger.info("Optimization job started: %s", job_id)
    return str(job_id)


@pytest.mark.full
@pytest.mark.parametrize(
    "case_id,payload", OPTIMIZATION_CASES, ids=[c[0] for c in OPTIMIZATION_CASES]
)
def test_pipeline_optimize_flow(
    http_client: requests.Session,
    case_id: str,
    payload: JsonDict,
) -> None:
    logger.info("Running pipeline optimize flow case '%s'", case_id)
    job_id = _start_optimization_job(http_client, payload)
    status_url = f"{BASE_URL}/jobs/optimization/{job_id}/status"
    final_status = wait_for_job_completion(
        http_client,
        status_url,
        assert_initial_running=False,
    )

    assert final_status.get("state") == "COMPLETED", (
        f"Job {job_id} finished in unexpected state {final_status.get('state')}"
    )
    assert final_status.get("error_message") is None, (
        f"Job {job_id} returned error message: {final_status.get('error_message')}"
    )
