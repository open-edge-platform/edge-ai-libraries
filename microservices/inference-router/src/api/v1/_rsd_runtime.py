# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for the policy/strategy (RSD) management endpoints.

Policies and strategies live in their own YAML files (``policy.yaml`` /
``strategy.yaml``), not in ``config.yaml``. The management APIs target the
``<workspace>`` copy, which must already exist, and never mutate the bundled
defaults under ``src/rsd``. A successful write is applied immediately by
rebuilding the running router's :class:`DecisionEngine` in place — with a file
rollback if the rebuild fails, mirroring the atomic runtime-swap used by the
provider/plugin APIs.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException, Request

from src.api.v1._config_runtime import _atomic_write_yaml
from src.config.loader import resolve_workspace_dir
from src.exceptions import ConfigurationError
from src.rsd.decision import DecisionEngine


logger = logging.getLogger(__name__)


def workspace_rsd_path(filename: str) -> Path:
    """Return the ``<workspace>/<filename>`` path that writes target."""
    return (resolve_workspace_dir() / filename).expanduser()


def require_workspace_file(path: Path, label: str) -> None:
    """Reject a mutation when the workspace file does not already exist.

    The API edits an operator's workspace copy and never creates or mutates the
    bundled defaults in the source tree, so a missing workspace file is a 400.
    """
    if not path.is_file():
        raise HTTPException(
            status_code=400,
            detail=(
                f"Workspace {label} not found: {path}. "
                f"Create it before editing via the API."
            ),
        )


def read_yaml_document(path: Path) -> dict[str, Any]:
    """Parse a YAML file into a mapping; ``{}`` when absent.

    Raises 500 on unreadable / malformed YAML or a non-mapping top level, so
    callers surface a corrupt file rather than silently treating it as empty.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except FileNotFoundError:
        return {}
    except (OSError, yaml.YAMLError) as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read {path.name}: {exc}")
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail=f"{path.name} must be a mapping")
    return data


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write raw bytes crash-safely (temp file + atomic rename).

    Used to restore a file's previous contents on rollback so a concurrent
    lock-free reader (GET/list) can never observe a half-written file.
    """
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("wb") as handle:
        handle.write(data)
    os.replace(tmp_path, path)


def rebuild_decision_engine(http_request: Request) -> None:
    """Rebuild the running router's DecisionEngine from the on-disk RSD files.

    ``DecisionEngine.from_config`` re-reads the resolved ``policy.yaml`` /
    ``strategy.yaml`` on construction, so a fresh instance reflects the latest
    file contents. The new engine is only swapped in after it builds cleanly;
    if construction raises, the current engine is left untouched.
    """
    router = getattr(http_request.app.state, "router", None)
    config = getattr(http_request.app.state, "config", None)
    if router is None or config is None:
        raise HTTPException(status_code=503, detail="Router not initialized")
    engine = DecisionEngine.from_config(config.routing)
    router.decision_engine = engine


async def apply_rsd_document(
    http_request: Request,
    workspace_path: Path,
    document: dict[str, Any],
) -> None:
    """Persist ``document`` to ``workspace_path`` and apply it immediately.

    Writes atomically, then rebuilds the DecisionEngine. If the rebuild fails —
    e.g. the change would leave the active routing policy referencing a missing
    strategy — the previous file contents are restored and the error surfaces as
    a 400, so the mutation is all-or-nothing. The caller MUST hold
    ``app.state.config_lock`` and MUST have verified the file exists first.
    """
    old_bytes = workspace_path.read_bytes()
    _atomic_write_yaml(workspace_path, document)
    try:
        rebuild_decision_engine(http_request)
    except HTTPException:
        _atomic_write_bytes(workspace_path, old_bytes)
        raise
    except ConfigurationError as exc:
        _atomic_write_bytes(workspace_path, old_bytes)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # pragma: no cover - defensive
        _atomic_write_bytes(workspace_path, old_bytes)
        raise HTTPException(status_code=400, detail=f"Failed to apply change: {exc}")
