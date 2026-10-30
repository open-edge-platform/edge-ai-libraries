# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pure construction of the benchmark matrix (pipeline x variant x streams).

:func:`build_matrix` takes raw ``GET /pipelines`` / ``GET /devices`` payloads
plus the per-pipeline missing-model map and returns which cases are
included, which are excluded (with a reason), and which included pipelines
have models that are not installed. It performs no I/O so it can be used by
both the pytest ``conftest`` and the CLI ``--dry-run``; :func:`format_matrix`
renders it as plain text for both.

Missing models are *reported*, not decided on here: the pytest side passes
them to ``wrap_cases_for_pytest`` which owns the skip-with-reason behaviour.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .settings import SPECS_BY_KEY, ResolvedSettings

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
    known_pipeline_ids: list[str] = field(default_factory=list)

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

        # Record every well-formed pipeline id before applying the
        # pipelines/skip_pipelines filters below
        matrix.known_pipeline_ids.append(pipeline_id)

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


# --------------------------------------------------------------------------- #
# Plain-text rendering (shared by the CLI --dry-run and the pytest run log)
# --------------------------------------------------------------------------- #


def format_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    cells = [list(map(str, headers))] + [[str(c) for c in row] for row in rows]
    widths = [max(len(row[i]) for row in cells) for i in range(len(headers))]
    lines = []
    for n, row in enumerate(cells):
        lines.append("  ".join(c.ljust(w) for c, w in zip(row, widths)).rstrip())
        if n == 0:
            lines.append("  ".join("-" * w for w in widths))
    return "\n".join(lines)


def format_matrix(matrix: Matrix, skip_missing_models: bool = True) -> str:
    """Render the matrix, exclusions and missing-model runs as plain text.

    ``skip_missing_models`` mirrors ``benchmark.filters.skip_missing_models``:
    when false, runs whose models are missing are scheduled anyway, so they
    are counted as runs and listed as "will run anyway" instead of skipped.
    The ``matrix`` itself is not modified.
    """
    out: list[str] = []
    families = ", ".join(matrix.available_families) or "(none)"
    out.append(f"Host device families: {families}")
    streams = ", ".join(map(str, matrix.stream_counts))

    rows = matrix.rows()
    will_run = [
        (case.pipeline_id, case.device_family, s, case.case_id + f"_x{s}")
        for case, s in rows
        if not skip_missing_models or case.pipeline_id not in matrix.missing_models
    ]
    out.append("")
    out.append(
        f"Matrix: {len(will_run)} run(s) = pipeline x variant x streams [{streams}]"
    )
    out.append(
        format_table(("pipeline", "variant", "streams", "test id"), will_run)
        if will_run
        else "  (empty)"
    )

    out.append("")
    out.append(f"Excluded: {len(matrix.excluded)} pipeline/variant(s)")
    out.append(
        format_table(
            ("pipeline", "variant", "reason", "detail"),
            [
                (
                    e.pipeline_id or e.pipeline_name or "?",
                    e.variant,
                    e.reason.value,
                    e.detail,
                )
                for e in matrix.excluded
            ],
        )
        if matrix.excluded
        else "  (none)"
    )

    missing = [
        (
            case.pipeline_id,
            case.device_family,
            s,
            ", ".join(matrix.missing_models[case.pipeline_id]),
        )
        for case, s in rows
        if case.pipeline_id in matrix.missing_models
    ]
    out.append("")
    if skip_missing_models:
        out.append(f"Skipped at run time: missing_models: {len(missing)} run(s)")
    else:
        out.append(
            f"Missing models, will run anyway: {len(missing)} run(s) "
            "(benchmark.filters.skip_missing_models is false; these runs may "
            "fail)"
        )
    out.append(
        format_table(("pipeline", "variant", "streams", "missing models"), missing)
        if missing
        else "  (none)"
    )
    return "\n".join(out)


def describe_no_cases(matrix: Matrix) -> str:
    """Explain why the matrix has nothing to run, and what to change."""
    if matrix.excluded:
        return (
            f"All {len(matrix.excluded)} discovered pipeline/variant(s) were "
            "excluded by the benchmark filters or because this host lacks the "
            "device they need, so there is nothing to benchmark (see the "
            "'Excluded' table in the matrix above). To fix: widen --pipelines "
            "/ --variants, shorten --skip-pipelines / --skip-variants, or run "
            "on a host that has the required devices."
        )
    return (
        "ViPPET returned no pipelines with variants, so there is nothing to "
        "benchmark. To fix: check that ViPPET loaded its pipeline definitions "
        "(GET /pipelines should list pipelines with variants; see the ViPPET "
        "logs)."
    )


# --------------------------------------------------------------------------- #
# Validation of user-supplied filter ids
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class UnknownFilterId:
    """A configured id that matches nothing ViPPET (or this suite) knows."""

    key: str
    """Settings key the id came from, e.g. ``benchmark.pipelines``."""
    value: str
    valid: list[str]

    @property
    def flag(self) -> str:
        return SPECS_BY_KEY[self.key].flag

    def describe(self) -> str:
        kind = "pipeline id" if self.key.endswith("pipelines") else "device family"
        valid = ", ".join(self.valid) or "(none)"
        return (
            f"{self.value!r} in {self.key} ({self.flag}) is not a known "
            f"{kind}; valid values: {valid}"
        )


def find_unknown_filter_ids(
    filters: MatrixFilters, known_pipeline_ids: Iterable[str]
) -> list[UnknownFilterId]:
    """Return every filter id that matches no known pipeline or device family.

    ``pipelines`` is matched exactly (as the matrix does); ``skip_pipelines``
    case-insensitively; variant filters against the supported families.
    """
    valid_pipelines = sorted(set(known_pipeline_ids))
    valid_pipelines_lower = {p.lower() for p in valid_pipelines}
    families = sorted(SUPPORTED_DEVICE_FAMILIES)
    issues: list[UnknownFilterId] = []

    if filters.pipelines != "*":
        requested = (
            [filters.pipelines]
            if isinstance(filters.pipelines, str)
            else list(filters.pipelines)
        )
        issues += [
            UnknownFilterId("benchmark.pipelines", pid, valid_pipelines)
            for pid in requested
            if pid not in valid_pipelines
        ]
    issues += [
        UnknownFilterId("benchmark.filters.skip_pipelines", pid, valid_pipelines)
        for pid in filters.skip_pipelines
        if pid.lower() not in valid_pipelines_lower
    ]
    issues += [
        UnknownFilterId("benchmark.filters.skip_variants", variant, families)
        for variant in filters.skip_variants
        if variant.upper() not in SUPPORTED_DEVICE_FAMILIES
    ]
    issues += [
        UnknownFilterId("benchmark.variants", variant, families)
        for variant in filters.variants
        if variant.upper() not in SUPPORTED_DEVICE_FAMILIES
    ]
    return issues


def describe_unknown_filter_ids(
    issues: Sequence[UnknownFilterId], config_path: Any
) -> str:
    """Multi-line explanation for an aborted run (``on_unknown_id: fail``)."""
    lines = [
        f"{len(issues)} benchmark filter id(s) match no pipeline or device "
        "family that ViPPET reports, so the run would not benchmark what was "
        "asked for:"
    ]
    lines += [f"  - {issue.describe()}" for issue in issues]
    lines.append(
        f"To fix: correct or remove these ids in {config_path} or in the "
        "matching CLI flag, or set PERF_ON_UNKNOWN_ID=warn (--on-unknown-id "
        "warn) to skip them and run the rest."
    )
    return "\n".join(lines)
