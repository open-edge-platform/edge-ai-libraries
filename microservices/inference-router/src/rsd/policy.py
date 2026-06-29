# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Decision policy definitions for ordered strategy execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from src.exceptions import ConfigurationError


POLICY_CRITERIA = {"FirstMatch", "AllMatch"}


@dataclass
class DecisionPolicy:
    """Named policy containing strategies and a provider selection criterion."""

    name: str
    strategies: List[str]
    criterion: str = "FirstMatch"


def resolve_policy_file() -> Path:
    """Return the canonical path to the decision policy YAML file."""
    return Path(__file__).with_name("policy.yaml").expanduser().resolve()


def load_decision_policies(
    policy_file: Optional[Path] = None,
) -> Dict[str, DecisionPolicy]:
    """Load named decision policies from policy.yaml."""
    policy_path = policy_file or resolve_policy_file()

    try:
        with open(policy_path) as handle:
            payload = yaml.safe_load(handle) or {}
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Policy file not found: {policy_path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Failed to parse policy YAML: {exc}") from exc
    except OSError as exc:
        raise ConfigurationError(f"Failed to read policy file: {exc}") from exc

    policies_data = payload.get("policies", [])
    if not isinstance(policies_data, list):
        raise ConfigurationError("policy.yaml must define a 'policies' list")

    policies: Dict[str, DecisionPolicy] = {}
    for policy_data in policies_data:
        policy = build_decision_policy(policy_data)
        policies[policy.name] = policy

    return policies


def build_decision_policy(policy_data: dict) -> DecisionPolicy:
    """Build a DecisionPolicy from a parsed YAML mapping."""
    if not isinstance(policy_data, dict):
        raise ConfigurationError("Each policy entry must be a mapping")

    name = policy_data.get("name")
    if not name:
        raise ConfigurationError("Policy entry must have a 'name'")

    strategies = policy_data.get("strategies")
    if not isinstance(strategies, list) or not strategies:
        raise ConfigurationError(f"Policy '{name}' must define a non-empty 'strategies' list")

    for strategy_name in strategies:
        if not isinstance(strategy_name, str) or not strategy_name:
            raise ConfigurationError(f"Policy '{name}' strategies must be non-empty strings")

    criterion = policy_data.get("criterion", "FirstMatch")
    if criterion not in POLICY_CRITERIA:
        allowed = ", ".join(sorted(POLICY_CRITERIA))
        raise ConfigurationError(
            f"Policy '{name}' has invalid criterion '{criterion}'. Allowed values are: {allowed}"
        )

    return DecisionPolicy(name=name, strategies=strategies, criterion=criterion)