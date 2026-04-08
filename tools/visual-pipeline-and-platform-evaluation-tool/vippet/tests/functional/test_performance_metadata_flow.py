"""Functional tests covering the performance job metadata (metadata_mode=file) flow.

These tests validate:
* Jobs submitted with ``metadata_mode=file`` complete successfully and include
  ``metadata_stream_urls`` in the status response.
* The metadata snapshot endpoint returns a JSON array of records.
* The metadata SSE stream endpoint responds with the correct headers.
* Error paths: unknown job, pipeline without ``gvametapublish``, density test
  with metadata enabled, and job with metadata disabled all return 404 / 400 /
  FAILED as appropriate.
"""

import logging
import time
from collections.abc import Generator

import pytest
import requests

from helpers.api_helpers import (
    JsonDict,
    run_job_with_retry,
    start_density_job,
    start_performance_job,
    wait_for_job_completion,
)
from helpers.config import BASE_URL
from helpers.pipeline_case_helpers import (
    PipelineCase,
    collect_pipeline_cases,
)

logger = logging.getLogger(__name__)

# Seconds to wait before retrying a failed job
RETRY_DELAY_SECONDS: float = 5.0

# A known pipeline/variant that does NOT contain a gvametapublish element,
# used for error-path tests that need a valid (but metadata-free) pipeline.
_PIPELINE_WITHOUT_METADATA = "smart-parking"
_VARIANT_WITHOUT_METADATA = "cpu"


def _has_gvametapublish(
    session: requests.Session, pipeline_id: str, variant_id: str
) -> bool:
    """Return True if the advanced pipeline graph for *variant_id* contains a gvametapublish node."""
    response = session.get(f"{BASE_URL}/pipelines/{pipeline_id}", timeout=30)
    if response.status_code != 200:
        return False
    for variant in response.json().get("variants", []):
        if variant.get("id") == variant_id:
            nodes = variant.get("pipeline_graph", {}).get("nodes", [])
            return any(node.get("type") == "gvametapublish" for node in nodes)
    return False


def _discover_metadata_pipeline_cases() -> tuple[
    list[PipelineCase | object], list[str]
]:
    """Discover (pipeline, variant) combinations that include a gvametapublish element."""
    reason = (
        "No pipeline/variant with a gvametapublish element was discovered from the VIPPET API. "
        "Ensure API reachability and at least one supported device (CPU/GPU/NPU)."
    )
    try:
        with requests.Session() as session:
            session.headers.update({"Accept": "application/json"})
            all_cases = collect_pipeline_cases(session)
            meta_cases = [
                case
                for case in all_cases
                if _has_gvametapublish(session, case.pipeline_id, case.variant_id)
            ]
    except Exception:
        logger.exception("Failed to collect metadata pipeline cases from VIPPET API")
        meta_cases = []

    if not meta_cases:
        return [pytest.param(None, marks=pytest.mark.skip(reason=reason))], ["no-cases"]
    return list(meta_cases), [case.case_id for case in meta_cases]


METADATA_PIPELINE_CASES, METADATA_CASE_IDS = _discover_metadata_pipeline_cases()


@pytest.fixture(autouse=True)
def _inter_test_pause() -> Generator[None, None, None]:
    yield
    time.sleep(0.5)


def _build_metadata_performance_payload(
    case: PipelineCase,
    streams: int = 1,
) -> JsonDict:
    """Construct a POST /tests/performance request body with metadata_mode=file for *case*."""
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
            "output_mode": "disabled",
            "metadata_mode": "file",
        },
    }


def _attempt_performance_job(session: requests.Session, payload: JsonDict) -> JsonDict:
    """Submit a performance job and wait for it to finish.

    Returns the final status dict regardless of outcome so the caller can
    decide whether to retry via :func:`run_job_with_retry`.
    """
    job_id = start_performance_job(session, payload)
    status_url = f"{BASE_URL}/jobs/tests/performance/{job_id}/status"
    return wait_for_job_completion(session, status_url)


@pytest.mark.full
@pytest.mark.parametrize("case", METADATA_PIPELINE_CASES, ids=METADATA_CASE_IDS)
def test_performance_metadata_file_mode_job(
    http_client: requests.Session,
    case: PipelineCase | None,
) -> None:
    """Verify end-to-end metadata_mode=file behaviour for a single job run.

    Runs a performance job with ``metadata_mode=file`` and asserts all three
    observable outcomes in one pass:

    1. Job reaches COMPLETED state with a non-empty ``metadata_stream_urls`` dict.
    2. Each metadata snapshot endpoint (snapshot URL derived by stripping ``/stream``)
       returns HTTP 200 with a non-empty JSON array of records.
    3. Each metadata SSE stream endpoint returns HTTP 200 with
       ``Content-Type: text/event-stream``.

    Only (pipeline, variant) pairs whose advanced graph contains a
    ``gvametapublish`` node are included in the parametrize set.
    """
    assert case is not None
    pipeline_label = f"pipeline_id={case.pipeline_id} variant_id={case.variant_id}"
    logger.info(
        "Running metadata file-mode test for pipeline='%s' variant=%s",
        case.pipeline_name,
        case.device_family,
    )

    payload = _build_metadata_performance_payload(case)
    final_status = run_job_with_retry(
        lambda: _attempt_performance_job(http_client, payload),
        retry_delay_seconds=RETRY_DELAY_SECONDS,
    )

    # --- 1. Job completion ---
    assert final_status.get("state") == "COMPLETED", (
        f"{pipeline_label} finished in unexpected state {final_status.get('state')!r}"
    )
    assert final_status.get("error_message") is None, (
        f"{pipeline_label} returned error message: {final_status.get('error_message')!r}"
    )

    metadata_stream_urls = final_status.get("metadata_stream_urls")
    assert isinstance(metadata_stream_urls, dict) and metadata_stream_urls, (
        f"{pipeline_label} 'metadata_stream_urls' must be a non-empty dict, "
        f"got {metadata_stream_urls!r}"
    )
    for pipeline_key, urls in metadata_stream_urls.items():
        assert isinstance(urls, list) and len(urls) > 0, (
            f"{pipeline_label} 'metadata_stream_urls[{pipeline_key!r}]' must be a "
            f"non-empty list, got {urls!r}"
        )
    logger.info(
        "%s completed with metadata_stream_urls: %s",
        pipeline_label,
        metadata_stream_urls,
    )

    # --- 2. Snapshot endpoint ---
    for pipeline_key, stream_urls in metadata_stream_urls.items():
        for file_index, stream_url in enumerate(stream_urls):
            snapshot_url = stream_url.removesuffix("/stream")
            response = http_client.get(f"{BASE_URL}{snapshot_url}", timeout=30)
            assert response.status_code == 200, (
                f"Expected 200 from metadata snapshot endpoint "
                f"(pipeline_key={pipeline_key!r}, file_index={file_index}), "
                f"got {response.status_code}: {response.text}"
            )
            records = response.json()
            assert isinstance(records, list) and len(records) > 0, (
                f"Expected a non-empty JSON array from the metadata snapshot endpoint "
                f"(pipeline_key={pipeline_key!r}, file_index={file_index}), "
                f"got {type(records).__name__}: {records!r}"
            )
            logger.info(
                "%s snapshot pipeline_key=%s file_index=%d → %d record(s)",
                pipeline_label,
                pipeline_key,
                file_index,
                len(records),
            )

    # --- 3. SSE stream headers ---
    for pipeline_key, stream_urls in metadata_stream_urls.items():
        for file_index, stream_url in enumerate(stream_urls):
            response = http_client.get(
                f"{BASE_URL}{stream_url}", stream=True, timeout=30
            )
            try:
                assert response.status_code == 200, (
                    f"Expected 200 from metadata SSE stream endpoint "
                    f"(pipeline_key={pipeline_key!r}, file_index={file_index}), "
                    f"got {response.status_code}"
                )
                content_type = response.headers.get("Content-Type", "")
                assert "text/event-stream" in content_type, (
                    f"Expected 'text/event-stream' Content-Type from SSE stream endpoint "
                    f"(pipeline_key={pipeline_key!r}, file_index={file_index}), "
                    f"got {content_type!r}"
                )
            finally:
                response.close()
            logger.info(
                "%s SSE stream pipeline_key=%s file_index=%d → 200 text/event-stream",
                pipeline_label,
                pipeline_key,
                file_index,
            )


@pytest.mark.full
def test_performance_metadata_snapshot_for_job_with_disabled_metadata_returns_404(
    http_client: requests.Session,
) -> None:
    """GET metadata snapshot for an existing job whose metadata_mode is disabled returns 404.

    After submitting a performance job with ``metadata_mode=disabled``, the
    MetadataManager has no record of that job.  The snapshot endpoint must
    respond with 404 and a message that indicates metadata is unavailable
    (rather than the "job not found" 404 message).
    """
    payload = {
        "pipeline_performance_specs": [
            {
                "pipeline": {
                    "source": "variant",
                    "pipeline_id": _PIPELINE_WITHOUT_METADATA,
                    "variant_id": _VARIANT_WITHOUT_METADATA,
                },
                "streams": 1,
            }
        ],
        "execution_config": {
            "output_mode": "disabled",
            "metadata_mode": "disabled",
            "max_runtime": "5",
        },
    }

    job_id = start_performance_job(http_client, payload)
    logger.info("Started non-metadata performance job %s", job_id)

    response = http_client.get(
        f"{BASE_URL}/jobs/tests/performance/{job_id}/metadata/some-pipeline/0",
        timeout=30,
    )

    assert response.status_code == 404, (
        f"Expected 404 for metadata snapshot of a job with metadata_mode=disabled, "
        f"got {response.status_code}: {response.text}"
    )
    message = response.json().get("message", "")
    assert "metadata" in message.lower(), (
        f"Expected 404 message to mention 'metadata', got: {message!r}"
    )
    logger.info(
        "Job %s with metadata_mode=disabled correctly returned 404: %s", job_id, message
    )


@pytest.mark.smoke
def test_metadata_snapshot_for_nonexistent_job_returns_404(
    http_client: requests.Session,
) -> None:
    """GET metadata snapshot for a completely unknown job ID returns 404."""
    response = http_client.get(
        f"{BASE_URL}/jobs/tests/performance/nonexistent-job-id/metadata/some-pipeline/0",
        timeout=30,
    )

    assert response.status_code == 404, (
        f"Expected 404 for metadata snapshot with unknown job id, "
        f"got {response.status_code}: {response.text}"
    )


@pytest.mark.smoke
def test_metadata_stream_for_nonexistent_job_returns_404(
    http_client: requests.Session,
) -> None:
    """GET metadata SSE stream for a completely unknown job ID returns 404."""
    response = http_client.get(
        f"{BASE_URL}/jobs/tests/performance/nonexistent-job-id/metadata/some-pipeline/0/stream",
        timeout=30,
    )

    assert response.status_code == 404, (
        f"Expected 404 for metadata SSE stream with unknown job id, "
        f"got {response.status_code}: {response.text}"
    )


@pytest.mark.smoke
def test_density_test_with_metadata_mode_file_fails(
    http_client: requests.Session,
) -> None:
    """Density tests do not support metadata_mode=file; the job must reach FAILED state.

    The API accepts the request (202) and creates the job, but the background
    thread rejects the configuration immediately.  The job must reach FAILED
    state with an error message that mentions ``metadata``.
    """
    payload = {
        "fps_floor": 30,
        "pipeline_density_specs": [
            {
                "pipeline": {
                    "source": "variant",
                    "pipeline_id": _PIPELINE_WITHOUT_METADATA,
                    "variant_id": _VARIANT_WITHOUT_METADATA,
                },
                "stream_rate": 100,
            }
        ],
        "execution_config": {
            "output_mode": "disabled",
            "metadata_mode": "file",
        },
    }

    job_id = start_density_job(http_client, payload)
    logger.info("Started density job (metadata_mode=file) %s", job_id)

    status_url = f"{BASE_URL}/jobs/tests/density/{job_id}/status"
    final_status = wait_for_job_completion(
        http_client, status_url, assert_initial_running=False
    )

    assert final_status.get("state") == "FAILED", (
        f"Expected density job {job_id} to reach FAILED state, "
        f"got {final_status.get('state')!r}"
    )
    details: list = final_status.get("details") or []
    assert any("metadata" in entry.lower() for entry in details), (
        f"Expected a details entry mentioning 'metadata', got: {details!r}"
    )
    logger.info("Job %s correctly reached FAILED with details: %s", job_id, details)


@pytest.mark.smoke
def test_performance_metadata_file_without_gvametapublish_fails(
    http_client: requests.Session,
) -> None:
    """A performance job with metadata_mode=file on a pipeline without gvametapublish reaches FAILED.

    The API accepts the request (202) and creates the job, but the background
    thread fails immediately when ``build_pipeline_command`` detects that the
    pipeline has no ``gvametapublish`` element.  The job must reach FAILED state
    with an error message that mentions ``gvametapublish``.
    """
    payload = {
        "pipeline_performance_specs": [
            {
                "pipeline": {
                    "source": "variant",
                    "pipeline_id": _PIPELINE_WITHOUT_METADATA,
                    "variant_id": _VARIANT_WITHOUT_METADATA,
                },
                "streams": 1,
            }
        ],
        "execution_config": {
            "output_mode": "disabled",
            "metadata_mode": "file",
        },
    }

    job_id = start_performance_job(http_client, payload)
    logger.info("Started performance job (no gvametapublish) %s", job_id)

    status_url = f"{BASE_URL}/jobs/tests/performance/{job_id}/status"
    final_status = wait_for_job_completion(
        http_client, status_url, assert_initial_running=False
    )

    assert final_status.get("state") == "FAILED", (
        f"Expected job {job_id} to reach FAILED state, "
        f"got {final_status.get('state')!r}"
    )
    error_message = final_status.get("error_message") or ""
    details: list = final_status.get("details") or []
    assert "gvametapublish" in error_message.lower() or any(
        "gvametapublish" in entry.lower() for entry in details
    ), (
        f"Expected error_message or details to mention 'gvametapublish', "
        f"got error_message={error_message!r}, details={details!r}"
    )
    logger.info(
        "Job %s correctly reached FAILED with error: %s details: %s",
        job_id,
        error_message,
        details,
    )
