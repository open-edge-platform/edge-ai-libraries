# SPDX-License-Identifier: Apache-2.0
"""End-to-end functional test for uploaded (custom) models.

This module exercises the production fix in ``graph.py`` that adds a
``ModelManager`` fallback to both the model-path -> display-name and
the display-name -> model-path resolvers. Without that fix, the simple
-> advanced graph conversion silently drops uploaded models because
they are absent from the YAML-backed ``SupportedModelsManager`` registry.

Per variant the test:
1. Fetches the simple graph of the ``Age & Gender Recognition`` pipeline.
2. Patches ``gvadetect`` / ``gvaclassify`` to reference the uploaded
   copies created by the ``uploaded_model_names`` session fixture.
3. Converts the patched simple graph back to the advanced form via
   ``POST /pipelines/{id}/variants/{vid}/convert-to-advanced`` - this
   is the call that fails without the fix.
4. Runs a performance job using the resulting advanced graph and
   asserts ``COMPLETED`` with positive FPS.

Parametrized over every CPU/GPU/NPU variant the host advertises.
"""

from __future__ import annotations

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
    wait_for_job_completion,
)
from helpers.config import BASE_URL
from helpers.pipeline_case_helpers import (
    PipelineCase,
    discover_pipeline_cases_for_pytest,
)

logger = logging.getLogger(__name__)

_TARGET_PIPELINE_NAME: str = "Age & Gender Recognition"
_FACE_MODEL: str = "face-detection-retail-0004"
_AGE_GENDER_MODEL: str = "age-gender-recognition-retail-0013"

RETRY_DELAY_SECONDS: float = 5.0


PIPELINE_CASES, CASE_IDS = discover_pipeline_cases_for_pytest()

_AGE_GENDER_CASES: list[PipelineCase] = [
    case
    for case in PIPELINE_CASES
    if isinstance(case, PipelineCase) and case.pipeline_name == _TARGET_PIPELINE_NAME
]


def _age_gender_param_or_skip() -> tuple[list[PipelineCase | object], list[str]]:
    if not _AGE_GENDER_CASES:
        return (
            [
                pytest.param(
                    None,
                    marks=pytest.mark.skip(
                        reason=(
                            f"no runnable variants of {_TARGET_PIPELINE_NAME!r} "
                            "on this system"
                        )
                    ),
                )
            ],
            ["no-cases"],
        )
    return list(_AGE_GENDER_CASES), [c.case_id for c in _AGE_GENDER_CASES]


_PARAMS, _IDS = _age_gender_param_or_skip()


@pytest.fixture(autouse=True)
def _inter_test_pause() -> Generator[None, None, None]:
    """Small pause between tests, same as other performance flow files."""
    yield
    time.sleep(0.5)


def _patch_model_nodes(
    graph: JsonDict,
    *,
    face_display_name: str,
    age_gender_display_name: str,
) -> JsonDict:
    """Return a copy of *graph* with the inference nodes pointing at the
    uploaded model copies.

    The simple graph stores model references as the model's display name
    in ``node.data["model"]``. We identify nodes by element type:
      * ``gvadetect``   -> face detection model
      * ``gvaclassify`` -> age/gender classifier
    Uploaded models never carry a model-proc, so we drop any existing
    one from the patched nodes.
    """
    modified = copy.deepcopy(graph)
    patched_detect = False
    patched_classify = False
    for node in modified.get("nodes", []):
        ntype = node.get("type")
        data = node.setdefault("data", {})
        if ntype == "gvadetect":
            data["model"] = face_display_name
            data.pop("model-proc", None)
            patched_detect = True
            logger.info("Patched gvadetect.model -> %s", face_display_name)
        elif ntype == "gvaclassify":
            data["model"] = age_gender_display_name
            data.pop("model-proc", None)
            patched_classify = True
            logger.info("Patched gvaclassify.model -> %s", age_gender_display_name)
    if not patched_detect:
        pytest.fail("No 'gvadetect' node found in the simple graph")
    if not patched_classify:
        pytest.fail("No 'gvaclassify' node found in the simple graph")
    return modified


def _build_payload(advanced_graph: JsonDict, streams: int = 1) -> JsonDict:
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
    job_id = start_performance_job(session, payload)
    status_url = f"{BASE_URL}/jobs/tests/performance/{job_id}/status"
    return wait_for_job_completion(session, status_url)


# --------------------------------------------------------------------------- #
# Baseline: the catalogue (YAML) models still work for this pipeline.
# --------------------------------------------------------------------------- #


@pytest.mark.full
@pytest.mark.parametrize("case", _PARAMS, ids=_IDS)
def test_age_gender_pipeline_with_original_models(
    http_client: requests.Session,
    case: PipelineCase | None,
) -> None:
    """Sanity baseline: run the pipeline unmodified.

    If this fails the uploaded-models variant cannot be expected to
    pass either - the failure is easier to diagnose here first.
    """
    assert case is not None

    simple_graph = get_variant_simple_graph(
        http_client, case.pipeline_id, case.variant_id
    )
    advanced = convert_to_advanced(
        http_client, case.pipeline_id, case.variant_id, simple_graph
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
# The fix under test: uploaded (custom) models go through graph.py's
# ModelManager fallback and run to completion.
# --------------------------------------------------------------------------- #


@pytest.mark.full
@pytest.mark.parametrize("case", _PARAMS, ids=_IDS)
def test_age_gender_pipeline_with_uploaded_models(
    http_client: requests.Session,
    uploaded_model_names: dict[str, str],
    case: PipelineCase | None,
) -> None:
    """Run the same pipeline with both model refs swapped for uploaded
    (custom) copies.

    Without the production fix, ``convert_to_advanced`` would raise 400
    with ``ValueError("Display name '...-uploaded-...' not found")``
    because ``SupportedModelsManager`` does not know the custom names;
    the new ``ModelManager`` fallback in ``graph.py`` is what makes
    this test green.
    """
    assert case is not None

    face_name = uploaded_model_names.get(_FACE_MODEL)
    age_gender_name = uploaded_model_names.get(_AGE_GENDER_MODEL)
    if not face_name or not age_gender_name:
        pytest.skip(
            "Uploaded copies of the reference models are unavailable; "
            "this test depends on the uploaded_model_names fixture."
        )

    simple_graph = get_variant_simple_graph(
        http_client, case.pipeline_id, case.variant_id
    )
    patched = _patch_model_nodes(
        simple_graph,
        face_display_name=face_name,
        age_gender_display_name=age_gender_name,
    )
    advanced = convert_to_advanced(
        http_client, case.pipeline_id, case.variant_id, patched
    )

    final = run_job_with_retry(
        lambda: _attempt_job(http_client, _build_payload(advanced)),
        retry_delay_seconds=RETRY_DELAY_SECONDS,
    )
    label = (
        f"pipeline_id={case.pipeline_id} variant_id={case.variant_id} (uploaded models)"
    )
    assert final.get("state") == "COMPLETED", (
        f"{label} finished in unexpected state {final.get('state')} "
        f"(error: {final.get('error_message')})"
    )
    assert (final.get("per_stream_fps") or 0) > 0, (
        f"{label} per_stream_fps must be greater than zero"
    )
