# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""v1 strategy management endpoints.

A strategy is a named rule set plus a provider selector (see
:mod:`src.rsd.engine.strategy`). These endpoints treat each strategy as an object and
CRUD them over the on-disk ``strategy.yaml``: all operations target the
``<workspace>`` copy, which must already exist, and writes are applied
immediately by rebuilding the router's DecisionEngine (see
:mod:`src.api.v1._rsd_runtime`).

A POSTed ``ModelBasedRule`` may set its classifier from prompt text, which is
packed into a hard classifier version; see :mod:`src.api.v1._model_based_strategy`.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request

from src.api.v1._classifier_info import classifier_options
from src.api.v1._model_based_strategy import (
    plan_model_based,
    prompt_info,
    rule_version,
    strip_prompt_info,
)
from src.api.v1._rsd_runtime import (
    ReconcileReport,
    apply_rsd_document,
    read_yaml_document,
    require_workspace_file,
    workspace_rsd_path,
)
from src.exceptions import ConfigurationError
from src.router.logging_utils import sanitize_for_log
from src.rsd.engine.decision import DecisionEngine
from src.rsd.engine.policy import resolve_policy_file
from src.rsd.engine.strategy import build_strategy_definition
from src.rsd.model_based.format import write_rcv
from src.rsd.model_based.registry import get_registry
from src.rsd.model_based.settings import artifacts_dir

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


def _engine(http_request: Request) -> Any:
    """The running DecisionEngine, or one built from the config (None if neither works)."""
    router_obj = getattr(http_request.app.state, "router", None)
    engine = getattr(router_obj, "decision_engine", None)
    if engine is None:
        config = getattr(http_request.app.state, "config", None)
        try:
            engine = DecisionEngine.from_config(config.routing)
        except Exception:  # noqa: BLE001 - no usable engine: nothing is active
            return None
    return engine


def _active_strategies(http_request: Request) -> set[str]:
    """Names of the strategies in the active policy (empty if unknown)."""
    return set(getattr(_engine(http_request), "strategy_names", None) or [])


def _with_prompt_info(
    entry: dict[str, Any], engine: Any, include_classifier_options: bool = False
) -> dict[str, Any]:
    """The documented strategy shape plus a ModelBasedRule's read-only ``prompt_info``."""
    response = _normalize(entry)
    name = entry.get("name")
    active = name in set(getattr(engine, "strategy_names", None) or [])
    live_rule = None
    if active:
        definition = getattr(engine, "strategy_definitions", {}).get(name)
        live_rule = next(
            (b.rule for b in getattr(definition, "rules", []) if b.name == "ModelBasedRule"),
            None,
        )
    info = prompt_info(entry, get_registry(), active, live_rule)
    if info is not None:
        response["rules"] = [
            {**rule, "prompt_info": info}
            if isinstance(rule, dict) and rule.get("type") == "ModelBasedRule"
            else rule
            for rule in response["rules"]
        ]
        if include_classifier_options:
            response["classifier_options"] = classifier_options(get_registry())
    return response


@router.get("/strategies")
async def list_strategies(http_request: Request) -> list[dict[str, Any]]:
    """List all strategies defined in the workspace ``strategy.yaml``.

    A ModelBasedRule carries a read-only ``prompt_info`` (see :func:`get_strategy`).
    """
    workspace_path = workspace_rsd_path(STRATEGY_FILE)
    require_workspace_file(workspace_path, STRATEGY_FILE)
    engine = _engine(http_request)
    return [
        _with_prompt_info(entry, engine) for entry in _entries(read_yaml_document(workspace_path))
    ]


@router.get("/strategies/{name}")
async def get_strategy(name: str, http_request: Request) -> dict[str, Any]:
    """Get a single strategy by name from the workspace ``strategy.yaml``.

    A ModelBasedRule carries its current classifier status in read-only
    ``prompt_info``. The top-level ``classifier_options`` catalog contains the
    available model/version choices and the text extracted from hard versions.
    """
    workspace_path = workspace_rsd_path(STRATEGY_FILE)
    require_workspace_file(workspace_path, STRATEGY_FILE)
    entry = _find(_entries(read_yaml_document(workspace_path)), name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")
    return _with_prompt_info(
        entry, _engine(http_request), include_classifier_options=True
    )


@router.post("/strategies/{name}")
async def create_or_update_strategy(
    name: str, body: dict[str, Any], http_request: Request
) -> dict[str, Any]:
    """Create or replace a strategy, persist to workspace, and apply immediately.

    With a ``ModelBasedRule``, its classifier version is resolved (or packed
    from ``text``) and checked first, and the response carries
    ``prompt_result`` (and ``reconcile``, the versions loaded / released by the
    switch).
    """
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
            if "rules" in entry:  # a GET result's read-only prompt_info is not stored
                entry["rules"] = strip_prompt_info(entry["rules"])

            # A ModelBasedRule version is resolved / packed and checked first;
            # a ``text`` param is rewritten to ``{model, version}`` in ``entry``.
            registry = get_registry()
            plan = plan_model_based(entry, registry, name in _active_strategies(http_request))

            # Validate with the same builder used at startup.
            try:
                build_strategy_definition(entry)
            except ConfigurationError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

            document = read_yaml_document(workspace_path)
            entries = _entries(document)
            previous = rule_version(_find(entries, name))
            response = _normalize(entry)
            if plan is not None:
                response["prompt_result"] = plan.result(previous)

            if _find(entries, name) is None:
                entries = [*entries, entry]
            else:
                entries = [
                    entry if (isinstance(e, dict) and e.get("name") == name) else e
                    for e in entries
                ]
            document["strategies"] = entries

            written = None
            if plan is not None and plan.created:
                target = artifacts_dir() / plan.model / f"{plan.version}.rcv"
                target.parent.mkdir(parents=True, exist_ok=True)
                written = write_rcv(target, plan.check.bundle)
            report = ReconcileReport()
            try:
                await apply_rsd_document(http_request, workspace_path, document)
            except BaseException:
                if written is not None:  # an unused new version is not kept
                    written.unlink(missing_ok=True)
                raise
            if plan is not None:
                response["reconcile"] = report.result()
        return response
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
