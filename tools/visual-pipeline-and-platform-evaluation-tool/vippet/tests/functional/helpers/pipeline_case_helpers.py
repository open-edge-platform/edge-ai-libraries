"""Shared helpers for discovering runnable pipeline/variant test cases."""

import logging
import re
from dataclasses import dataclass

import pytest
import requests

from .api_helpers import fetch_devices, fetch_pipelines

logger = logging.getLogger(__name__)

SUPPORTED_DEVICE_FAMILIES: frozenset[str] = frozenset({"CPU", "GPU", "NPU"})


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


def collect_pipeline_cases(session: requests.Session) -> list[PipelineCase]:
    """Discover runnable (pipeline, variant) combinations from the live API."""
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


def discover_pipeline_cases_for_pytest(
    *,
    skip_reason: str | None = None,
) -> tuple[list[PipelineCase | object], list[str]]:
    """Return pytest parameter values and ids for pipeline-driven tests.

    If discovery fails or yields no runnable combinations, returns a single
    skipped parameter to keep collection stable and avoid hard failures.
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
    except Exception:
        logger.exception("Failed to collect pipeline cases from VIPPET API")
        cases = []

    if not cases:
        return [pytest.param(None, marks=pytest.mark.skip(reason=reason))], ["no-cases"]

    return list(cases), [case.case_id for case in cases]
