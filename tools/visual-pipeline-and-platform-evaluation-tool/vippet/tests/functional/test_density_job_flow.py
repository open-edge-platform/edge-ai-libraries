"""Functional test covering the density job happy path."""

import logging
import time
from collections.abc import Generator
from typing import Any

import pytest
import requests

from api_helpers import wait_for_job_completion
from config import BASE_URL
from pipeline_case_helpers import PipelineCase, discover_pipeline_cases_for_pytest

logger = logging.getLogger(__name__)

type JsonDict = dict[str, Any]

# Minimum acceptable FPS per stream for density tests
FLOOR_FPS: int = 30

# Stream rate used when a single pipeline variant is tested in isolation
STREAM_RATE: int = 100


PIPELINE_CASES, CASE_IDS = discover_pipeline_cases_for_pytest()


# Brief pause between tests
@pytest.fixture(autouse=True)
def _inter_test_pause() -> Generator[None, None, None]:
    yield
    time.sleep(0.5)


def _build_density_payload(case: PipelineCase) -> JsonDict:
    """Construct the POST /tests/density request body for *case*."""
    return {
        "fps_floor": FLOOR_FPS,
        "pipeline_density_specs": [
            {
                "pipeline": {
                    "source": "variant",
                    "pipeline_id": case.pipeline_id,
                    "variant_id": case.variant_id,
                },
                "stream_rate": STREAM_RATE,
            }
        ],
        "execution_config": {
            "max_runtime": "5",
            "output_mode": "disabled",
        },
    }


def _start_density_job(session: requests.Session, payload: JsonDict) -> str:
    """Submit a density test job and return the assigned job ID."""
    logger.info(
        "Starting density job – pipeline_id=%s variant_id=%s fps_floor=%d",
        payload["pipeline_density_specs"][0]["pipeline"]["pipeline_id"],
        payload["pipeline_density_specs"][0]["pipeline"]["variant_id"],
        payload["fps_floor"],
    )
    response = session.post(f"{BASE_URL}/tests/density", json=payload, timeout=30)
    response.raise_for_status()
    job_id: str = response.json().get("job_id", "")
    assert job_id, "Density test response missing 'job_id'"
    logger.info("Density job started: %s", job_id)
    return job_id


@pytest.mark.full
@pytest.mark.parametrize("case", PIPELINE_CASES, ids=CASE_IDS)
def test_density_job_completes_successfully(
    http_client: requests.Session,
    case: PipelineCase | None,
) -> None:
    """Verify that a density test job for *case* reaches COMPLETED state.

    Pipeline variants are discovered dynamically at collection time by querying
    ``GET /pipelines`` and ``GET /devices``.  Only (pipeline, variant) pairs
    whose variant name matches one of the device families reported by the
    devices endpoint (CPU / GPU / NPU) are included in the parametrize set.
    """
    assert case is not None
    logger.info(
        "Running density test for pipeline='%s' variant=%s",
        case.pipeline_name,
        case.device_family,
    )

    payload = _build_density_payload(case)
    job_id = _start_density_job(http_client, payload)

    status_url = f"{BASE_URL}/jobs/tests/density/{job_id}/status"
    final_status = wait_for_job_completion(http_client, status_url)

    assert final_status.get("state") == "COMPLETED", (
        f"Job {job_id} finished in unexpected state {final_status.get('state')}"
    )
    assert final_status.get("total_fps") is None, (
        f"Job {job_id} should not return total_fps for density tests"
    )
    assert (final_status.get("per_stream_fps") or 0) > 0, (
        f"Job {job_id} per_stream_fps must be greater than zero"
    )
    assert (final_status.get("total_streams") or 0) > 0, (
        f"Job {job_id} returned invalid total_streams"
    )
    assert final_status.get("error_message") is None, (
        f"Job {job_id} returned error message: {final_status.get('error_message')}"
    )
