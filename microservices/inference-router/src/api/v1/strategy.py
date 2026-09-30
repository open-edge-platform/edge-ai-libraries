# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""v1 strategy management endpoints.

A strategy is a named rule set plus a provider selector (see
:mod:`src.rsd.strategy`). These endpoints treat each strategy as an object and
CRUD them over the on-disk ``strategy.yaml``: all operations target the
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
from src.rsd.policy import resolve_policy_file
from src.rsd.strategy import build_strategy_definition
from src.router.logging_utils import sanitize_for_log


logger = logging.getLogger(__name__)
router = APIRouter()

STRATEGY_FILE = "strategy.yaml"

# Top-level keys a strategy object may carry (besides ``name``, taken from the
# path). Persistence whitelists these so an unknown/typo key in the body — which
# ``build_strategy_definition`` silently ignores — never pollutes strategy.yaml.
_KNOWN_KEYS = ("description", "rules", "provider_selector", "sort", "require_healthy", "limit")


def _entries(document: dict[str, Any]) -> list[dict[str, Any]]:
    strategies = document.get("strategies")
    if strategies is None:
        return []
    if not isinstance(strategies, list):
        raise HTTPException(
            status_code=500,
            detail="strategy.yaml must define a 'strategies' list",
        )
    return strategies


def _find(entries: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for entry in entries:
        if isinstance(entry, dict) and entry.get("name") == name:
            return entry
    return None


def _normalize(entry: dict[str, Any]) -> dict[str, Any]:
    """Present a stored strategy in the documented shape, filling defaults.

    A stored ``strategy.yaml`` entry may omit optional fields (``description``,
    ``rules``, ``sort``, ``require_healthy``, ``limit``); responses fill them so
    the object shape is stable. ``rules`` / ``provider_selector`` are passed
    through as-is (already in ``{type, param}`` / selector form).
    """
    return {
        "name": entry.get("name"),
        "description": entry.get("description", ""),
        "rules": entry.get("rules", []),
        "provider_selector": entry.get("provider_selector", {}),
        "sort": entry.get("sort", []),
        "require_healthy": entry.get("require_healthy", False),
        "limit": entry.get("limit"),
    }


def _policies_referencing(name: str) -> list[str]:
    """Return names of policies whose ``strategies`` list contains ``name``."""
    document = read_yaml_document(resolve_policy_file())
    policies = document.get("policies")
    if policies is None:
        return []
    if not isinstance(policies, list):
        raise HTTPException(
            status_code=500,
            detail="policy.yaml must define a 'policies' list",
        )
    referencing: list[str] = []
    for policy in policies:
        if not isinstance(policy, dict):
            continue
        policy_name = policy.get("name")
        strategies = policy.get("strategies")
        if policy_name and isinstance(strategies, list) and name in strategies:
            referencing.append(policy_name)
    return referencing


@router.get("/strategies")
async def list_strategies() -> list[dict[str, Any]]:
    """List all strategies defined in the workspace ``strategy.yaml``."""
    workspace_path = workspace_rsd_path(STRATEGY_FILE)
    require_workspace_file(workspace_path, STRATEGY_FILE)
    return [_normalize(entry) for entry in _entries(read_yaml_document(workspace_path))]


@router.get("/strategies/{name}")
async def get_strategy(name: str) -> dict[str, Any]:
    """Get a single strategy by name from the workspace ``strategy.yaml``."""
    workspace_path = workspace_rsd_path(STRATEGY_FILE)
    require_workspace_file(workspace_path, STRATEGY_FILE)
    entry = _find(_entries(read_yaml_document(workspace_path)), name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")
    return _normalize(entry)


@router.post("/strategies/{name}")
async def create_or_update_strategy(
    name: str, body: dict[str, Any], http_request: Request
) -> dict[str, Any]:
    """Create or replace a strategy, persist to workspace, and apply immediately."""
    workspace_path = workspace_rsd_path(STRATEGY_FILE)
    try:
        async with http_request.app.state.config_lock:
            require_workspace_file(workspace_path, STRATEGY_FILE)

            # ``name`` comes from the path; a body ``name`` and any unknown keys
            # are dropped so only recognized fields are persisted.
            body = body or {}
            entry: dict[str, Any] = {"name": name}
            for key in _KNOWN_KEYS:
                if key in body:
                    entry[key] = body[key]

            # Validate with the same builder used at startup.
            try:
                build_strategy_definition(entry)
            except ConfigurationError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

            document = read_yaml_document(workspace_path)
            entries = _entries(document)
            if _find(entries, name) is None:
                entries = [*entries, entry]
            else:
                entries = [
                    entry if (isinstance(e, dict) and e.get("name") == name) else e
                    for e in entries
                ]
            document["strategies"] = entries

            await apply_rsd_document(http_request, workspace_path, document)
        return _normalize(entry)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to create/update strategy {sanitize_for_log(name)}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to configure strategy")


@router.delete("/strategies/{name}")
async def delete_strategy(name: str, http_request: Request) -> dict[str, Any]:
    """Delete a strategy, persist to workspace, and apply immediately."""
    workspace_path = workspace_rsd_path(STRATEGY_FILE)
    try:
        async with http_request.app.state.config_lock:
            require_workspace_file(workspace_path, STRATEGY_FILE)

            # Refuse to orphan a policy that still references this strategy.
            referencing = _policies_referencing(name)
            if referencing:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Strategy '{name}' is referenced by policies: "
                        f"{', '.join(referencing)}"
                    ),
                )

            document = read_yaml_document(workspace_path)
            entries = _entries(document)
            remaining = [
                e for e in entries if not (isinstance(e, dict) and e.get("name") == name)
            ]
            if len(remaining) == len(entries):
                raise HTTPException(
                    status_code=404, detail=f"Strategy '{name}' not found"
                )
            document["strategies"] = remaining

            await apply_rsd_document(http_request, workspace_path, document)
        return {"status": "success", "message": f"Strategy '{name}' deleted"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to delete strategy {sanitize_for_log(name)}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to delete strategy")
