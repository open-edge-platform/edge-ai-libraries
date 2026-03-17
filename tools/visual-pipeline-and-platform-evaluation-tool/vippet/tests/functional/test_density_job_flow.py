"""Functional test covering the density job happy path."""

import logging
import time
from collections.abc import Generator
from typing import Any

import pytest
import requests

from helpers.api_helpers import (
    run_job_with_retry,
    start_density_job,
    wait_for_job_completion,
)
from helpers.config import BASE_URL
from helpers.pipeline_case_helpers import (
    PipelineCase,
    discover_pipeline_cases_for_pytest,
)

logger = logging.getLogger(__name__)

type JsonDict = dict[str, Any]

# Seconds to wait before retrying a failed job
RETRY_DELAY_SECONDS: float = 5.0

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


def _attempt_density_job(session: requests.Session, payload: JsonDict) -> JsonDict:
    """Submit a density job and wait for it to finish.

    Returns the final status dict regardless of whether the job succeeded or
    failed, so the caller can decide whether to retry.
    """
    job_id = start_density_job(session, payload)
    status_url = f"{BASE_URL}/jobs/tests/density/{job_id}/status"
    return wait_for_job_completion(session, status_url)


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
    final_status = run_job_with_retry(
        lambda: _attempt_density_job(http_client, payload),
        retry_delay_seconds=RETRY_DELAY_SECONDS,
    )

    pipeline_label = f"pipeline_id={case.pipeline_id} variant_id={case.variant_id}"
    assert final_status.get("state") == "COMPLETED", (
        f"{pipeline_label} finished in unexpected state {final_status.get('state')}"
    )
    assert final_status.get("total_fps") is None, (
        f"{pipeline_label} should not return total_fps for density tests"
    )
    assert (final_status.get("per_stream_fps") or 0) > 0, (
        f"{pipeline_label} per_stream_fps must be greater than zero"
    )
    assert (final_status.get("total_streams") or 0) > 0, (
        f"{pipeline_label} returned invalid total_streams"
    )
    assert final_status.get("error_message") is None, (
        f"{pipeline_label} returned error message: {final_status.get('error_message')}"
    )


@pytest.mark.smoke
def test_start_density_job_with_nonexistent_variant_returns_400(
    http_client: requests.Session,
) -> None:
    """Posts a density test request referencing a non-existent variant and asserts 400."""
    payload = {
        "fps_floor": 30,
        "pipeline_density_specs": [
            {
                "pipeline": {
                    "source": "variant",
                    "pipeline_id": "does-not-exist",
                    "variant_id": "does-not-exist",
                },
                "stream_rate": 10,
            }
        ],
        "execution_config": {"max_runtime": "5", "output_mode": "disabled"},
    }

    response = http_client.post(f"{BASE_URL}/tests/density", json=payload, timeout=30)

    assert response.status_code == 400, (
        f"Expected 400 for density job with non-existent variant, "
        f"got {response.status_code}, body={response.text}"
    )
