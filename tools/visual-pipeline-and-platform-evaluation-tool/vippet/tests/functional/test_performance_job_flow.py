"""Integration test covering the performance job happy path.

Run with Python 3.12+ and pytest while the VIPPET API is available locally:

    python3.12 -m pytest integration/test_performance_job_flow.py
"""

import logging
import os
import time
from typing import Any

import pytest
import requests

from config import BASE_URL, POLL_INTERVAL_SECONDS, POLL_TIMEOUT_SECONDS

ALL_PIPELINE_CASES = [
    (
        "simple_video_struct_cpu",
        ("Simple Video Structurization (D-T-C) [CPU]",),
        ("CPU",),
    ),
    (
        "simple_video_struct_gpu",
        ("Simple Video Structurization (D-T-C) [GPU]",),
        ("GPU",),
    ),
    (
        "nvr_dual_cpu",
        (
            "Smart NVR Pipeline - Analytics Branch [CPU]",
            "Smart NVR Pipeline - Media Only Branch [CPU]",
        ),
        ("CPU", "CPU"),
    ),
    (
        "nvr_dual_gpu",
        (
            "Smart NVR Pipeline - Analytics Branch [GPU]",
            "Smart NVR Pipeline - Media Only Branch [GPU]",
        ),
        ("GPU", "GPU"),
    ),
    (
        "nvr_dual_npu",
        (
            "Smart NVR Pipeline - Analytics Branch [NPU]",
            "Smart NVR Pipeline - Media Only Branch [NPU]",
        ),
        ("NPU", "NPU"),
    ),
]
SUPPORTED_DEVICE_FILTERS = {"CPU", "GPU", "NPU"}


def _parse_device_filters() -> set[str] | None:
    raw = os.environ.get("VIPPET_DEVICE_FILTERS")
    if not raw:
        return None
    filters = {token.strip().upper() for token in raw.split(",") if token.strip()}
    if not filters:
        return None
    invalid = filters - SUPPORTED_DEVICE_FILTERS
    if invalid:
        raise AssertionError(
            "Unknown device filter(s): " + ", ".join(sorted(invalid))
        )
    return filters


def _resolve_selected_cases() -> list[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    cases = ALL_PIPELINE_CASES

    device_filters = _parse_device_filters()
    if device_filters:
        cases = [
            case
            for case in cases
            if set(device_name.upper() for device_name in case[2]).issubset(
                device_filters
            )
        ]

    return cases


SELECTED_PIPELINE_CASES = _resolve_selected_cases()
assert SELECTED_PIPELINE_CASES, "No pipeline cases selected for execution"
CASE_IDS = [case[0] for case in SELECTED_PIPELINE_CASES]
logger = logging.getLogger(__name__)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _inter_test_pause():
    yield
    time.sleep(0.5)


def _fetch_pipeline_id(session: requests.Session, pipeline_name: str) -> str:
    logger.info("Fetching pipeline id for '%s'", pipeline_name)
    response = session.get(f"{BASE_URL}/pipelines", timeout=30)
    response.raise_for_status()
    pipelines: list[dict[str, Any]] = response.json()
    logger.debug("Received %d pipelines", len(pipelines))

    matching = next((p for p in pipelines if p.get("name") == pipeline_name), None)
    assert matching is not None, (
        f"Pipeline named '{pipeline_name}' not found in /pipelines response"
    )
    pipeline_id = matching.get("id")
    assert pipeline_id, "Matching pipeline missing 'id' field"
    logger.info("Using pipeline id %s for '%s'", pipeline_id, pipeline_name)
    return str(pipeline_id)


def _start_performance_job(
    session: requests.Session,
    specs: list[dict[str, Any]],
    encoder_device_name: str,
) -> str:
    pipeline_ids = [spec.get("id") for spec in specs]
    logger.info(
        "Starting performance job for pipeline_ids=%s with encoder device %s",
        pipeline_ids,
        encoder_device_name,
    )
    payload = {
        "pipeline_performance_specs": specs,
        "video_output": {
            "enabled": True,
            "encoder_device": {"device_name": encoder_device_name, "gpu_id": 0},
        },
    }

    response = session.post(
        f"{BASE_URL}/tests/performance",
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    job_id = response.json().get("job_id")
    assert job_id, "Performance test response missing 'job_id'"
    logger.info("Performance job started: %s", job_id)
    return str(job_id)


def _get_job_status(session: requests.Session, job_id: str) -> dict[str, Any]:
    response = session.get(
        f"{BASE_URL}/jobs/tests/performance/{job_id}/status",
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _wait_for_completion(session: requests.Session, job_id: str) -> dict[str, Any]:
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    last_status: dict[str, Any] | None = None

    # First fetch must report RUNNING per test specification.
    first_status = _get_job_status(session, job_id)
    assert first_status.get("state") == "RUNNING", (
        f"Expected initial job state RUNNING, got {first_status.get('state')}"
    )
    logger.info(
        "Job %s initial state %s (elapsed=%sms)",
        job_id,
        first_status.get("state"),
        first_status.get("elapsed_time"),
    )
    last_status = first_status

    while time.time() < deadline:
        if last_status.get("state") == "COMPLETED":
            logger.info("Job %s finished with COMPLETED state", job_id)
            return last_status
        time.sleep(POLL_INTERVAL_SECONDS)
        last_status = _get_job_status(session, job_id)
        logger.info(
            "Job %s polled state=%s total_fps=%s error=%s",
            job_id,
            last_status.get("state"),
            last_status.get("total_fps"),
            last_status.get("error_message"),
        )

    pytest.fail(
        f"Job {job_id} did not reach COMPLETED within {POLL_TIMEOUT_SECONDS} seconds"
    )


@pytest.mark.parametrize(
    "case_id, pipeline_names, device_names",
    SELECTED_PIPELINE_CASES,
    ids=CASE_IDS,
)
def test_performance_job_completes_successfully(
    http_client: requests.Session,
    case_id: str,
    pipeline_names: tuple[str, ...],
    device_names: tuple[str, ...],
):
    logger.info("Running performance flow for case '%s'", case_id)
    specs = []
    assert len(pipeline_names) == len(device_names), (
        "Number of pipeline names and device names must match"
    )
    for pipeline_name, expected_device in zip(pipeline_names, device_names):
        pipeline_id = _fetch_pipeline_id(http_client, pipeline_name)
        encoder_device_name = _infer_device_from_pipeline_name(pipeline_name)
        assert (
            encoder_device_name == expected_device
        ), "Encoder device mismatch vs expected"
        specs.append({"id": pipeline_id, "streams": 3})

    job_id = _start_performance_job(http_client, specs, device_names[0])
    final_status = _wait_for_completion(http_client, job_id)

    assert final_status.get("state") == "COMPLETED", (
        f"Job {job_id} finished in unexpected state {final_status.get('state')}"
    )
    assert final_status.get("total_fps") is not None, (
        f"Job {job_id} missing total_fps in response"
    )
    assert final_status.get("per_stream_fps") > 0, (
        f"Job {job_id} missing per_stream_fps in response"
    )
    assert final_status.get("total_streams") is not None, (
        f"Job {job_id} total_streams is missing in response"
    )
    assert final_status.get("error_message") is None, (
        f"Job {job_id} returned error message: {final_status.get('error_message')}"
    )

    video_output_paths = final_status.get("video_output_paths")
    assert isinstance(video_output_paths, dict) and video_output_paths, (
        f"Job {job_id} missing video_output_paths in response"
    )
    for spec in specs:
        pipeline_id = spec["id"]
        paths = video_output_paths.get(pipeline_id)
        assert paths, f"Job {job_id} produced no video outputs for {pipeline_id}"


def _infer_device_from_pipeline_name(pipeline_name: str) -> str:
    """Extract the trailing [DEVICE] suffix and map it to encoder device name."""
    if "[" in pipeline_name and "]" in pipeline_name:
        suffix = pipeline_name.rsplit("[", 1)[1].rstrip("] ").strip().upper()
        if suffix in {"CPU", "GPU", "NPU"}:
            logger.info(
                "Derived encoder device '%s' from pipeline name '%s'",
                suffix,
                pipeline_name,
            )
            return suffix
    raise AssertionError(
        f"Unable to determine encoder device from pipeline name '{pipeline_name}'"
    )
