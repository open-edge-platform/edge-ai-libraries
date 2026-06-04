"""Shared helpers for discovering runnable pipeline/variant test cases."""

import logging
import re
from collections import defaultdict
from dataclasses import dataclass

import pytest
import requests

from .api_helpers import fetch_devices, fetch_models, fetch_pipelines

logger = logging.getLogger(__name__)

SUPPORTED_DEVICE_FAMILIES: frozenset[str] = frozenset({"CPU", "GPU", "NPU"})

# Install statuses that mark a model as runnable. Anything else
# (NOT_INSTALLED / INSTALLING / FAILED) makes the pipeline that
# references it unrunnable.
_RUNNABLE_INSTALL_STATUSES: frozenset[str] = frozenset({"installed"})


@dataclass(frozen=True)
class PipelineCase:
    """One (pipeline, variant) combination used as a parametrized test case."""

    case_id: str
    pipeline_id: str
    variant_id: str
    device_family: str
    pipeline_name: str


def _make_case_id(pipeline_name: str, variant_name: str) -> str:
    """Return a stable, pytest-safe identifier for a (pipeline, variant) pair."""
    slug = re.sub(r"[^a-z0-9]+", "_", pipeline_name.lower()).strip("_")
    return f"{slug}_{variant_name.lower()}"


def _required_families(variant_name: str) -> set[str] | None:
    """Return required device families encoded in *variant_name*.

    Expected format is an underscore-separated list of known family names,
    e.g. ``CPU``, ``GPU`` or ``GPU_NPU``.
    """
    parts = set(variant_name.split("_"))
    return parts if parts <= SUPPORTED_DEVICE_FAMILIES else None


def missing_models_per_pipeline(
    session: requests.Session,
) -> dict[str, set[str]]:
    """Return ``{pipeline_id: {display_name, ...}}`` of models the pipeline
    needs but that are **not** installed on the current system.

    Uses the reverse index exposed by ``GET /models`` through
    ``used_by_pipelines`` (populated by
    :meth:`PipelineManager.get_model_display_names_used_by_pipelines`).
    A pipeline missing from the result has all its required models
    installed and is runnable from the model standpoint.

    Granularity is per-pipeline (not per-variant) because
    ``used_by_pipelines`` is built from each variant's inference nodes
    aggregated under the parent pipeline id. In practice every variant
    of the same pipeline references the same model display names (only
    the ``device`` property differs), so this is the right granularity.
    """
    result: dict[str, set[str]] = defaultdict(set)
    for model in fetch_models(session):
        status = str(model.get("install_status") or "").lower()
        if status in _RUNNABLE_INSTALL_STATUSES:
            continue
        display_name = model.get("display_name") or ""
        for pipeline_id in model.get("used_by_pipelines") or []:
            result[pipeline_id].add(display_name)
    return dict(result)


def collect_pipeline_cases(session: requests.Session) -> list[PipelineCase]:
    """Discover runnable (pipeline, variant) combinations from the live API.

    Returns every variant whose required device families are advertised
    by the host. Filtering by *model installation* is intentionally not
    done here so callers that post-filter (e.g. by pipeline name) can
    decide what to do with model-unrunnable cases; use
    :func:`wrap_cases_for_pytest` to attach
    ``pytest.mark.skip`` reasons after filtering.
    """
    available_families: set[str] = {
        device.get("device_family", "").upper()
        for device in fetch_devices(session)
        if device.get("device_family")
    } & SUPPORTED_DEVICE_FAMILIES

    if not available_families:
        logger.warning("No supported device families detected on this system")
        return []

    logger.info("Available device families: %s", sorted(available_families))

    cases: list[PipelineCase] = []
    for pipeline in fetch_pipelines(session):
        pipeline_id: str = pipeline.get("id", "")
        pipeline_name: str = pipeline.get("name", "")
        if not (pipeline_id and pipeline_name):
            continue
        for variant in pipeline.get("variants", []):
            variant_id: str = variant.get("id", "")
            variant_name: str = variant.get("name", "").upper()
            required = _required_families(variant_name)
            if variant_id and required and required <= available_families:
                cases.append(
                    PipelineCase(
                        case_id=_make_case_id(pipeline_name, variant_name),
                        pipeline_id=pipeline_id,
                        variant_id=variant_id,
                        device_family=variant_name,
                        pipeline_name=pipeline_name,
                    )
                )

    logger.info("Collected %d pipeline/variant test case(s)", len(cases))
    return cases


def wrap_cases_for_pytest(
    cases: list[PipelineCase],
    missing_models_by_pipeline: dict[str, set[str]],
) -> tuple[list[PipelineCase | object], list[str]]:
    """Return ``(params, ids)`` ready for ``pytest.mark.parametrize``.

    Pipeline cases whose required models are not installed are wrapped
    in ``pytest.param(..., marks=pytest.mark.skip(reason=...))`` so the
    pytest report shows an explicit ``SKIPPED`` with the missing model
    names. Other cases are passed through unchanged.
    """
    params: list[PipelineCase | object] = []
    ids: list[str] = []
    for case in cases:
        missing = missing_models_by_pipeline.get(case.pipeline_id)
        if missing:
            reason = (
                f"Pipeline {case.pipeline_name!r} requires model(s) that are "
                f"not installed: {sorted(missing)}. Install them through "
                f"POST /models/download (or the UI Models page) to enable "
                f"this case."
            )
            params.append(pytest.param(case, marks=pytest.mark.skip(reason=reason)))
        else:
            params.append(case)
        ids.append(case.case_id)
    return params, ids


def discover_pipeline_cases_for_pytest(
    *,
    skip_reason: str | None = None,
) -> tuple[list[PipelineCase | object], list[str]]:
    """Return pytest parameter values and ids for pipeline-driven tests.

    Pipeline cases whose required models are not installed are kept in
    the parametrize list but wrapped in ``pytest.mark.skip`` with the
    list of missing model display names, so the pytest report shows an
    explicit ``SKIPPED`` instead of silently dropping the case from
    collection.

    If discovery fails or yields no runnable combinations at all,
    returns a single skipped parameter to keep collection stable and
    avoid hard failures.
    """
    reason = (
        skip_reason
        or "No pipeline/variant test cases were discovered from VIPPET API. "
        "Ensure API reachability and at least one supported device (CPU/GPU/NPU)."
    )

    try:
        with requests.Session() as session:
            session.headers.update({"Accept": "application/json"})
            cases = collect_pipeline_cases(session)
            missing = missing_models_by_pipeline = missing_models_per_pipeline(session)
            if missing:
                logger.info(
                    "Pipelines with missing models: %s",
                    {k: sorted(v) for k, v in missing.items()},
                )
    except Exception:
        logger.exception("Failed to collect pipeline cases from VIPPET API")
        cases = []
        missing_models_by_pipeline = {}

    if not cases:
        return [pytest.param(None, marks=pytest.mark.skip(reason=reason))], ["no-cases"]

    return wrap_cases_for_pytest(cases, missing_models_by_pipeline)


def skip_if_pipeline_models_missing(
    session: requests.Session, pipeline_id: str
) -> None:
    """Skip the current test if *pipeline_id* has any non-installed model.

    Helper for tests that hard-code a pipeline id (no parametrization
    through :func:`discover_pipeline_cases_for_pytest`) but still need
    the same "model installed?" gating, e.g.
    ``test_pipeline_optimize_flow`` against ``smart-parking``.
    """
    missing = missing_models_per_pipeline(session).get(pipeline_id)
    if missing:
        pytest.skip(
            f"Pipeline {pipeline_id!r} requires model(s) that are not "
            f"installed: {sorted(missing)}. Install them through "
            f"POST /models/download (or the UI Models page) to enable "
            f"this test."
        )
