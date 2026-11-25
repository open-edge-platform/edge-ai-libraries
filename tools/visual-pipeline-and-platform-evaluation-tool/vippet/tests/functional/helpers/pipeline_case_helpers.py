"""Shared helpers for discovering runnable pipeline/variant test cases."""

import logging
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
import requests

from .api_helpers import (
    fetch_default_video_recordings,
    fetch_devices,
    fetch_models,
    fetch_pipelines,
    fetch_videos,
)

logger = logging.getLogger(__name__)

SUPPORTED_DEVICE_FAMILIES: frozenset[str] = frozenset({"CPU", "GPU", "NPU"})

# Install statuses that mark a model as runnable. Anything else
# (NOT_INSTALLED / INSTALLING / FAILED) makes the pipeline that
# references it unrunnable.
_RUNNABLE_INSTALL_STATUSES: frozenset[str] = frozenset({"installed"})

# Input video name of a variant whose input node has no video selected.
NO_INPUT_VIDEO: str = ""

# Pipelines with this tag read sensor data, not videos (same rule as the UI).
_TIME_SERIES_TAG = "Time Series"

# (pipeline id, variant id)
VariantKey = tuple[str, str]


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


# --------------------------------------------------------------------------- #
# Input videos
# --------------------------------------------------------------------------- #


def _input_video_name(node: Mapping[str, Any]) -> str | None:
    """Return the video a graph node reads, ``""`` when none is selected,
    or ``None`` when the node does not read a video."""
    data = node.get("data")
    data = data if isinstance(data, Mapping) else {}
    node_type = node.get("type")
    if node_type == "source":
        if str(data.get("kind") or "").lower() != "video":
            return None
        return str(data.get("source") or data.get("location") or "").strip()
    if node_type == "filesrc":
        return str(data.get("location") or "").strip()
    return None


def input_video_names(
    pipeline: Mapping[str, Any], variant: Mapping[str, Any]
) -> list[str]:
    """Return the input videos *variant* reads, in graph order, once each.

    Same rule as the ViPPET UI Pipelines page: the ``filesrc`` and video
    ``source`` nodes of the variant's ``pipeline_graph``; absolute paths and
    Time Series pipelines are ignored. :data:`NO_INPUT_VIDEO` stands for an
    input node with no video selected.
    """
    if _TIME_SERIES_TAG in (pipeline.get("tags") or []):
        return []
    graph = variant.get("pipeline_graph")
    nodes = graph.get("nodes") if isinstance(graph, Mapping) else None
    names: list[str] = []
    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, Mapping):
            continue
        name = _input_video_name(node)
        if name is None or name.startswith("/") or name in names:
            continue
        names.append(name)
    return names


def _variants(pipeline: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    variants = pipeline.get("variants")
    if not isinstance(variants, list):
        return []
    return [v for v in variants if isinstance(v, Mapping)]


def find_missing_videos(
    pipelines: Iterable[Mapping[str, Any]], available_videos: Iterable[str]
) -> dict[VariantKey, list[str]]:
    """Return ``{(pipeline_id, variant_id): [video names]}`` of input videos
    each variant reads that are not in *available_videos* (``GET /videos``).

    Granularity is per variant: variants of one pipeline may read different
    videos. Variants that read no missing video are left out.
    """
    available = set(available_videos)
    result: dict[VariantKey, list[str]] = {}
    for pipeline in pipelines:
        pipeline_id = str(pipeline.get("id") or "")
        if not pipeline_id:
            continue
        for variant in _variants(pipeline):
            variant_id = str(variant.get("id") or "")
            missing = [
                name
                for name in input_video_names(pipeline, variant)
                if name not in available
            ]
            if variant_id and missing:
                result[(pipeline_id, variant_id)] = missing
    return result


@dataclass(frozen=True)
class MissingVideos:
    """Input videos the variants need that ViPPET does not have."""

    by_variant: dict[VariantKey, list[str]] = field(default_factory=dict)
    """``{(pipeline_id, variant_id): [video names]}``."""
    downloadable: frozenset[str] = frozenset()
    """Missing names that are sample videos ViPPET can download."""

    def get(self, pipeline_id: str, variant_id: str) -> list[str]:
        return self.by_variant.get((pipeline_id, variant_id), [])


def missing_videos_for_pipelines(
    session: requests.Session, pipelines: Sequence[Mapping[str, Any]]
) -> MissingVideos:
    """Find the missing input videos of *pipelines* (a ``GET /pipelines``).

    ``GET /videos`` is read only when a variant reads a video, and
    ``GET /videos/default-recordings`` only when one is missing, so older or
    fake ViPPET instances without these endpoints keep working.
    """
    if not any(input_video_names(p, v) for p in pipelines for v in _variants(p)):
        return MissingVideos()
    available = {
        video["filename"]
        for video in fetch_videos(session)
        if isinstance(video, dict) and isinstance(video.get("filename"), str)
    }
    by_variant = find_missing_videos(pipelines, available)
    if not by_variant:
        return MissingVideos()
    samples = {
        recording["filename"]
        for recording in fetch_default_video_recordings(session) or []
        if isinstance(recording.get("filename"), str)
    }
    names = {name for missing in by_variant.values() for name in missing}
    return MissingVideos(by_variant, frozenset(names & samples))


def missing_videos_per_variant(session: requests.Session) -> MissingVideos:
    """Like :func:`missing_videos_for_pipelines`, reading ``GET /pipelines``."""
    return missing_videos_for_pipelines(session, fetch_pipelines(session))


def _missing_videos_or_none(
    session: requests.Session, pipelines: Sequence[Mapping[str, Any]]
) -> MissingVideos:
    """Like :func:`missing_videos_for_pipelines`, but a failed video lookup
    is logged and reported as nothing missing, so it cannot hide every case
    behind one "no-cases" skip."""
    try:
        missing_videos = missing_videos_for_pipelines(session, pipelines)
    except (requests.RequestException, AssertionError) as exc:
        logger.warning(
            "Could not look up input videos (%s); no case is skipped for "
            "missing videos",
            exc,
        )
        return MissingVideos()
    if missing_videos.by_variant:
        logger.info(
            "Variants with missing input videos: %s", missing_videos.by_variant
        )
    return missing_videos


_DEFAULT_DOWNLOAD_HINT: str = (
    "Download them on the ViPPET UI Videos page (or through "
    "POST /videos/download-default) to enable this case."
)


def describe_missing_videos(
    pipeline_name: str,
    names: Iterable[str],
    downloadable: Iterable[str],
    download_hint: str = _DEFAULT_DOWNLOAD_HINT,
) -> str:
    """Explain why a case cannot run without its input videos.

    Sample videos ViPPET can download get *download_hint*; other names must
    be uploaded; :data:`NO_INPUT_VIDEO` means no video is selected at all.
    """
    names = set(names)
    can_download = set(downloadable)
    parts: list[str] = []
    if NO_INPUT_VIDEO in names:
        parts.append(
            f"Pipeline {pipeline_name!r} has no input video selected. Select "
            "one in the pipeline Input node to enable this case."
        )
    samples = sorted(n for n in names if n and n in can_download)
    others = sorted(n for n in names if n and n not in can_download)
    if samples:
        parts.append(
            f"Pipeline {pipeline_name!r} requires input video(s) that are not "
            f"downloaded: {samples}. {download_hint}"
        )
    if others:
        parts.append(
            f"Pipeline {pipeline_name!r} requires input video(s) that are not "
            f"available and are not sample videos ViPPET can download: "
            f"{others}. Upload them on the ViPPET UI Videos page to enable "
            "this case."
        )
    return " ".join(parts)


def collect_pipeline_cases(
    session: requests.Session,
    pipelines: Sequence[Mapping[str, Any]] | None = None,
) -> list[PipelineCase]:
    """Discover runnable (pipeline, variant) combinations from the live API.

    Returns every variant whose required device families are advertised
    by the host. Filtering by *model installation* is intentionally not
    done here so callers that post-filter (e.g. by pipeline name) can
    decide what to do with model-unrunnable cases; use
    :func:`wrap_cases_for_pytest` to attach
    ``pytest.mark.skip`` reasons after filtering.

    *pipelines* is a ``GET /pipelines`` response the caller already has;
    when omitted it is fetched here.
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
    if pipelines is None:
        pipelines = fetch_pipelines(session)
    for pipeline in pipelines:
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


_DEFAULT_INSTALL_HINT: str = (
    "Install them through POST /models/download (or the UI Models page) to "
    "enable this case."
)


def describe_missing_models(
    pipeline_name: str,
    names: Iterable[str],
    install_hint: str = _DEFAULT_INSTALL_HINT,
) -> str:
    """Explain why a case is skipped while its models are not installed."""
    return (
        f"Pipeline {pipeline_name!r} requires model(s) that are not installed: "
        f"{sorted(names)}. {install_hint}"
    )


def wrap_cases_for_pytest(
    cases: list[PipelineCase],
    missing_models_by_pipeline: dict[str, set[str]],
    skip_missing_models: bool = True,
    install_hint: str = _DEFAULT_INSTALL_HINT,
    missing_videos: MissingVideos | None = None,
    video_download_hint: str = _DEFAULT_DOWNLOAD_HINT,
) -> tuple[list[PipelineCase | object], list[str]]:
    """Return ``(params, ids)`` ready for ``pytest.mark.parametrize``.

    When ``skip_missing_models`` is true, cases whose required models are not
    installed are wrapped in ``pytest.param(..., marks=pytest.mark.skip(reason=...))``
    so the pytest report shows an explicit ``SKIPPED`` with the missing
    model names. When false, those cases are passed through unchanged and
    are allowed to fail at runtime. ``install_hint`` ends the skip reason and
    tells the user how to install the models (the performance suite points
    at its CLI option instead of the raw API).

    Cases whose input videos are in *missing_videos* are always skipped (a
    pipeline cannot start without its input); ``video_download_hint`` tells
    the user how to download the sample videos among them.
    """
    params: list[PipelineCase | object] = []
    ids: list[str] = []
    for case in cases:
        reasons: list[str] = []
        missing = missing_models_by_pipeline.get(case.pipeline_id)
        if missing and skip_missing_models:
            reasons.append(
                describe_missing_models(case.pipeline_name, missing, install_hint)
            )
        videos = (
            missing_videos.get(case.pipeline_id, case.variant_id)
            if missing_videos
            else []
        )
        if videos:
            assert missing_videos is not None
            reasons.append(
                describe_missing_videos(
                    case.pipeline_name,
                    videos,
                    missing_videos.downloadable,
                    video_download_hint,
                )
            )
        if reasons:
            reason = " ".join(reasons)
            params.append(pytest.param(case, marks=pytest.mark.skip(reason=reason)))
        else:
            params.append(case)
        ids.append(case.case_id)
    return params, ids


def discover_pipeline_cases_for_pytest(
    *,
    skip_reason: str | None = None,
    skip_missing_models: bool = True,
    skip_missing_videos: bool = True,
) -> tuple[list[PipelineCase | object], list[str]]:
    """Return pytest parameter values and ids for pipeline-driven tests.

    When ``skip_missing_models`` is true, pipeline cases whose required
    models are not installed are wrapped in ``pytest.mark.skip`` with
    the missing model display names. Set it to false to schedule them
    without a skip mark. ``skip_missing_videos`` does the same for input
    videos; set it to false for tests that replace the input video. When
    only the video lookup fails, a warning is logged and no case is skipped
    for its videos (a really missing video then fails its case visibly).

    If discovery fails or yields no runnable combinations at all,
    returns a single skipped parameter to keep collection stable and
    avoid hard failures.
    """
    reason = (
        skip_reason
        or "No pipeline/variant test cases were discovered from VIPPET API. "
        "Ensure API reachability and at least one supported device (CPU/GPU/NPU)."
    )

    missing_videos = MissingVideos()
    try:
        with requests.Session() as session:
            session.headers.update({"Accept": "application/json"})
            pipelines = fetch_pipelines(session)
            cases = collect_pipeline_cases(session, pipelines)
            missing = missing_models_by_pipeline = missing_models_per_pipeline(session)
            if missing:
                logger.info(
                    "Pipelines with missing models: %s",
                    {k: sorted(v) for k, v in missing.items()},
                )
            if skip_missing_videos:
                missing_videos = _missing_videos_or_none(session, pipelines)
    except Exception:
        logger.exception("Failed to collect pipeline cases from VIPPET API")
        cases = []
        missing_models_by_pipeline = {}

    if not cases:
        return [pytest.param(None, marks=pytest.mark.skip(reason=reason))], ["no-cases"]

    return wrap_cases_for_pytest(
        cases,
        missing_models_by_pipeline,
        skip_missing_models=skip_missing_models,
        missing_videos=missing_videos,
    )


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


def skip_if_variant_videos_missing(
    session: requests.Session, pipeline_id: str, variant_id: str
) -> None:
    """Skip the current test if the variant's input videos are missing.

    Counterpart of :func:`skip_if_pipeline_models_missing` for tests that
    hard-code a pipeline id.
    """
    missing = missing_videos_per_variant(session)
    videos = missing.get(pipeline_id, variant_id)
    if videos:
        pytest.skip(describe_missing_videos(pipeline_id, videos, missing.downloadable))
