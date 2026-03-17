"""Functional test covering pipeline optimization flows."""

import logging

import pytest
import requests

from helpers.api_helpers import (
    JsonDict,
    start_optimization_job,
    wait_for_job_completion,
)
from helpers.config import BASE_URL

logger = logging.getLogger(__name__)


PIPELINE_ID = "license-plate-recognition"
PIPELINE_VARIANT = "cpu"

OPTIMIZATION_CASES = [
    (
        "preprocess",
        {
            "type": "preprocess",
            "parameters": {"search_duration": 10, "sample_duration": 3},
        },
    ),
    (
        "optimize",
        {
            "type": "optimize",
            "parameters": {"search_duration": 10, "sample_duration": 3},
        },
    ),
]


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
    job_id = start_optimization_job(http_client, PIPELINE_ID, PIPELINE_VARIANT, payload)
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
