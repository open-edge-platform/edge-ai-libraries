"""Functional tests for job management endpoints (status, summary, stop)."""

import logging
from typing import Any
from uuid import uuid4

import pytest
import requests

from helpers.api_helpers import (
    start_density_job,
    start_optimization_job,
    start_performance_job,
    wait_for_job_completion,
)
from helpers.config import BASE_URL

logger = logging.getLogger(__name__)

type JsonDict = dict[str, Any]

# IDs that will never exist in the system
_NONEXISTENT_JOB_ID = f"does-not-exist-{uuid4().hex[:8]}"

PIPELINE_ID = "age-gender-recognition"
PIPELINE_VARIANT = "cpu"


def _start_performance_job(session: requests.Session) -> str:
    """Submit a minimal performance job and return its job_id."""
    payload = {
        "pipeline_performance_specs": [
            {
                "pipeline": {
                    "source": "variant",
                    "pipeline_id": PIPELINE_ID,
                    "variant_id": PIPELINE_VARIANT,
                },
                "streams": 1,
            }
        ],
        "execution_config": {"output_mode": "disabled", "max_runtime": "5"},
    }
    return start_performance_job(session, payload)


def _start_density_job(session: requests.Session) -> str:
    """Submit a minimal density job and return its job_id."""
    payload = {
        "fps_floor": 30,
        "pipeline_density_specs": [
            {
                "pipeline": {
                    "source": "variant",
                    "pipeline_id": PIPELINE_ID,
                    "variant_id": PIPELINE_VARIANT,
                },
                "stream_rate": 100,
            }
        ],
        "execution_config": {"max_runtime": "5", "output_mode": "disabled"},
    }
    return start_density_job(session, payload)


def _start_optimization_job(session: requests.Session) -> str:
    """Submit a minimal optimization job and return its job_id."""
    payload = {
        "type": "preprocess",
        "parameters": {"search_duration": 5, "sample_duration": 2},
    }
    return start_optimization_job(session, PIPELINE_ID, PIPELINE_VARIANT, payload)


@pytest.mark.smoke
def test_get_performance_job_status_for_nonexistent_job_returns_404(
    http_client: requests.Session,
) -> None:
    """Calls GET /jobs/tests/performance/{job_id}/status with a non-existent job ID and asserts 404."""
    response = http_client.get(
        f"{BASE_URL}/jobs/tests/performance/{_NONEXISTENT_JOB_ID}/status",
        timeout=30,
    )

    assert response.status_code == 404, (
        f"Expected 404 for unknown performance job, "
        f"got {response.status_code}, body={response.text}"
    )


@pytest.mark.smoke
def test_stop_performance_job_for_nonexistent_job_returns_404(
    http_client: requests.Session,
) -> None:
    """Calls DELETE /jobs/tests/performance/{job_id} with a non-existent job ID and asserts 404."""
    response = http_client.delete(
        f"{BASE_URL}/jobs/tests/performance/{_NONEXISTENT_JOB_ID}",
        timeout=30,
    )

    assert response.status_code == 404, (
        f"Expected 404 for unknown performance job stop, "
        f"got {response.status_code}, body={response.text}"
    )


@pytest.mark.full
def test_get_all_performance_job_statuses_returns_list(
    http_client: requests.Session,
) -> None:
    """After submitting a performance job, GET /jobs/tests/performance/status returns a non-empty list containing the job."""
    job_id = _start_performance_job(http_client)

    response = http_client.get(f"{BASE_URL}/jobs/tests/performance/status", timeout=30)

    assert response.status_code == 200, (
        f"Expected 200 from /jobs/tests/performance/status, "
        f"got {response.status_code}, body={response.text}"
    )
    statuses = response.json()
    assert isinstance(statuses, list), "Response must be a list"
    assert statuses, "Expected at least one performance job in the list"
    job_ids = [s.get("id") for s in statuses]
    assert job_id in job_ids, (
        f"Submitted job_id={job_id} not found in status list: {job_ids}"
    )


@pytest.mark.full
def test_get_performance_job_summary_returns_correct_request(
    http_client: requests.Session,
) -> None:
    """After submitting a performance job, GET /jobs/tests/performance/{job_id} echoes back the original request."""
    job_id = _start_performance_job(http_client)

    response = http_client.get(
        f"{BASE_URL}/jobs/tests/performance/{job_id}", timeout=30
    )

    assert response.status_code == 200, (
        f"Expected 200 for performance job summary, "
        f"got {response.status_code}, body={response.text}"
    )
    summary = response.json()
    assert summary.get("id") == job_id, (
        f"Summary id {summary.get('id')!r} does not match submitted job_id={job_id!r}"
    )
    assert "request" in summary, "Summary must contain 'request' field"


@pytest.mark.full
def test_stop_completed_performance_job_returns_409(
    http_client: requests.Session,
) -> None:
    """After a performance job completes, DELETE /jobs/tests/performance/{job_id} returns 409 (not running)."""
    job_id = _start_performance_job(http_client)
    status_url = f"{BASE_URL}/jobs/tests/performance/{job_id}/status"
    wait_for_job_completion(http_client, status_url)

    response = http_client.delete(
        f"{BASE_URL}/jobs/tests/performance/{job_id}",
        timeout=30,
    )

    assert response.status_code == 409, (
        f"Expected 409 when stopping a completed performance job, "
        f"got {response.status_code}, body={response.text}"
    )


@pytest.mark.smoke
def test_get_density_job_status_for_nonexistent_job_returns_404(
    http_client: requests.Session,
) -> None:
    """Calls GET /jobs/tests/density/{job_id}/status with a non-existent job ID and asserts 404."""
    response = http_client.get(
        f"{BASE_URL}/jobs/tests/density/{_NONEXISTENT_JOB_ID}/status",
        timeout=30,
    )

    assert response.status_code == 404, (
        f"Expected 404 for unknown density job, "
        f"got {response.status_code}, body={response.text}"
    )


@pytest.mark.smoke
def test_stop_density_job_for_nonexistent_job_returns_404(
    http_client: requests.Session,
) -> None:
    """Calls DELETE /jobs/tests/density/{job_id} with a non-existent job ID and asserts 404."""
    response = http_client.delete(
        f"{BASE_URL}/jobs/tests/density/{_NONEXISTENT_JOB_ID}",
        timeout=30,
    )

    assert response.status_code == 404, (
        f"Expected 404 for unknown density job stop, "
        f"got {response.status_code}, body={response.text}"
    )


@pytest.mark.full
def test_get_all_density_job_statuses_returns_list(
    http_client: requests.Session,
) -> None:
    """After submitting a density job, GET /jobs/tests/density/status returns a non-empty list containing the job."""
    job_id = _start_density_job(http_client)

    response = http_client.get(f"{BASE_URL}/jobs/tests/density/status", timeout=30)

    assert response.status_code == 200, (
        f"Expected 200 from /jobs/tests/density/status, "
        f"got {response.status_code}, body={response.text}"
    )
    statuses = response.json()
    assert isinstance(statuses, list), "Response must be a list"
    assert statuses, "Expected at least one density job in the list"
    job_ids = [s.get("id") for s in statuses]
    assert job_id in job_ids, (
        f"Submitted job_id={job_id} not found in status list: {job_ids}"
    )


@pytest.mark.full
def test_get_density_job_summary_returns_correct_request(
    http_client: requests.Session,
) -> None:
    """After submitting a density job, GET /jobs/tests/density/{job_id} echoes back the original request."""
    job_id = _start_density_job(http_client)

    response = http_client.get(f"{BASE_URL}/jobs/tests/density/{job_id}", timeout=30)

    assert response.status_code == 200, (
        f"Expected 200 for density job summary, "
        f"got {response.status_code}, body={response.text}"
    )
    summary = response.json()
    assert summary.get("id") == job_id, (
        f"Summary id {summary.get('id')!r} does not match submitted job_id={job_id!r}"
    )
    assert "request" in summary, "Summary must contain 'request' field"


@pytest.mark.full
def test_stop_completed_density_job_returns_409(
    http_client: requests.Session,
) -> None:
    """After a density job completes, DELETE /jobs/tests/density/{job_id} returns 409 (not running)."""
    job_id = _start_density_job(http_client)
    status_url = f"{BASE_URL}/jobs/tests/density/{job_id}/status"
    wait_for_job_completion(http_client, status_url)

    response = http_client.delete(
        f"{BASE_URL}/jobs/tests/density/{job_id}",
        timeout=30,
    )

    assert response.status_code == 409, (
        f"Expected 409 when stopping a completed density job, "
        f"got {response.status_code}, body={response.text}"
    )


@pytest.mark.smoke
def test_get_optimization_job_status_for_nonexistent_job_returns_404(
    http_client: requests.Session,
) -> None:
    """Calls GET /jobs/optimization/{job_id}/status with a non-existent job ID and asserts 404."""
    response = http_client.get(
        f"{BASE_URL}/jobs/optimization/{_NONEXISTENT_JOB_ID}/status",
        timeout=30,
    )

    assert response.status_code == 404, (
        f"Expected 404 for unknown optimization job status, "
        f"got {response.status_code}, body={response.text}"
    )


@pytest.mark.full
def test_get_all_optimization_job_statuses_returns_list(
    http_client: requests.Session,
) -> None:
    """After an optimization job, GET /jobs/optimization/status returns a non-empty list containing the job."""
    job_id = _start_optimization_job(http_client)

    response = http_client.get(f"{BASE_URL}/jobs/optimization/status", timeout=30)

    assert response.status_code == 200, (
        f"Expected 200 from /jobs/optimization/status, "
        f"got {response.status_code}, body={response.text}"
    )
    statuses = response.json()
    assert isinstance(statuses, list), "Response must be a list"
    assert statuses, "Expected at least one optimization job in the list"
    job_ids = [s.get("id") for s in statuses]
    assert job_id in job_ids, (
        f"Submitted job_id={job_id} not found in status list: {job_ids}"
    )


@pytest.mark.full
def test_get_optimization_job_summary_returns_correct_request(
    http_client: requests.Session,
) -> None:
    """After an optimization job, GET /jobs/optimization/{job_id} echoes back the original request."""
    job_id = _start_optimization_job(http_client)

    response = http_client.get(f"{BASE_URL}/jobs/optimization/{job_id}", timeout=30)

    assert response.status_code == 200, (
        f"Expected 200 for optimization job summary, "
        f"got {response.status_code}, body={response.text}"
    )
    summary = response.json()
    assert summary.get("id") == job_id, (
        f"Summary id {summary.get('id')!r} does not match submitted job_id={job_id!r}"
    )
