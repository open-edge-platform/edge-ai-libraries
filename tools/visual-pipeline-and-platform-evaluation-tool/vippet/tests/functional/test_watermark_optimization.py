# SPDX-License-Identifier: Apache-2.0
"""Functional tests for automatic gvawatermark handling.

These tests submit performance jobs end-to-end and check that the chosen
output mode does not break execution for two complementary built-in
pipelines. They intentionally do NOT iterate over every pipeline or
every device variant: the broad coverage already lives in
``test_performance_job_flow.py``. The goal here is to exercise both
branches of :meth:`Graph.strip_watermark_if_all_sinks_are_fake`
end-to-end on real graphs that include ``gvadetect`` and ``gvaclassify``.

Pipelines used:
  * ``license-plate-recognition`` -- has a single ``gvawatermark`` and a
    single ``fakesink`` as terminal. In ``output_mode="disabled"`` the
    optimization MUST strip the watermark before the graph is launched.
    This test verifies the modified graph still runs successfully.
  * ``smart-nvr`` -- the most complex predefined pipeline. It has
    multiple ``gvawatermark`` nodes and an intermediate ``splitmuxsink``
    next to the main ``fakesink``. The strip path MUST be a no-op here.
    The test verifies the unchanged graph still runs successfully in
    ``output_mode="disabled"``.

The API does not expose the generated GStreamer command string, so the
tests can only assert end-to-end success (job state, FPS, output paths).
Together with the unit tests in
``vippet/tests/unit/managers_tests/pipeline_manager_watermark_test.py``
this confirms that the optimization neither breaks pipeline connectivity
when it fires, nor accidentally fires on graphs that need the overlay.
"""

import logging

import pytest
import requests

from helpers.api_helpers import (
    JsonDict,
    run_job_with_retry,
    start_performance_job,
    wait_for_job_completion,
)
from helpers.config import BASE_URL

logger = logging.getLogger(__name__)

# Pipeline that exercises the strip path:
#   - single gvawatermark
#   - gvadetect + gvaclassify in the chain
#   - single fakesink as terminal -> watermark is removed in disabled mode
STRIP_PIPELINE_ID: str = "license-plate-recognition"
STRIP_VARIANT_ID: str = "cpu"

# Pipeline that exercises the preservation path:
#   - multiple gvawatermark nodes (one per tee branch)
#   - intermediate splitmuxsink (non-fakesink) plus fakesink as main sink
#     -> watermark must stay even with output_mode=disabled
SMART_NVR_PIPELINE_ID: str = "smart-nvr"
SMART_NVR_VARIANT_ID: str = "cpu"

# Seconds to wait before retrying a failed job
RETRY_DELAY_SECONDS: float = 5.0


def _build_payload(
    pipeline_id: str,
    variant_id: str,
    output_mode: str,
    streams: int = 1,
) -> JsonDict:
    return {
        "pipeline_performance_specs": [
            {
                "pipeline": {
                    "source": "variant",
                    "pipeline_id": pipeline_id,
                    "variant_id": variant_id,
                },
                "streams": streams,
            }
        ],
        "execution_config": {
            "output_mode": output_mode,
        },
    }


def _attempt_job(session: requests.Session, payload: JsonDict) -> JsonDict:
    job_id = start_performance_job(session, payload)
    status_url = f"{BASE_URL}/jobs/tests/performance/{job_id}/status"
    return wait_for_job_completion(session, status_url)


@pytest.mark.full
def test_license_plate_recognition_with_output_disabled_strips_watermark(
    http_client: requests.Session,
) -> None:
    """``output_mode=disabled`` on license-plate-recognition triggers the strip path.

    The pipeline has a single ``gvawatermark`` followed by a single
    ``fakesink``, so
    :meth:`Graph.strip_watermark_if_all_sinks_are_fake` MUST remove the
    watermark and reconnect the surrounding edges. The job must still
    complete with a positive FPS, which proves the modified graph is
    still launchable.
    """
    logger.info(
        "Running %s/%s with output_mode=disabled (strip path)",
        STRIP_PIPELINE_ID,
        STRIP_VARIANT_ID,
    )
    payload = _build_payload(STRIP_PIPELINE_ID, STRIP_VARIANT_ID, "disabled", streams=1)
    final_status = run_job_with_retry(
        lambda: _attempt_job(http_client, payload),
        retry_delay_seconds=RETRY_DELAY_SECONDS,
    )

    label = f"pipeline_id={STRIP_PIPELINE_ID} variant_id={STRIP_VARIANT_ID}"
    assert final_status.get("state") == "COMPLETED", (
        f"{label} finished in unexpected state {final_status.get('state')}"
    )
    assert final_status.get("error_message") is None, (
        f"{label} returned error message: {final_status.get('error_message')}"
    )
    assert (final_status.get("per_stream_fps") or 0) > 0, (
        f"{label} per_stream_fps must be greater than zero"
    )


@pytest.mark.full
def test_license_plate_recognition_with_output_file_preserves_watermark(
    http_client: requests.Session,
) -> None:
    """``output_mode=file`` on license-plate-recognition keeps the watermark.

    With ``output_mode=file`` the main fakesink is converted to an
    OUTPUT_PLACEHOLDER and replaced by the encoder + filesink, so the
    strip path is a no-op and the overlay is preserved in the produced
    file. The job must complete and report a non-empty
    ``video_output_paths`` entry.
    """
    logger.info(
        "Running %s/%s with output_mode=file (preserve path)",
        STRIP_PIPELINE_ID,
        STRIP_VARIANT_ID,
    )
    payload = _build_payload(STRIP_PIPELINE_ID, STRIP_VARIANT_ID, "file", streams=1)
    final_status = run_job_with_retry(
        lambda: _attempt_job(http_client, payload),
        retry_delay_seconds=RETRY_DELAY_SECONDS,
    )

    label = f"pipeline_id={STRIP_PIPELINE_ID} variant_id={STRIP_VARIANT_ID}"
    assert final_status.get("state") == "COMPLETED", (
        f"{label} finished in unexpected state {final_status.get('state')}"
    )
    assert final_status.get("error_message") is None, (
        f"{label} returned error message: {final_status.get('error_message')}"
    )

    video_output_paths = final_status.get("video_output_paths")
    assert isinstance(video_output_paths, dict) and video_output_paths, (
        f"{label} 'video_output_paths' must be a non-empty dict, "
        f"got {video_output_paths!r}"
    )
    for variant_path, paths in video_output_paths.items():
        assert isinstance(paths, list) and len(paths) > 0, (
            f"{label} 'video_output_paths[{variant_path!r}]' must be a "
            f"non-empty list, got {paths!r}"
        )


@pytest.mark.full
def test_smart_nvr_with_output_disabled_preserves_watermark(
    http_client: requests.Session,
) -> None:
    """``output_mode=disabled`` on smart-nvr keeps the watermark.

    smart-nvr has an intermediate ``splitmuxsink`` next to the main
    ``fakesink``, so the strip path MUST be a no-op (the recorded file
    is itself a visible output). The job must complete with a positive
    FPS to confirm the optimization does not accidentally fire on
    NVR-style graphs.
    """
    logger.info(
        "Running %s/%s with output_mode=disabled (no-op path)",
        SMART_NVR_PIPELINE_ID,
        SMART_NVR_VARIANT_ID,
    )
    payload = _build_payload(
        SMART_NVR_PIPELINE_ID, SMART_NVR_VARIANT_ID, "disabled", streams=1
    )
    final_status = run_job_with_retry(
        lambda: _attempt_job(http_client, payload),
        retry_delay_seconds=RETRY_DELAY_SECONDS,
    )

    label = f"pipeline_id={SMART_NVR_PIPELINE_ID} variant_id={SMART_NVR_VARIANT_ID}"
    assert final_status.get("state") == "COMPLETED", (
        f"{label} finished in unexpected state {final_status.get('state')}"
    )
    assert final_status.get("error_message") is None, (
        f"{label} returned error message: {final_status.get('error_message')}"
    )
    assert (final_status.get("per_stream_fps") or 0) > 0, (
        f"{label} per_stream_fps must be greater than zero"
    )
