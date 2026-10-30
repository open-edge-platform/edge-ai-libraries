# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""The ``config`` block of a result artefact, and replay comparison.

The block records everything needed to reproduce a run from its JSON alone:
resolved settings and their sources, the config selector, code revisions,
the resolved matrix and the tests pytest selected. A replay
(``--config <result JSON or run dir>``) is compared against it with
:func:`compare_with_recording`.
"""

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

from .matrix import Matrix
from .reporters import CONFIG_SCHEMA_VERSION, REPLAY_SECTIONS
from .settings import ENV_ALLOW_MATRIX_DRIFT, PERF_DIR, ResolvedSettings

MATRIX_DRIFT_EXIT_CODE = 6

_METRICS_URL_KEYS = frozenset({"metrics.metrics_url", "metrics.capabilities_url"})


def suite_revision() -> str:
    """Git commit of the suite (performance and functional helpers),
    suffixed ``-dirty`` for uncommitted changes; ``unknown`` without git."""

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=PERF_DIR.parent,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()

    try:
        commit = git("rev-parse", "HEAD")
        dirty = git("status", "--porcelain", "--untracked-files=no", "--", ".")
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return f"{commit}-dirty" if dirty else commit


def build_config_block(
    settings: ResolvedSettings,
    *,
    matrix: Matrix | None,
    selection: Sequence[Mapping[str, Any]],
    revisions: Mapping[str, str],
    pytest_args: Sequence[str],
    filter_problem: str | None,
    replay: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "selector": {
            "value": settings.config_selector,
            "origin": settings.config_origin,
            "path": str(settings.config_path),
            "sha256": settings.config_sha256,
        },
        "values": dict(settings.values),
        "sources": dict(settings.sources),
        "revisions": dict(revisions),
        "pytest_args": list(pytest_args),
        "matrix": asdict(matrix or Matrix()),
        "selection": [dict(s) for s in selection],
        "filter_problem": filter_problem,
        "replay": dict(replay) if replay else None,
    }


def _diff(label: str, was: set[str], now: set[str]) -> list[str]:
    return [f"removed {label}: {item}" for item in sorted(was - now)] + [
        f"added {label}: {item}" for item in sorted(now - was)
    ]


def compare_with_recording(
    settings: ResolvedSettings,
    matrix: Matrix,
    revisions: Mapping[str, str],
    selection: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the ``replay`` section: what differs from the recorded run.

    Only ``matrix_drift`` (included cases, their missing models and, when
    given, the selected tests) means the replay would measure something else.
    """
    recording = settings.recording
    assert recording is not None
    was = recording.config
    was_matrix, now_matrix = was["matrix"], asdict(matrix)

    changed = {
        key for key, value in settings.values.items() if was["values"].get(key) != value
    }
    setting_changes = [
        f"{key}: {was['values'].get(key)!r} -> {settings[key]!r} "
        f"({settings.sources[key]})"
        for key in sorted(changed)
    ]
    revision_changes = [
        f"{name}: {was['revisions'].get(name, 'unrecorded')} -> {value}"
        for name, value in revisions.items()
        if was["revisions"].get(name) != value
    ]

    def cases(m: Mapping[str, Any]) -> set[str]:
        return {
            f"{c['pipeline_id']}/{c['variant_id']} ({c['device_family']})"
            for c in m["included"]
        }

    def missing(m: Mapping[str, Any]) -> set[str]:
        return {
            f"{p}: {', '.join(models)}" for p, models in m["missing_models"].items()
        }

    def selected(items: Sequence[Mapping[str, Any]]) -> set[str]:
        return {f"{s['pipeline_id']}/{s['variant_id']} x{s['streams']}" for s in items}

    def excluded(m: Mapping[str, Any]) -> set[str]:
        return {
            f"{e['pipeline_id']}/{e['variant']} ({e['reason']})" for e in m["excluded"]
        }

    matrix_drift = _diff("case", cases(was_matrix), cases(now_matrix)) + _diff(
        "missing models", missing(was_matrix), missing(now_matrix)
    )
    if selection is not None:
        matrix_drift += _diff("test", selected(was["selection"]), selected(selection))

    notes = (
        _diff("exclusion", excluded(was_matrix), excluded(now_matrix))
        + _diff(
            "pipeline id",
            set(was_matrix["known_pipeline_ids"]),
            set(now_matrix["known_pipeline_ids"]),
        )
        + _diff(
            "device family",
            set(was_matrix["available_families"]),
            set(now_matrix["available_families"]),
        )
    )
    if "vippet.base_url" in changed and not _METRICS_URL_KEYS <= changed:
        notes.append(
            "vippet.base_url changed but the metrics URLs did not, so hardware "
            "metrics still come from the recorded host. To fix: also pass "
            "--metrics-url and --capabilities-url."
        )

    return {
        "benchmark_id": recording.benchmark_id,
        "sha256": recording.sha256,
        "allow_matrix_drift": settings.allow_matrix_drift,
        "setting_changes": setting_changes,
        "revision_changes": revision_changes,
        "matrix_drift": matrix_drift,
        "notes": notes,
    }


def format_replay(replay: Mapping[str, Any]) -> str:
    lines = [f"Replay of {replay['benchmark_id']} (sha256 {replay['sha256']})"]
    for title, key in REPLAY_SECTIONS:
        items = replay[key]
        lines.append(f"{title}: {len(items) or '(none)'}")
        lines += [f"  {item}" for item in items]
    return "\n".join(lines)


def describe_matrix_drift(replay: Mapping[str, Any]) -> str:
    return (
        f"the replay would not benchmark the same cases as {replay['benchmark_id']} "
        "(see 'Matrix drift' above). To fix: restore the recorded pipelines, "
        "devices and models, or pass --allow-matrix-drift "
        f"({ENV_ALLOW_MATRIX_DRIFT}=true) to run anyway."
    )
