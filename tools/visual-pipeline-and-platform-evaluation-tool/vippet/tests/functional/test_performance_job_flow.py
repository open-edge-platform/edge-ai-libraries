"""Functional test covering the performance job happy path."""

import logging
import time
from collections.abc import Generator

import pytest
import requests

from helpers.api_helpers import (
    JsonDict,
    run_job_with_retry,
    start_performance_job,
    wait_for_job_completion,
)
from helpers.config import BASE_URL
from helpers.pipeline_case_helpers import (
    PipelineCase,
    discover_pipeline_cases_for_pytest,
)

logger = logging.getLogger(__name__)

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


def _build_performance_payload(
    case: PipelineCase,
    output_mode: str = "disabled",
    streams: int = STREAMS_PER_PIPELINE,
) -> JsonDict:
    """Construct the POST /tests/performance request body for *case*."""
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
            "output_mode": output_mode,
        },
    }


def _attempt_performance_job(session: requests.Session, payload: JsonDict) -> JsonDict:
    """Submit a performance job and wait for it to finish.

    Returns the final status dict regardless of whether the job succeeded or
    failed, so the caller can decide whether to retry.
    """
    job_id = start_performance_job(session, payload)
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


@pytest.mark.full
@pytest.mark.parametrize("case", PIPELINE_CASES, ids=CASE_IDS)
def test_performance_file_output_job_completes_successfully(
    http_client: requests.Session,
    case: PipelineCase | None,
) -> None:
    """Verify that a performance job with file output mode completes and produces output files.

    Runs each pipeline/variant with ``output_mode="file"`` and a single stream,
    then asserts that the job reaches ``COMPLETED`` state and that
    ``video_output_paths`` in the response contains at least one non-empty path.
    """
    assert case is not None
    logger.info(
        "Running performance (file output) test for pipeline='%s' variant=%s",
        case.pipeline_name,
        case.device_family,
    )

    payload = _build_performance_payload(case, output_mode="file", streams=1)
    final_status = run_job_with_retry(
        lambda: _attempt_performance_job(http_client, payload),
        retry_delay_seconds=RETRY_DELAY_SECONDS,
    )

    pipeline_label = f"pipeline_id={case.pipeline_id} variant_id={case.variant_id}"
    assert final_status.get("state") == "COMPLETED", (
        f"{pipeline_label} finished in unexpected state {final_status.get('state')}"
    )
    assert final_status.get("error_message") is None, (
        f"{pipeline_label} returned error message: {final_status.get('error_message')}"
    )

    video_output_paths = final_status.get("video_output_paths")
    assert isinstance(video_output_paths, dict) and video_output_paths, (
        f"{pipeline_label} 'video_output_paths' must be a non-empty dict, got {video_output_paths!r}"
    )
    for variant_path, paths in video_output_paths.items():
        assert isinstance(paths, list) and len(paths) > 0, (
            f"{pipeline_label} 'video_output_paths[{variant_path!r}]' must be a non-empty list, got {paths!r}"
        )
    logger.info(
        "%s completed with video output paths: %s",
        pipeline_label,
        video_output_paths,
    )


@pytest.mark.full
@pytest.mark.parametrize("case", PIPELINE_CASES, ids=CASE_IDS)
def test_performance_live_stream_output_job_completes_successfully(
    http_client: requests.Session,
    case: PipelineCase | None,
) -> None:
    """Submits a performance job for every predefined pipeline/device variant with live_stream output and asserts each job reaches COMPLETED state with valid stream URLs."""
    assert case is not None
    logger.info(
        "Running performance (live stream output) test for pipeline='%s' variant=%s",
        case.pipeline_name,
        case.device_family,
    )

    payload = _build_performance_payload(case, output_mode="live_stream", streams=1)
    final_status = run_job_with_retry(
        lambda: _attempt_performance_job(http_client, payload),
        retry_delay_seconds=RETRY_DELAY_SECONDS,
    )

    pipeline_label = f"pipeline_id={case.pipeline_id} variant_id={case.variant_id}"
    assert final_status.get("state") == "COMPLETED", (
        f"{pipeline_label} finished in unexpected state {final_status.get('state')}"
    )
    assert final_status.get("error_message") is None, (
        f"{pipeline_label} returned error message: {final_status.get('error_message')}"
    )

    live_stream_urls = final_status.get("live_stream_urls")
    assert isinstance(live_stream_urls, dict) and live_stream_urls, (
        f"{pipeline_label} 'live_stream_urls' must be a non-empty dict, got {live_stream_urls!r}"
    )
    for pipeline_id, url in live_stream_urls.items():
        assert isinstance(url, str) and url, (
            f"{pipeline_label} 'live_stream_urls[{pipeline_id!r}]' must be a non-empty string, got {url!r}"
        )
    logger.info(
        "%s completed with live stream URLs: %s",
        pipeline_label,
        live_stream_urls,
    )


@pytest.mark.smoke
def test_start_performance_job_with_zero_streams_returns_400(
    http_client: requests.Session,
) -> None:
    """Posts a performance test request with streams=0 to POST /tests/performance and asserts 400."""
    payload = {
        "pipeline_performance_specs": [
            {
                "pipeline": {
                    "source": "variant",
                    "pipeline_id": "license-plate-recognition",
                    "variant_id": "cpu",
                },
                "streams": 0,
            }
        ],
        "execution_config": {"output_mode": "disabled"},
    }

    response = http_client.post(
        f"{BASE_URL}/tests/performance", json=payload, timeout=30
    )

    assert response.status_code == 400, (
        f"Expected 400 for performance job with streams=0, "
        f"got {response.status_code}, body={response.text}"
    )


@pytest.mark.smoke
def test_start_performance_job_with_nonexistent_variant_returns_400(
    http_client: requests.Session,
) -> None:
    """Posts a performance test request referencing a non-existent variant and asserts 400."""
    payload = {
        "pipeline_performance_specs": [
            {
                "pipeline": {
                    "source": "variant",
                    "pipeline_id": "does-not-exist",
                    "variant_id": "does-not-exist",
                },
                "streams": 1,
            }
        ],
        "execution_config": {"output_mode": "disabled"},
    }

    response = http_client.post(
        f"{BASE_URL}/tests/performance", json=payload, timeout=30
    )

    assert response.status_code == 400, (
        f"Expected 400 for performance job with non-existent variant, "
        f"got {response.status_code}, body={response.text}"
    )
