# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""v1 decision-policy management endpoints.

A policy is a named, ordered list of strategies plus a combine ``criterion``
(see :mod:`src.rsd.policy`). These endpoints treat each policy as an object and
CRUD them over the on-disk ``policy.yaml``: all operations target the
``<workspace>`` copy, which must already exist, and writes are applied
immediately by rebuilding the router's DecisionEngine (see
:mod:`src.api.v1._rsd_runtime`).
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from src.api.v1._rsd_runtime import (
    apply_rsd_document,
    read_yaml_document,
    require_workspace_file,
    workspace_rsd_path,
)
from src.exceptions import ConfigurationError
from src.rsd.policy import build_decision_policy
from src.rsd.strategy import load_strategy_definitions, resolve_strategy_file
from src.router.logging_utils import sanitize_for_log


logger = logging.getLogger(__name__)
router = APIRouter()

POLICY_FILE = "policy.yaml"


def _entries(document: dict[str, Any]) -> list[dict[str, Any]]:
    policies = document.get("policies")
    if policies is None:
        return []
    if not isinstance(policies, list):
        raise HTTPException(
            status_code=500,
            detail="policy.yaml must define a 'policies' list",
        )
    return policies


def _find(entries: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for entry in entries:
        if isinstance(entry, dict) and entry.get("name") == name:
            return entry
    return None


def _normalize(entry: dict[str, Any]) -> dict[str, Any]:
    """Present a stored policy in the documented shape, filling defaults.

    A hand-written ``policy.yaml`` entry may omit ``criterion`` (runtime default
    ``FirstMatch``); GET responses fill it so the object shape is stable.
    """
    return {
        "name": entry.get("name"),
        "criterion": entry.get("criterion", "FirstMatch"),
        "strategies": entry.get("strategies", []),
    }


def _known_strategy_names() -> set[str]:
    return set(load_strategy_definitions(resolve_strategy_file()))


@router.get("/policies")
async def list_policies() -> list[dict[str, Any]]:
    """List all policies defined in the workspace ``policy.yaml``."""
    workspace_path = workspace_rsd_path(POLICY_FILE)
    require_workspace_file(workspace_path, POLICY_FILE)
    return [_normalize(entry) for entry in _entries(read_yaml_document(workspace_path))]


@router.get("/policies/{name}")
async def get_policy(name: str) -> dict[str, Any]:
    """Get a single policy by name from the workspace ``policy.yaml``."""
    workspace_path = workspace_rsd_path(POLICY_FILE)
    require_workspace_file(workspace_path, POLICY_FILE)
    entry = _find(_entries(read_yaml_document(workspace_path)), name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Policy '{name}' not found")
    return _normalize(entry)


@router.post("/policies/{name}")
async def create_or_update_policy(
    name: str, body: dict[str, Any], http_request: Request
) -> dict[str, Any]:
    """Create or replace a policy, persist to workspace, and apply immediately."""
    workspace_path = workspace_rsd_path(POLICY_FILE)
    try:
        async with http_request.app.state.config_lock:
            require_workspace_file(workspace_path, POLICY_FILE)

            # Validate structure with the same builder used at startup.
            try:
                policy = build_decision_policy({**(body or {}), "name": name})
            except ConfigurationError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

            # Referential integrity: every referenced strategy must exist.
            try:
                known = _known_strategy_names()
            except ConfigurationError as exc:
                raise HTTPException(
                    status_code=400, detail=f"Cannot validate strategies: {exc}"
                )
            missing = [s for s in policy.strategies if s not in known]
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Policy '{name}' references unknown strategy '{missing[0]}'",
                )

            stored = {
                "name": policy.name,
                "criterion": policy.criterion,
                "strategies": list(policy.strategies),
            }
            document = read_yaml_document(workspace_path)
            entries = _entries(document)
            if _find(entries, name) is None:
                entries = [*entries, stored]
            else:
                entries = [
                    stored if (isinstance(e, dict) and e.get("name") == name) else e
                    for e in entries
                ]
            document["policies"] = entries

            await apply_rsd_document(http_request, workspace_path, document)
        return stored
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to create/update policy {sanitize_for_log(name)}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to configure policy")


@router.delete("/policies/{name}")
async def delete_policy(name: str, http_request: Request) -> dict[str, Any]:
    """Delete a policy, persist to workspace, and apply immediately."""
    workspace_path = workspace_rsd_path(POLICY_FILE)
    try:
        async with http_request.app.state.config_lock:
            require_workspace_file(workspace_path, POLICY_FILE)

            # Refuse to delete the policy the router is actively routing with.
            config = getattr(http_request.app.state, "config", None)
            active = getattr(getattr(config, "routing", None), "policy", None)
            if active == name:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Policy '{name}' is the active routing policy "
                        f"and cannot be deleted"
                    ),
                )

            document = read_yaml_document(workspace_path)
            entries = _entries(document)
            remaining = [
                e for e in entries if not (isinstance(e, dict) and e.get("name") == name)
            ]
            if len(remaining) == len(entries):
                raise HTTPException(status_code=404, detail=f"Policy '{name}' not found")
            document["policies"] = remaining

            await apply_rsd_document(http_request, workspace_path, document)
        return {"status": "success", "message": f"Policy '{name}' deleted"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to delete policy {sanitize_for_log(name)}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to delete policy")
