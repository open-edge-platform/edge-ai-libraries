# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The ``config`` block of a result artefact.
The block records the effective configuration of a run: the config selector,
every resolved setting and where its value came from, the filters applied to
the matrix and the code revisions. Passing the result JSON (or its run
directory) as ``--config`` reuses its ``values`` as the YAML layer.
"""

import subprocess
from dataclasses import asdict
from typing import Any
from .matrix import Matrix, MatrixFilters
from .settings import PERF_DIR, ResolvedSettings


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
    vippet_version: str,
) -> dict[str, Any]:
    """Build the result's ``config`` block from the resolved settings."""
    excluded = [
        {
            "pipeline_id": e.pipeline_id,
            "variant": e.variant,
            "reason": e.reason.value,
            "detail": e.detail,
        }
        for e in (matrix.excluded if matrix else [])
    ]
    return {
        "selector": {
            "value": settings.config_selector,
            "origin": settings.config_origin,
            "path": str(settings.config_path),
        },
        "values": dict(settings.values),
        "sources": dict(settings.sources),
        "filters": {
            "applied": {
                name: list(value) if isinstance(value, tuple) else value
                for name, value in asdict(MatrixFilters.from_settings(settings)).items()
            },
            "excluded": excluded,
        },
        "revisions": {"suite": suite_revision(), "vippet": vippet_version},
    }
