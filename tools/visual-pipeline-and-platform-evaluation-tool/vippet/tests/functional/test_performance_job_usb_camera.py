"""Functional tests: run every available pipeline variant with a USB camera input."""

import copy
import logging
import time
from collections.abc import Generator

import pytest
import requests

from helpers.config import BASE_URL
from helpers.api_helpers import (
    JsonDict,
    convert_to_advanced,
    fetch_cameras,
    get_variant_simple_graph,
    poll_job_not_failed,
    start_performance_job,
    stop_performance_job,
    wait_for_job_completion,
)
from helpers.pipeline_case_helpers import (
    PipelineCase,
    collect_pipeline_cases,
)

logger = logging.getLogger(__name__)

CAMERA_JOB_RUNTIME_SECONDS: float = 8.0

# Seconds to wait before retrying a failed job
RETRY_DELAY_SECONDS: float = 5.0

# Pipelines that are designed for file-only input and do not support USB cameras
CAMERA_UNSUPPORTED_PIPELINES: frozenset[str] = frozenset({"Simple NVR", "Smart NVR"})


def _discover_filtered_cases(
    exclude_names: frozenset[str] | None = None,
    include_names: frozenset[str] | None = None,
    skip_reason: str | None = None,
) -> tuple[list[PipelineCase | object], list[str]]:
    """Collect pipeline cases optionally filtered by pipeline name."""
    reason = (
        skip_reason
        or "No pipeline/variant test cases were discovered from VIPPET API. "
        "Ensure API reachability and at least one supported device (CPU/GPU/NPU)."
    )
    try:
        with requests.Session() as _session:
            _session.headers.update({"Accept": "application/json"})
            cases = collect_pipeline_cases(_session)
            if exclude_names:
                cases = [c for c in cases if c.pipeline_name not in exclude_names]
            if include_names:
                cases = [c for c in cases if c.pipeline_name in include_names]
    except Exception:
        logger.exception("Failed to collect pipeline cases from VIPPET API")
        cases = []
    if not cases:
        return [pytest.param(None, marks=pytest.mark.skip(reason=reason))], ["no-cases"]
    return list(cases), [case.case_id for case in cases]


# Camera-compatible pipelines (file-only pipelines excluded)
PIPELINE_CASES, CASE_IDS = _discover_filtered_cases(
    exclude_names=CAMERA_UNSUPPORTED_PIPELINES
)

# File-only pipelines expected to fail when run with a USB camera
UNSUPPORTED_PIPELINE_CASES, UNSUPPORTED_CASE_IDS = _discover_filtered_cases(
    include_names=CAMERA_UNSUPPORTED_PIPELINES,
    skip_reason=f"No camera-unsupported pipeline cases ({' / '.join(sorted(CAMERA_UNSUPPORTED_PIPELINES))}) found on this system.",
)


# Brief pause between tests
@pytest.fixture(autouse=True)
def _inter_test_pause() -> Generator[None, None, None]:
    yield
    time.sleep(0.5)


def _fetch_first_usb_camera(session: requests.Session) -> JsonDict | None:
    """Return the first USB camera from GET /cameras, or ``None`` if none exist."""
    cameras = fetch_cameras(session)
    for camera in cameras:
        if camera.get("device_type") == "USB":
            return camera
    return None


def _patch_source_node(graph: JsonDict, camera_device_path: str) -> JsonDict:
    """Return a deep copy of *graph* with the first ``source`` node set to camera input.

    Sets ``data.kind = "camera"`` and ``data.source = <camera_device_path>`` on
    the first node whose ``type`` equals ``"source"``.
    """
    modified = copy.deepcopy(graph)
    for node in modified.get("nodes", []):
        if node.get("type") == "source":
            node["data"]["kind"] = "camera"
            node["data"]["source"] = camera_device_path
            logger.info(
                "Patched source node to camera input: device_path=%s",
                camera_device_path,
            )
            return modified
    pytest.fail(
        "No 'source' node found in the simple graph – "
        "cannot patch camera input for this pipeline variant"
    )


def _build_camera_performance_payload(advanced_graph: JsonDict) -> JsonDict:
    """Build the POST /tests/performance body for a graph-sourced pipeline."""
    return {
        "pipeline_performance_specs": [
            {
                "pipeline": {
                    "source": "graph",
                    "pipeline_graph": advanced_graph,
                },
                "streams": 1,
            }
        ],
        "execution_config": {
            "output_mode": "live_stream",
            "max_runtime": 0,
        },
    }


def _attempt_camera_job(
    session: requests.Session,
    payload: JsonDict,
) -> None:
    """Submit a camera performance job, monitor it, and stop it.

    Monitors the job for ``CAMERA_JOB_RUNTIME_SECONDS`` asserting it never
    reaches FAILED state, then stops it.  Raises ``AssertionError`` (via
    :func:`poll_job_not_failed`) if the job fails during that window.
    """
    job_id = start_performance_job(session, payload)
    status_url = f"{BASE_URL}/jobs/tests/performance/{job_id}/status"
    try:
        poll_job_not_failed(
            session,
            status_url,
            duration_seconds=CAMERA_JOB_RUNTIME_SECONDS,
        )
    finally:
        stop_performance_job(session, job_id)


@pytest.mark.full
@pytest.mark.requires_camera
@pytest.mark.parametrize("case", PIPELINE_CASES, ids=CASE_IDS)
def test_performance_job_with_usb_camera_stays_running(
    http_client: requests.Session,
    case: PipelineCase | None,
) -> None:
    """Run each camera-compatible pipeline variant with a USB camera as input.

    Pipeline variants are discovered dynamically using the same device-family
    matching logic as the regular performance tests.  For each runnable
    (pipeline, variant) pair the test:

    1. Skips if no USB camera is connected to the host.
    2. Reads the variant's simple graph.
    3. Patches the ``source`` node to use the USB camera device path.
    4. Converts the modified simple graph to an advanced graph via the API.
    5. Submits a performance test job backed by the advanced graph.
    6. Monitors the job for 8 seconds, asserting it never reaches FAILED state.
    7. Stops the job.
    """
    assert case is not None

    # find a USB camera; skip the test if none is available
    usb_camera = _fetch_first_usb_camera(http_client)
    if usb_camera is None:
        pytest.skip("No USB cameras available in current environment")

    camera_device_path: str = usb_camera["details"]["device_path"]
    logger.info(
        "Using USB camera: id=%s device_path=%s",
        usb_camera.get("device_id"),
        camera_device_path,
    )

    simple_graph = get_variant_simple_graph(
        http_client, case.pipeline_id, case.variant_id
    )

    # patch the source node to use the USB camera
    modified_simple_graph = _patch_source_node(simple_graph, camera_device_path)

    advanced_graph = convert_to_advanced(
        http_client, case.pipeline_id, case.variant_id, modified_simple_graph
    )

    # submit the performance job
    payload = _build_camera_performance_payload(advanced_graph)
    try:
        _attempt_camera_job(http_client, payload)
    except AssertionError:
        logger.warning(
            "First camera job attempt failed – retrying once after %.1fs",
            RETRY_DELAY_SECONDS,
        )
        time.sleep(RETRY_DELAY_SECONDS)
        _attempt_camera_job(http_client, payload)


@pytest.mark.full
@pytest.mark.requires_camera
@pytest.mark.parametrize("case", UNSUPPORTED_PIPELINE_CASES, ids=UNSUPPORTED_CASE_IDS)
def test_performance_job_with_usb_camera_fails_for_unsupported_pipeline(
    http_client: requests.Session,
    case: PipelineCase | None,
) -> None:
    """Verify that file-only pipelines reach FAILED state when run with a USB camera.

    Pipelines such as Simple NVR and Smart NVR are designed exclusively for
    file-based input.  Patching their source node to a USB camera device and
    submitting a performance job should result in the job reaching FAILED state.
    """
    assert case is not None

    usb_camera = _fetch_first_usb_camera(http_client)
    if usb_camera is None:
        pytest.skip("No USB cameras available in current environment")

    camera_device_path: str = usb_camera["details"]["device_path"]
    logger.info(
        "Testing camera rejection for pipeline='%s' variant=%s device_path=%s",
        case.pipeline_name,
        case.device_family,
        camera_device_path,
    )

    simple_graph = get_variant_simple_graph(
        http_client, case.pipeline_id, case.variant_id
    )
    modified_simple_graph = _patch_source_node(simple_graph, camera_device_path)
    advanced_graph = convert_to_advanced(
        http_client, case.pipeline_id, case.variant_id, modified_simple_graph
    )

    payload = _build_camera_performance_payload(advanced_graph)
    job_id = start_performance_job(http_client, payload)
    status_url = f"{BASE_URL}/jobs/tests/performance/{job_id}/status"

    final_status = wait_for_job_completion(
        http_client, status_url, assert_initial_running=False
    )
    pipeline_label = f"pipeline_id={case.pipeline_id} variant_id={case.variant_id}"
    assert final_status.get("state") == "FAILED", (
        f"{pipeline_label} expected FAILED when using USB camera input, "
        f"got state={final_status.get('state')!r}"
    )
    logger.info(
        "%s correctly reached FAILED state: error=%s",
        pipeline_label,
        final_status.get("error_message"),
    )
