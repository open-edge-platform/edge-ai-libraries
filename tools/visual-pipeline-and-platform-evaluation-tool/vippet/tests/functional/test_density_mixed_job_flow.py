"""Functional tests for mixed-density mode of the density job flow.

Mixed-density mode is selected automatically when **exactly one** of two
pipeline specs sets the new ``streams`` field. That pipeline is pinned
to ``streams`` for every iteration; the other pipeline is incremented
by the same algorithm used by classic density.

To keep CI cost low we intentionally do NOT iterate over every
(pipeline, variant, device) combination. We pick a handful of stable
sample pipeline names and pair them; if either pipeline of a pair is
not runnable on the current host (missing models or unsupported
device), the case is skipped.
"""

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
    collect_pipeline_cases,
    missing_models_per_pipeline,
)

logger = logging.getLogger(__name__)

type JsonDict = dict[str, Any]

# Seconds to wait before retrying a failed job
RETRY_DELAY_SECONDS: float = 5.0

# Minimum acceptable FPS per stream for density tests
FLOOR_FPS: int = 30

# Fixed stream count for the pinned pipeline in mixed-density mode.
# Kept small so the benchmark does not need many iterations to converge
# even on modest CI hardware.
FIXED_STREAMS: int = 1

# Sample pipeline name pairs exercised by mixed-density mode. Two pairs
# are enough to cover the feature end-to-end without multiplying CI
# cost by the full (pipeline x variant x device) matrix.
SAMPLE_MIXED_PAIRS: list[tuple[str, str]] = [
    ("Smart NVR", "Simple NVR"),
    ("Age & Gender Recognition", "Smart NVR"),
]


@pytest.fixture(autouse=True)
def _inter_test_pause() -> Generator[None, None, None]:
    yield
    time.sleep(0.5)


def _pick_case_by_pipeline_name(
    cases: list[PipelineCase], pipeline_name: str
) -> PipelineCase | None:
    """Return the first runnable case matching *pipeline_name*, or None."""
    for case in cases:
        if case.pipeline_name == pipeline_name:
            return case
    return None


def _resolve_pair(
    session: requests.Session, name_fixed: str, name_grow: str
) -> tuple[PipelineCase, PipelineCase]:
    """Resolve a (fixed, grow) pipeline pair from the live API.

    Skips the calling test (with a descriptive reason) when either
    pipeline is not present, has no variant matching an available
    device, or has any required model missing.
    """
    cases = collect_pipeline_cases(session)
    missing = missing_models_per_pipeline(session)

    fixed_case = _pick_case_by_pipeline_name(cases, name_fixed)
    grow_case = _pick_case_by_pipeline_name(cases, name_grow)

    for label, case, pipeline_name in (
        ("fixed", fixed_case, name_fixed),
        ("grow", grow_case, name_grow),
    ):
        if case is None:
            pytest.skip(
                f"Mixed-density {label} pipeline {pipeline_name!r} has no "
                f"runnable variant on this host."
            )
        case_missing = missing.get(case.pipeline_id)
        if case_missing:
            pytest.skip(
                f"Mixed-density {label} pipeline {pipeline_name!r} requires "
                f"model(s) that are not installed: {sorted(case_missing)}."
            )

    assert fixed_case is not None and grow_case is not None
    return fixed_case, grow_case


def _build_mixed_density_payload(
    fixed_case: PipelineCase,
    grow_case: PipelineCase,
    *,
    fixed_streams: int = FIXED_STREAMS,
) -> JsonDict:
    """Construct a POST /tests/density request body for mixed mode.

    The first spec pins ``streams=fixed_streams`` and therefore selects
    mixed-density mode; the second spec leaves ``streams`` unset and is
    the pipeline incremented by the benchmark search.
    """
    return {
        "fps_floor": FLOOR_FPS,
        "pipeline_density_specs": [
            {
                "pipeline": {
                    "source": "variant",
                    "pipeline_id": fixed_case.pipeline_id,
                    "variant_id": fixed_case.variant_id,
                },
                "streams": fixed_streams,
            },
            {
                "pipeline": {
                    "source": "variant",
                    "pipeline_id": grow_case.pipeline_id,
                    "variant_id": grow_case.variant_id,
                },
            },
        ],
        "execution_config": {
            "max_runtime": "20",
            "output_mode": "disabled",
        },
    }


def _attempt_density_job(session: requests.Session, payload: JsonDict) -> JsonDict:
    """Submit a density job and wait for it to finish."""
    job_id = start_density_job(session, payload)
    status_url = f"{BASE_URL}/jobs/tests/density/{job_id}/status"
    return wait_for_job_completion(session, status_url)


# --------------------------------------------------------------------------- #
# Happy-path: a real mixed-density job runs end-to-end.
# --------------------------------------------------------------------------- #


@pytest.mark.full
@pytest.mark.parametrize(
    "name_fixed,name_grow",
    SAMPLE_MIXED_PAIRS,
    ids=[f"{a}__{b}".replace(" ", "_") for a, b in SAMPLE_MIXED_PAIRS],
)
def test_mixed_density_job_completes_successfully(
    http_client: requests.Session,
    name_fixed: str,
    name_grow: str,
) -> None:
    """Run a mixed-density job for a small sample of pipeline pairs.

    The test asserts the job reaches COMPLETED state and that the result
    reflects mixed mode: the pinned pipeline keeps exactly
    ``FIXED_STREAMS`` streams while the incremented pipeline ends with
    at least one stream.
    """
    fixed_case, grow_case = _resolve_pair(http_client, name_fixed, name_grow)
    logger.info(
        "Mixed-density pair: fixed=%r (variant=%s, streams=%d), grow=%r (variant=%s)",
        fixed_case.pipeline_name,
        fixed_case.device_family,
        FIXED_STREAMS,
        grow_case.pipeline_name,
        grow_case.device_family,
    )

    payload = _build_mixed_density_payload(fixed_case, grow_case)
    final_status = run_job_with_retry(
        lambda: _attempt_density_job(http_client, payload),
        retry_delay_seconds=RETRY_DELAY_SECONDS,
    )

    label = (
        f"fixed={fixed_case.pipeline_id} grow={grow_case.pipeline_id} "
        f"variants=({fixed_case.variant_id},{grow_case.variant_id})"
    )
    assert final_status.get("state") == "COMPLETED", (
        f"{label} finished in unexpected state {final_status.get('state')!r} "
        f"(error: {final_status.get('error_message')!r})"
    )
    assert (final_status.get("per_stream_fps") or 0) > 0, (
        f"{label} per_stream_fps must be greater than zero"
    )
    assert final_status.get("error_message") is None, (
        f"{label} returned error message: {final_status.get('error_message')}"
    )

    # The status payload exposes the per-pipeline allocation chosen by
    # the benchmark. The pinned pipeline must keep FIXED_STREAMS on
    # every iteration, so the result must report exactly that count.
    streams_per_pipeline = final_status.get("streams_per_pipeline") or []
    assert len(streams_per_pipeline) == 2, (
        f"{label} expected 2 entries in streams_per_pipeline, got {streams_per_pipeline!r}"
    )

    fixed_pipeline_id = (
        f"/pipelines/{fixed_case.pipeline_id}/variants/{fixed_case.variant_id}"
    )
    grow_pipeline_id = (
        f"/pipelines/{grow_case.pipeline_id}/variants/{grow_case.variant_id}"
    )

    by_id = {entry.get("id"): entry for entry in streams_per_pipeline}
    assert fixed_pipeline_id in by_id, (
        f"{label} fixed pipeline {fixed_pipeline_id!r} missing from result: {by_id!r}"
    )
    assert grow_pipeline_id in by_id, (
        f"{label} grow pipeline {grow_pipeline_id!r} missing from result: {by_id!r}"
    )

    assert by_id[fixed_pipeline_id].get("streams") == FIXED_STREAMS, (
        f"{label} fixed pipeline must keep streams={FIXED_STREAMS}, "
        f"got {by_id[fixed_pipeline_id].get('streams')!r}"
    )
    assert (by_id[grow_pipeline_id].get("streams") or 0) >= 1, (
        f"{label} incremented pipeline must end with at least 1 stream, "
        f"got {by_id[grow_pipeline_id].get('streams')!r}"
    )

    # Total stream count reported by the status must match the sum of
    # per-pipeline counts.
    expected_total = by_id[fixed_pipeline_id].get("streams") + by_id[
        grow_pipeline_id
    ].get("streams")
    assert final_status.get("total_streams") == expected_total, (
        f"{label} total_streams={final_status.get('total_streams')!r} "
        f"does not match sum of per-pipeline counts ({expected_total})"
    )


# --------------------------------------------------------------------------- #
# Smoke: API-level validation errors for mixed-density requests.
# These hit the route without spinning up a job, so they are cheap and
# do not depend on any real pipeline being runnable.
# --------------------------------------------------------------------------- #


def _variant_pipeline(pid: str, vid: str) -> JsonDict:
    return {"source": "variant", "pipeline_id": pid, "variant_id": vid}


@pytest.mark.smoke
def test_mixed_density_one_spec_returns_400(http_client: requests.Session) -> None:
    """A single spec with ``streams`` set is invalid for mixed mode."""
    payload = {
        "fps_floor": 30,
        "pipeline_density_specs": [
            {"pipeline": _variant_pipeline("pid-a", "vid-a"), "streams": 2},
        ],
        "execution_config": {"max_runtime": "20", "output_mode": "disabled"},
    }
    response = http_client.post(f"{BASE_URL}/tests/density", json=payload, timeout=30)

    assert response.status_code == 400, (
        f"Expected 400 for mixed-density with one spec, "
        f"got {response.status_code}, body={response.text}"
    )
    assert "exactly two" in response.json().get("message", ""), response.text


@pytest.mark.smoke
def test_mixed_density_three_specs_returns_400(http_client: requests.Session) -> None:
    """Three specs (with one ``streams`` set) are invalid for mixed mode."""
    payload = {
        "fps_floor": 30,
        "pipeline_density_specs": [
            {"pipeline": _variant_pipeline("pid-a", "vid-a"), "streams": 2},
            {"pipeline": _variant_pipeline("pid-b", "vid-b")},
            {"pipeline": _variant_pipeline("pid-c", "vid-c")},
        ],
        "execution_config": {"max_runtime": "20", "output_mode": "disabled"},
    }
    response = http_client.post(f"{BASE_URL}/tests/density", json=payload, timeout=30)

    assert response.status_code == 400, (
        f"Expected 400 for mixed-density with three specs, "
        f"got {response.status_code}, body={response.text}"
    )
    assert "exactly two" in response.json().get("message", ""), response.text


@pytest.mark.smoke
def test_mixed_density_both_specs_with_streams_returns_400(
    http_client: requests.Session,
) -> None:
    """Both specs setting ``streams`` leaves no pipeline to increment."""
    payload = {
        "fps_floor": 30,
        "pipeline_density_specs": [
            {"pipeline": _variant_pipeline("pid-a", "vid-a"), "streams": 2},
            {"pipeline": _variant_pipeline("pid-b", "vid-b"), "streams": 3},
        ],
        "execution_config": {"max_runtime": "20", "output_mode": "disabled"},
    }
    response = http_client.post(f"{BASE_URL}/tests/density", json=payload, timeout=30)

    assert response.status_code == 400, (
        f"Expected 400 for mixed-density with both fixed, "
        f"got {response.status_code}, body={response.text}"
    )
    assert "exactly one spec" in response.json().get("message", ""), response.text
