# SPDX-License-Identifier: Apache-2.0
"""Functional integration tests: drive performance jobs whose input is an
artifact uploaded through ``POST /videos/upload`` or
``POST /images/upload``.

The flow mirrors the way a real user would chain the upload endpoints
with the performance test endpoint:

1. Upload an artifact (video or image archive) and capture the
   server-assigned name from the response.
2. Pick a pipeline variant matching one of the device families reported
   by ``GET /devices`` (CPU/GPU/NPU) so the test runs on whatever
   hardware happens to be available - same convention as the existing
   ``test_performance_job_flow.py``.
3. Fetch the variant's ``pipeline_graph_simple``, patch its ``source``
   node to point at the uploaded artifact, and convert it back to the
   advanced graph form expected by the performance test.
4. Submit a performance job using the inline graph and assert it
   reaches ``COMPLETED`` state with valid metrics.

These tests assume that every default model bundled with the variant is
already installed - the same assumption as ``test_performance_job_flow``.
"""

import copy
import logging
import time
from collections.abc import Generator

import pytest
import requests

from helpers.api_helpers import (
    JsonDict,
    convert_to_advanced,
    get_variant_simple_graph,
    run_job_with_retry,
    start_performance_job,
    upload_image_archive,
    upload_video,
    wait_for_job_completion,
)
from helpers.config import BASE_URL
from helpers.pipeline_case_helpers import (
    PipelineCase,
    discover_pipeline_cases_for_pytest,
)

logger = logging.getLogger(__name__)

# Pipelines whose ``source`` node only accepts a specific input kind.
# ``Simple NVR`` / ``Smart NVR`` expect RTSP-style multi-stream inputs and
# do not work with a single uploaded file - we exclude them here for
# the same reason ``test_performance_job_usb_camera`` excludes them.
_FILE_SOURCE_UNSUPPORTED: frozenset[str] = frozenset({"Simple NVR", "Smart NVR"})

# Pipelines that cannot meaningfully run with an image-set source. We
# exclude:
#   * Simple NVR / Smart NVR: multi-stream RTSP templates, not single
#     file/image-set inputs.
#   * Motion Detection: ``gvamotiondetect`` is a temporal element and
#     produces no detections on the same still frame repeated; the
#     backend can still build a runnable pipeline but the test would
#     be a tautology.
#   * Video Summarization VLM: requires a temporally-coherent video
#     stream as input and a heavyweight VLM model that is not part of
#     the default install (already skipped via the model-presence
#     fixture, but listed here for clarity).
_IMAGE_SET_UNSUPPORTED: frozenset[str] = frozenset(
    {
        "Simple NVR",
        "Smart NVR",
        "Motion Detection",
        "Video Summarization VLM",
    }
)

# Image extensions the ``/images/upload`` endpoint accepts. Mirrors the
# allow-list in ``vippet/images.py::IMAGE_EXTENSIONS`` and is used to
# parametrize the image-set test so we cover every supported image
# decoder the backend may select (jpegdec / pngdec / avdec_bmp /
# avdec_tiff).
_IMAGE_EXTENSIONS: tuple[str, ...] = (
    "jpg",
    "jpeg",
    "png",
    "bmp",
    "tif",
    "tiff",
)

# Seconds to wait before retrying a failed job, mirroring the other
# performance flow tests.
RETRY_DELAY_SECONDS: float = 5.0


PIPELINE_CASES, CASE_IDS = discover_pipeline_cases_for_pytest()


@pytest.fixture(autouse=True)
def _inter_test_pause() -> Generator[None, None, None]:
    """Small pause between tests, same as other performance flow files."""
    yield
    time.sleep(0.5)


def _patch_video_source_node(graph: JsonDict, video_filename: str) -> JsonDict:
    """Return a copy of *graph* with its ``source`` node set to the
    uploaded video filename."""
    modified = copy.deepcopy(graph)
    for node in modified.get("nodes", []):
        if node.get("type") == "source":
            node["data"]["kind"] = "video"
            node["data"]["source"] = video_filename
            logger.info("Patched source node to uploaded video: %s", video_filename)
            return modified
    pytest.fail("No 'source' node found in the simple graph")


def _patch_image_set_source_node(graph: JsonDict, set_name: str) -> JsonDict:
    """Return a copy of *graph* with its ``source`` node set to the
    uploaded image set."""
    modified = copy.deepcopy(graph)
    for node in modified.get("nodes", []):
        if node.get("type") == "source":
            node["data"]["kind"] = "image_set"
            node["data"]["source"] = set_name
            logger.info("Patched source node to uploaded image set: %s", set_name)
            return modified
    pytest.fail("No 'source' node found in the simple graph")


def _build_payload(advanced_graph: JsonDict, streams: int = 1) -> JsonDict:
    """Construct the POST /tests/performance request body using an inline
    advanced graph as the source."""
    return {
        "pipeline_performance_specs": [
            {
                "pipeline": {
                    "source": "graph",
                    "pipeline_graph": advanced_graph,
                },
                "streams": streams,
            }
        ],
        "execution_config": {
            "output_mode": "disabled",
        },
    }


def _attempt_job(session: requests.Session, payload: JsonDict) -> JsonDict:
    """Submit a performance job and wait for it to finish."""
    job_id = start_performance_job(session, payload)
    status_url = f"{BASE_URL}/jobs/tests/performance/{job_id}/status"
    return wait_for_job_completion(session, status_url)


# --------------------------------------------------------------------------- #
# Uploaded video -> performance job.
# --------------------------------------------------------------------------- #


_VIDEO_CASES = [
    case
    for case in PIPELINE_CASES
    if isinstance(case, PipelineCase)
    and case.pipeline_name not in _FILE_SOURCE_UNSUPPORTED
]


def _video_param_or_skip() -> tuple[list[PipelineCase | object], list[str]]:
    """Return parametrize values + ids for the uploaded-video test."""
    if not _VIDEO_CASES:
        return (
            [
                pytest.param(
                    None, marks=pytest.mark.skip(reason="no video-capable cases")
                )
            ],
            ["no-cases"],
        )
    return list(_VIDEO_CASES), [c.case_id for c in _VIDEO_CASES]


_VIDEO_PARAMS, _VIDEO_IDS = _video_param_or_skip()


@pytest.mark.full
@pytest.mark.parametrize("case", _VIDEO_PARAMS, ids=_VIDEO_IDS)
def test_uploaded_video_runs_in_performance_job(
    http_client: requests.Session,
    sample_video_bytes: bytes,
    upload_run_id: str,
    case: PipelineCase | None,
) -> None:
    """Upload a real mp4 then run a performance job that consumes it
    through the patched ``source`` node of every available pipeline
    variant. The job must reach ``COMPLETED`` with a positive FPS."""
    assert case is not None

    upload_filename = f"upload_{upload_run_id}_{case.case_id}.mp4"
    upload_response = upload_video(http_client, upload_filename, sample_video_bytes)
    assert upload_response.status_code == 201, upload_response.text

    simple_graph = get_variant_simple_graph(
        http_client, case.pipeline_id, case.variant_id
    )
    patched = _patch_video_source_node(simple_graph, upload_filename)
    advanced = convert_to_advanced(
        http_client, case.pipeline_id, case.variant_id, patched
    )

    final = run_job_with_retry(
        lambda: _attempt_job(http_client, _build_payload(advanced)),
        retry_delay_seconds=RETRY_DELAY_SECONDS,
    )
    label = f"pipeline_id={case.pipeline_id} variant_id={case.variant_id}"
    assert final.get("state") == "COMPLETED", (
        f"{label} finished in unexpected state {final.get('state')} "
        f"(error: {final.get('error_message')})"
    )
    assert (final.get("per_stream_fps") or 0) > 0, (
        f"{label} per_stream_fps must be greater than zero"
    )


# --------------------------------------------------------------------------- #
# Uploaded image set -> performance job.
# --------------------------------------------------------------------------- #


_IMAGE_CASES = [
    case
    for case in PIPELINE_CASES
    if isinstance(case, PipelineCase)
    and case.pipeline_name not in _IMAGE_SET_UNSUPPORTED
]


def _image_param_or_skip() -> tuple[list[object], list[str]]:
    """Return pytest parameter tuples ``(case, ext)`` and ids.

    The image-set test runs the cartesian product of every runnable
    pipeline/variant on this system × every accepted image extension,
    so a regression in the backend's image-decoder adaptation (e.g.
    ``pngdec`` not being followed by a ``videoconvert``) trips the
    test on at least one matrix cell.
    """
    if not _IMAGE_CASES:
        return (
            [
                pytest.param(
                    (None, None),
                    marks=pytest.mark.skip(
                        reason="no image-set-capable pipeline cases on this system"
                    ),
                )
            ],
            ["no-cases"],
        )
    params: list[object] = []
    ids: list[str] = []
    for case in _IMAGE_CASES:
        for ext in _IMAGE_EXTENSIONS:
            params.append((case, ext))
            ids.append(f"{case.case_id}-{ext}")
    return params, ids


_IMAGE_PARAMS, _IMAGE_IDS = _image_param_or_skip()


@pytest.mark.full
@pytest.mark.parametrize("case_and_ext", _IMAGE_PARAMS, ids=_IMAGE_IDS)
def test_uploaded_image_set_runs_in_performance_job(
    http_client: requests.Session,
    make_zip_archive,
    upload_run_id: str,
    case_and_ext: tuple[PipelineCase | None, str | None],
) -> None:
    """Upload an image archive, patch the pipeline ``source`` node to
    point at the resulting set, and assert the performance job
    completes successfully.

    Parametrized over the cartesian product of:
      * every runnable pipeline/variant (minus pipelines that make no
        sense on a still-image input - see ``_IMAGE_SET_UNSUPPORTED``);
      * every image extension the upload endpoint accepts (jpg/jpeg/
        png/bmp/tif/tiff). The backend selects a different software
        decoder per extension (jpegdec/pngdec/avdec_bmp/avdec_tiff),
        each with its own output caps; this matrix verifies the
        decoder -> DLStreamer adaptation works for every combination.
    """
    case, ext = case_and_ext
    assert case is not None and ext is not None

    archive_bytes, _ = make_zip_archive(ext=ext, count=6)
    archive_filename = f"upload_{upload_run_id}_{case.case_id}_{ext}.zip"
    upload_response = upload_image_archive(
        http_client,
        archive_filename,
        archive_bytes,
        content_type="application/zip",
    )
    assert upload_response.status_code == 201, upload_response.text
    set_name = upload_response.json()["name"]

    simple_graph = get_variant_simple_graph(
        http_client, case.pipeline_id, case.variant_id
    )
    patched = _patch_image_set_source_node(simple_graph, set_name)
    advanced = convert_to_advanced(
        http_client, case.pipeline_id, case.variant_id, patched
    )

    final = run_job_with_retry(
        lambda: _attempt_job(http_client, _build_payload(advanced)),
        retry_delay_seconds=RETRY_DELAY_SECONDS,
    )
    label = f"pipeline_id={case.pipeline_id} variant_id={case.variant_id} ext={ext}"
    assert final.get("state") == "COMPLETED", (
        f"{label} finished in unexpected state {final.get('state')} "
        f"(error: {final.get('error_message')})"
    )
