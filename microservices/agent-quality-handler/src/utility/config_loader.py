# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Config loader for agent orchestration settings."""

from collections.abc import Mapping
from typing import Any

import yaml

from .runtime_config import load_runtime_settings


def load_config(path: str | None = None) -> dict[str, Any]:
    """Load agents.yaml and require a mapping at its root."""
    target = path or load_runtime_settings().agents_config_path
    with open(target, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    if not isinstance(config, Mapping):
        raise ValueError(f"Agent config must contain a mapping: {target}")
    return dict(config)


def get_use_case_id(config: Mapping[str, Any] | None = None) -> str:
    """Return the configured non-empty use-case identifier."""
    if config is None:
        config = load_config()
    use_case_id = config.get("use_case_id")
    if not isinstance(use_case_id, str) or not use_case_id.strip():
        raise ValueError("Agent config must define a non-empty use_case_id")
    return use_case_id.strip()
