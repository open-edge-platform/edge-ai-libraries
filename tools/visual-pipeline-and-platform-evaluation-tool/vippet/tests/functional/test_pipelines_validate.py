"""Functional test covering the pipelines validate endpoint."""

import logging
from typing import Any

import pytest
import requests

from helpers.config import BASE_URL
from helpers.api_helpers import wait_for_job_completion

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

    all_statuses_response = http_client.get(
        f"{BASE_URL}/jobs/validation/status",
        timeout=30,
    )
    assert all_statuses_response.status_code == 200, (
        f"GET /jobs/validation/status returned {all_statuses_response.status_code}, "
        f"body={all_statuses_response.text}"
    )
    all_statuses = all_statuses_response.json()
    assert isinstance(all_statuses, list) and len(all_statuses) != 0, (
        "GET /jobs/validation/status returned an empty list"
    )
    logger.info("GET /jobs/validation/status returned %d job(s)", len(all_statuses))

    summary_response = http_client.get(
        f"{BASE_URL}/jobs/validation/{job_id}",
        timeout=30,
    )
    assert summary_response.status_code == 200, (
        f"GET /jobs/validation/{job_id} returned {summary_response.status_code}, "
        f"body={summary_response.text}"
    )
    summary = summary_response.json()
    assert summary.get("id") == job_id, (
        f"Job summary id mismatch: expected {job_id!r}, got {summary.get('id')!r}"
    )
    request_body = summary.get("request", {})
    assert request_body.get("pipeline_graph") == VALIDATION_PAYLOAD["pipeline_graph"], (
        f"Job summary pipeline_graph mismatch: {request_body.get('pipeline_graph')}"
    )
    assert request_body.get("parameters") == VALIDATION_PAYLOAD["parameters"], (
        f"Job summary parameters mismatch: {request_body.get('parameters')}"
    )
    logger.info("Job summary for %s matches the submitted payload", job_id)

    status_url = f"{BASE_URL}/jobs/validation/{job_id}/status"
    last_status = wait_for_job_completion(
        http_client, status_url, assert_initial_running=False
    )

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
