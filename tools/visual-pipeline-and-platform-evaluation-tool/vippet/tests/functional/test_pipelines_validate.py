"""Functional test covering the pipelines validate endpoint."""

import logging
import time
from typing import Any

import pytest
import requests

from config import BASE_URL, POLL_INTERVAL_SECONDS, POLL_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

VALIDATION_PAYLOAD: dict[str, Any] = {
    "type": "GStreamer",
    "pipeline_graph": {
        "nodes": [
            {"id": "0", "type": "videotestsrc", "data": {}},
            {"id": "1", "type": "videoconvert", "data": {}},
            {"id": "2", "type": "fakesink", "data": {}},
        ],
        "edges": [
            {"id": "0", "source": "0", "target": "1"},
            {"id": "1", "source": "1", "target": "2"},
        ],
    },
    "parameters": {"max-runtime": 10},
}


@pytest.mark.full
def test_pipeline_validate_job_completes(http_client: requests.Session) -> None:
    logger.info("Submitting validation job to %s/pipelines/validate", BASE_URL)
    response = http_client.post(
        f"{BASE_URL}/pipelines/validate",
        json=VALIDATION_PAYLOAD,
        timeout=60,
    )
    assert response.status_code == 202, (
        f"Validation endpoint returned {response.status_code}, body={response.text}"
    )
    payload = response.json()
    assert isinstance(payload, dict), "Validation response must be an object"
    job_id = payload.get("job_id")
    assert isinstance(job_id, str) and job_id, "Validation response missing job_id"
    logger.info("Validation job accepted with id %s", job_id)

    deadline = time.time() + POLL_TIMEOUT_SECONDS
    status_url = f"{BASE_URL}/jobs/validation/{job_id}/status"
    last_status: dict[str, Any] | None = None
    while time.time() < deadline:
        response = http_client.get(status_url, timeout=30)
        response.raise_for_status()
        last_status = response.json()
        assert isinstance(last_status, dict), (
            "Validation status payload must be an object"
        )
        state = last_status.get("state")
        logger.info(
            "Validation job %s polled state=%s is_valid=%s",
            job_id,
            state,
            last_status.get("is_valid"),
        )
        if state == "COMPLETED":
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    assert last_status is not None, "Validation job status polling produced no data"
    assert last_status.get("state") == "COMPLETED", (
        f"Validation job {job_id} finished in unexpected state {last_status.get('state')}"
    )
    assert last_status.get("is_valid") is True, (
        f"Validation job {job_id} expected is_valid=True, got {last_status.get('is_valid')}"
    )


@pytest.mark.smoke
def test_validate_pipeline_with_invalid_max_runtime_returns_400(
    http_client: requests.Session,
) -> None:
    """Posts a pipeline validation request with max-runtime=0 to POST /pipelines/validate and asserts 400."""
    payload = {
        "type": "GStreamer",
        "pipeline_graph": {
            "nodes": [
                {"id": "0", "type": "videotestsrc", "data": {}},
                {"id": "1", "type": "fakesink", "data": {}},
            ],
            "edges": [{"id": "0", "source": "0", "target": "1"}],
        },
        "parameters": {"max-runtime": 0},
    }

    response = http_client.post(
        f"{BASE_URL}/pipelines/validate",
        json=payload,
        timeout=30,
    )

    assert response.status_code == 400, (
        f"Expected 400 for max-runtime=0 validation request, "
        f"got {response.status_code}, body={response.text}"
    )
