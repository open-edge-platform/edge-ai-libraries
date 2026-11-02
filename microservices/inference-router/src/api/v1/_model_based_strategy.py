# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""The ``ModelBasedRule`` part of a strategy POST: resolve, pack and check its version.

A strategy POST may carry one ``ModelBasedRule`` whose ``param`` names its
classifier in one of four ways:

* nothing -- the packaged default version;
* ``version`` -- an existing version (``vN`` or ``default``);
* ``text`` (+ optional ``labels`` / ``threshold`` / ``note``) -- a hard prompt:
  packed into a new hard version, or the existing version with the same content;
* ``prompt_file`` -- a multi-class txt prompt; not a version, nothing to check here.

The version is checked before anything is written: fully (L1/L2/L3 + warmup)
when the strategy is in the active policy or a new version is packed (the
backbone is loaded for packing anyway), otherwise its format, L1 and L2 (with
the tokenizer alone). strategy.yaml then stores ``{model, version}`` only.

On GET, the rule carries a read-only ``prompt_info``: what its version holds
(for a hard version, the prompt text as written) and its current ``status`` --
``ok``, ``degraded`` (serving a fallback, see ``effective`` / ``reason``) or
``unverified`` (not in the active policy, so not loaded or fully checked yet).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException

from src.exceptions import ConfigurationError
from src.rsd.engine.strategy import build_strategy_definition
from src.rsd.model_based.hard_version import (
    build_hard_bundle,
    content_hash,
    find_hard_version,
    next_version,
)
from src.rsd.model_based.registry import (
    ClassifierNotFoundError,
    ClassifierRegistry,
    ClassifierRegistryError,
    VersionCheck,
)
from src.rsd.model_based.rule import ModelBasedRule
from src.rsd.model_based.settings import (
    DEFAULT_VERSION,
    HARD_THRESHOLD,
    KNOWN_BACKBONES,
    artifacts_dir,
    default_backbone,
)

RULE_TYPE = "ModelBasedRule"


@dataclass
class PromptPlan:
    """What a strategy POST does to its ``ModelBasedRule`` version."""

    model: str
    version: str
    check: VersionCheck
    created: bool
    active: bool

    def result(self, previous: Optional[str]) -> dict[str, Any]:
        bundle = self.check.bundle
        result: dict[str, Any] = {
            "model": self.model,
            "version": bundle.version,
            "kind": bundle.kind,
            "created": self.created,
            "active": self.active,
            "previous": previous,
            "validation": {"format": "ok", **self.check.validation},
            "warmup_ms": self.check.warmup_ms,
        }
        if "content_hash" in bundle.meta:
            result["content_hash"] = bundle.meta["content_hash"]
        return result


def _model_based_rule(entry: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The strategy's ``ModelBasedRule`` entry; several are left to the strategy builder."""
    rules = entry.get("rules")
    if not isinstance(rules, list):
        return None
    found = [r for r in rules if isinstance(r, dict) and r.get("type") == RULE_TYPE]
    return found[0] if len(found) == 1 else None


def rule_version(entry: Optional[dict[str, Any]]) -> Optional[str]:
    """The version a stored strategy's ``ModelBasedRule`` uses (None: no version)."""
    rule = _model_based_rule(entry or {})
    if rule is None:
        return None
    param = rule.get("param") or {}
    if not isinstance(param, dict) or param.get("prompt_file"):
        return None
    return param.get("version") or DEFAULT_VERSION


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=f"ModelBasedRule: {message}")


def _resolve_model(param: dict[str, Any]) -> str:
    model = param.get("model")
    if model is None:
        return default_backbone()
    if model not in KNOWN_BACKBONES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown model {model!r}; expected one of {sorted(KNOWN_BACKBONES)}",
        )
    return model


def _check(registry: ClassifierRegistry, model: str, **kwargs: Any) -> VersionCheck:
    try:
        return registry.check(model, **kwargs)
    except ClassifierNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ClassifierRegistryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _labels_for_text(param: dict[str, Any], entry: dict[str, Any]) -> list[str]:
    """Categories of a ``text`` version: ``labels``, else ``provider_selector.label``.

    A version answers with category positions, so categories taken from the
    selector need its keys to be exactly ``0..N-1``.
    """
    try:
        if param.get("labels") is not None:
            return ModelBasedRule._normalize_labels(param["labels"])
        selector = build_strategy_definition(entry).provider_selector.label
        if not isinstance(selector, dict):
            raise ConfigurationError(
                "without 'labels', the categories come from provider_selector.label, "
                f"which must then map zones to provider labels; got {selector!r}."
            )
        keys = sorted(selector)
        if keys != list(range(len(keys))):
            raise ConfigurationError(
                f"without 'labels', provider_selector.label must be keyed 0..N-1 "
                f"(a version answers with category positions); got keys {keys}. "
                "Set 'labels' to name the categories in zone order."
            )
        return ModelBasedRule._normalize_labels([selector[key] for key in keys])
    except ConfigurationError as exc:
        raise _bad_request(str(exc))


def _plan_text(
    param: dict[str, Any],
    entry: dict[str, Any],
    registry: ClassifierRegistry,
    active: bool,
) -> PromptPlan:
    text = param.get("text")
    if not isinstance(text, str) or not text.strip():
        raise _bad_request("'text' must be a non-empty string.")
    if "version" in param or param.get("prompt_file"):
        raise _bad_request("'text', 'version' and 'prompt_file' are mutually exclusive.")
    note = param.get("note", "")
    if not isinstance(note, str):
        raise _bad_request("'note' must be a string.")
    model = _resolve_model(param)

    # Validate the rest of the strategy with the version still unknown.
    probe = copy.deepcopy(entry)
    _model_based_rule(probe)["param"] = {"model": model}
    try:
        build_strategy_definition(probe)
    except ConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    labels = _labels_for_text(param, probe)
    try:
        threshold = ModelBasedRule._normalize_threshold(param.get("threshold"))
    except ConfigurationError as exc:
        raise _bad_request(str(exc))

    root = artifacts_dir()
    existing = find_hard_version(model, root, content_hash(text, labels, threshold))
    if existing is not None:
        check = _check(registry, model, version=existing, load=active)
        return PromptPlan(model, existing, check, created=False, active=active)

    try:
        runtime = registry.runtime(model)
    except ClassifierRegistryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    version = next_version(model, root)
    try:
        bundle = build_hard_bundle(
            runtime,
            model=model,
            version=version,
            text=text,
            labels=labels,
            threshold=threshold,
            note=note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Cannot pack {model}/{version}: {exc}")
    check = _check(registry, model, bundle=bundle, load=True)
    return PromptPlan(model, version, check, created=True, active=active)


def plan_model_based(
    entry: dict[str, Any], registry: ClassifierRegistry, active: bool
) -> Optional[PromptPlan]:
    """Resolve the strategy's ``ModelBasedRule`` version and rewrite its ``param``.

    ``entry`` is updated in place: a ``text`` param becomes ``{model, version}``.
    Returns ``None`` when the strategy has no single ``ModelBasedRule`` or it
    uses a ``prompt_file``. Raises :class:`HTTPException` (400 / 404 / 422).
    """
    rule = _model_based_rule(entry)
    if rule is None:
        return None
    param = rule.get("param")
    if param is None:
        param = {}
    if not isinstance(param, dict):
        raise _bad_request("'param' must be a mapping.")
    if "note" in param and "text" not in param:
        raise _bad_request("'note' applies only with 'text'.")

    if "text" in param:
        plan = _plan_text(param, entry, registry, active)
        rule["param"] = {"model": plan.model, "version": plan.version}
        return plan
    if param.get("prompt_file"):
        return None
    model = _resolve_model(param)
    try:
        build_strategy_definition(entry)  # parameter errors are 400, before any check
    except ConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    version = param.get("version") or "default"
    check = _check(registry, model, version=version, load=active)
    return PromptPlan(model, version, check, created=False, active=active)


def strip_prompt_info(rules: Any) -> Any:
    """Drop the read-only ``prompt_info`` a GET added, so a GET result can be POSTed back."""
    if not isinstance(rules, list):
        return rules
    return [
        {k: v for k, v in rule.items() if k != "prompt_info"} if isinstance(rule, dict) else rule
        for rule in rules
    ]


def _status(binding: Any) -> dict[str, Any]:
    if binding is None:  # in the active policy, but not loaded (yet)
        return {"status": "unverified", "effective": None, "reason": "not loaded yet"}
    return {
        "status": "ok" if binding.status == "ready" else "degraded",
        "effective": binding.effective[1] if binding.effective else None,
        "reason": binding.reason,
    }


def prompt_info(
    entry: dict[str, Any],
    registry: ClassifierRegistry,
    active: bool,
    rule_instance: Any = None,
) -> Optional[dict[str, Any]]:
    """Read-only description of a stored strategy's ``ModelBasedRule``; never raises.

    ``rule_instance`` is the live rule of an active strategy (for a
    ``prompt_file`` rule, whose classifier is not in the registry).
    """
    rule = _model_based_rule(entry)
    if rule is None:
        return None
    param = rule.get("param") or {}
    if not isinstance(param, dict):
        return None
    if param.get("prompt_file"):
        info: dict[str, Any] = {"kind": "prompt_file"}
        if not active:
            return {**info, "status": "unverified", "effective": None, "reason": None}
        loaded = getattr(rule_instance, "classifier", None) is not None
        return {
            **info,
            "status": "ok" if loaded else "degraded",
            "effective": None,
            "reason": None if loaded else "the classifier could not be loaded; see the router log",
        }

    # The key the rule registers under (ModelBasedRule.registry_requirement).
    model = param.get("model") or default_backbone()
    version = param.get("version") or DEFAULT_VERSION
    try:
        bundle, _ = registry.read(model, version)
        info, error = {"kind": bundle.kind}, None
    except Exception as exc:  # noqa: BLE001 - describe what we can, never fail a GET
        info, error = {"kind": None}, str(exc)
    if active:
        return {**info, **_status(registry.status(model, version))}
    return {**info, "status": "unverified", "effective": None, "reason": error}


__all__ = ["PromptPlan", "plan_model_based", "prompt_info", "rule_version", "strip_prompt_info"]
