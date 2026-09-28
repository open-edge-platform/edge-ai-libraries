# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pure construction of the benchmark matrix (pipeline x variant x streams).

:func:`build_matrix` takes raw ``GET /pipelines`` / ``GET /devices`` payloads
plus the per-pipeline missing-model map and returns which cases are
included, which are excluded (with a reason), and which included pipelines
have models that are not installed. It performs no I/O so it can be used by
both the pytest ``conftest`` and the CLI ``--dry-run``.

Missing models are *reported*, not decided on here: the pytest side passes
them to ``wrap_cases_for_pytest`` which owns the skip-with-reason behaviour.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .settings import ResolvedSettings

# Mirrors helpers.pipeline_case_helpers.SUPPORTED_DEVICE_FAMILIES; kept local
# so this module stays importable without the functional-test helpers.
SUPPORTED_DEVICE_FAMILIES: frozenset[str] = frozenset({"CPU", "GPU", "NPU"})

ALL_VARIANTS = "(all)"


class ExclusionReason(StrEnum):
    PIPELINE_FILTER = "pipeline_filter"
    SKIP_PIPELINES = "skip_pipelines"
    SKIP_VARIANTS = "skip_variants"
    VARIANT_FILTER = "variant_filter"
    UNSUPPORTED_FAMILY = "unsupported_family"
    MALFORMED = "malformed"


@dataclass(frozen=True)
class MatrixCase:
    """Field-compatible with ``helpers.pipeline_case_helpers.PipelineCase``."""

    case_id: str
    pipeline_id: str
    variant_id: str
    device_family: str
    pipeline_name: str


@dataclass(frozen=True)
class Exclusion:
    pipeline_id: str
    pipeline_name: str
    variant: str
    reason: ExclusionReason
    detail: str


@dataclass(frozen=True)
class MatrixFilters:
    pipelines: str | Sequence[str] = "*"
    variants: Sequence[str] = ("cpu", "gpu", "npu")
    skip_pipelines: Sequence[str] = ()
    skip_variants: Sequence[str] = ()
    stream_counts: Sequence[int] = (1, 3)

    @classmethod
    def from_settings(cls, settings: ResolvedSettings) -> "MatrixFilters":
        return cls(
            pipelines=settings["benchmark.pipelines"],
            variants=tuple(settings["benchmark.variants"]),
            skip_pipelines=tuple(settings["benchmark.filters.skip_pipelines"]),
            skip_variants=tuple(settings["benchmark.filters.skip_variants"]),
            stream_counts=tuple(settings["benchmark.stream_counts"]),
        )


@dataclass
class Matrix:
    included: list[MatrixCase] = field(default_factory=list)
    excluded: list[Exclusion] = field(default_factory=list)
    missing_models: dict[str, list[str]] = field(default_factory=dict)
    """``{pipeline_id: [model display names]}`` for *included* pipelines only."""
    stream_counts: list[int] = field(default_factory=list)
    available_families: list[str] = field(default_factory=list)

    def rows(self) -> list[tuple[MatrixCase, int]]:
        """Return the full (case, stream_count) cross-product."""
        return [(case, s) for case in self.included for s in self.stream_counts]


def make_case_id(pipeline_name: str, variant_name: str) -> str:
    """Stable pytest-safe id; same algorithm as ``pipeline_case_helpers``."""
    slug = re.sub(r"[^a-z0-9]+", "_", pipeline_name.lower()).strip("_")
    return f"{slug}_{variant_name.lower()}"


def _available_families(devices: Iterable[Mapping[str, Any]]) -> set[str]:
    return {
        str(device.get("device_family") or "").upper() for device in devices
    } & SUPPORTED_DEVICE_FAMILIES


def build_matrix(
    pipelines: Iterable[Mapping[str, Any]],
    devices: Iterable[Mapping[str, Any]],
    missing_models: Mapping[str, Iterable[str]],
    filters: MatrixFilters,
) -> Matrix:
    """Classify every discovered (pipeline, variant) pair.

    Check order per variant: unknown family name -> ``skip_variants`` ->
    ``variants`` filter -> host availability. Pipeline-level checks
    (``pipelines`` filter, ``skip_pipelines``) run first and produce a
    single row with variant ``(all)``.
    """
    available = _available_families(devices)
    allowed_pipelines = None if filters.pipelines == "*" else set(filters.pipelines)
    skip_pipelines = {p.lower() for p in filters.skip_pipelines}
    skip_variants = {v.upper() for v in filters.skip_variants}
    allowed_families = {v.upper() for v in filters.variants}

    matrix = Matrix(
        stream_counts=list(filters.stream_counts),
        available_families=sorted(available),
    )

    for pipeline in pipelines:
        pipeline_id = str(pipeline.get("id") or "")
        pipeline_name = str(pipeline.get("name") or "")
        if not (pipeline_id and pipeline_name):
            matrix.excluded.append(
                Exclusion(
                    pipeline_id,
                    pipeline_name,
                    ALL_VARIANTS,
                    ExclusionReason.MALFORMED,
                    "pipeline has no id or name",
                )
            )
            continue

        if allowed_pipelines is not None and pipeline_id not in allowed_pipelines:
            matrix.excluded.append(
                Exclusion(
                    pipeline_id,
                    pipeline_name,
                    ALL_VARIANTS,
                    ExclusionReason.PIPELINE_FILTER,
                    "not listed in benchmark.pipelines",
                )
            )
            continue
        if pipeline_id.lower() in skip_pipelines:
            matrix.excluded.append(
                Exclusion(
                    pipeline_id,
                    pipeline_name,
                    ALL_VARIANTS,
                    ExclusionReason.SKIP_PIPELINES,
                    "listed in benchmark.filters.skip_pipelines",
                )
            )
            continue

        pipeline_included = False
        for variant in pipeline.get("variants") or []:
            variant_id = str(variant.get("id") or "")
            variant_name = str(variant.get("name") or "").upper()

            def _exclude(reason: ExclusionReason, detail: str) -> None:
                matrix.excluded.append(
                    Exclusion(
                        pipeline_id,
                        pipeline_name,
                        variant_name or "?",
                        reason,
                        detail,
                    )
                )

            if not (variant_id and variant_name):
                _exclude(ExclusionReason.MALFORMED, "variant has no id or name")
                continue

            parts = set(variant_name.split("_"))
            unknown = parts - SUPPORTED_DEVICE_FAMILIES
            if unknown:
                _exclude(
                    ExclusionReason.UNSUPPORTED_FAMILY,
                    f"unknown device family {sorted(unknown)}",
                )
                continue
            if variant_name in skip_variants:
                _exclude(
                    ExclusionReason.SKIP_VARIANTS,
                    "listed in benchmark.filters.skip_variants",
                )
                continue
            if not parts <= allowed_families:
                _exclude(
                    ExclusionReason.VARIANT_FILTER,
                    f"needs {sorted(parts - allowed_families)} not in "
                    f"benchmark.variants",
                )
                continue
            if not parts <= available:
                _exclude(
                    ExclusionReason.UNSUPPORTED_FAMILY,
                    f"host does not report {sorted(parts - available)}",
                )
                continue

            matrix.included.append(
                MatrixCase(
                    case_id=make_case_id(pipeline_name, variant_name),
                    pipeline_id=pipeline_id,
                    variant_id=variant_id,
                    device_family=variant_name,
                    pipeline_name=pipeline_name,
                )
            )
            pipeline_included = True

        missing = sorted(missing_models.get(pipeline_id) or [])
        if pipeline_included and missing:
            matrix.missing_models[pipeline_id] = missing

    return matrix
