# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Config loader — reads agents.yaml from the mounted use-case config directory."""

import os
import yaml
from typing import Any


_CONFIG_PATH = os.environ.get(
    "AGENTS_CONFIG_PATH",
    os.path.join(os.environ.get("USE_CASE_CONFIGS_DIR", "/configs"), "agents.yaml"),
)


def load_config(path: str | None = None) -> dict[str, Any]:
    """Load agents.yaml.  Returns a dict; raises on missing file."""
    target = path or _CONFIG_PATH
    with open(target, "r") as f:
        return yaml.safe_load(f) or {}


def get_use_case_id(config: dict | None = None) -> str:
    if config is None:
        config = load_config()
    return config.get("use_case_id", "unknown")
