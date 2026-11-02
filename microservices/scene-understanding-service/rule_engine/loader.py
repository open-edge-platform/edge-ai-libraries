# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""YAML rule loader with ${var:default} resolution."""

import re
from pathlib import Path
from typing import Any, Dict, List

import yaml


_VAR_RE = re.compile(r"^\$\{(\w+):(.+)\}$")


def load_rules(path: Path, variables: Dict[str, Any] | None = None) -> List[dict]:
    """Load rules from a YAML file, resolving ${var:default} placeholders.

    Variable resolution priority (highest to lowest):
        1. ``variables`` argument (e.g. from RULES_VARIABLES env var)
        2. ``variables:`` section inside the YAML file itself
        3. Inline default in the placeholder (``${var:default}``)

    Args:
        path: Path to rules.yaml.
        variables: External overrides (e.g. env vars or app_config).

    Returns:
        List of rule dicts with resolved condition values.
    """
    external = variables or {}

    if not path.exists():
        return []

    with open(path, "r") as f:
        data = yaml.safe_load(f)

    # Merge: YAML defaults ← external overrides
    yaml_vars = data.get("variables", {}) or {}
    merged = {**yaml_vars, **external}

    rules = data.get("rules", [])

    for rule in rules:
        for cond in rule.get("conditions", []):
            cond["value"] = _resolve_var(cond["value"], merged)
        for action in rule.get("actions", []):
            params = action.get("params", {})
            for key in params:
                params[key] = _resolve_var(params[key], merged)

    return rules


def _resolve_var(value: Any, variables: Dict[str, Any]) -> Any:
    """Resolve ${var_name:default} from variables dict."""
    if not isinstance(value, str):
        return value
    m = _VAR_RE.match(value)
    if not m:
        return value
    var_name, default = m.group(1), m.group(2)
    resolved = variables.get(var_name)
    if resolved is not None:
        return resolved
    try:
        return int(default)
    except ValueError:
        try:
            return float(default)
        except ValueError:
            return default
