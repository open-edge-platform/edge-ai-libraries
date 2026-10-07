# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Loader for the legacy DL Streamer Pipeline Server config.json.

Usage
-----
    from config.loader import load_legacy_config

    cfg = load_legacy_config()          # reads ./config.json by default
    cfg = load_legacy_config("/path/to/config.json")

    for pipeline in cfg.pipelines:
        print(pipeline.name, pipeline.pipeline)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from config.models import LegacyConfig

_DEFAULT_CONFIG_PATH = os.environ.get("DLSPS_CONFIG_PATH", "config.json")


def load_legacy_config(path: str | os.PathLike | None = None) -> LegacyConfig:
    """Parse a legacy config.json file and return a validated :class:`LegacyConfig`.

    Args:
        path: Path to the config file.  Defaults to the value of the
              ``DLSPS_CONFIG_PATH`` environment variable, or ``config.json``
              in the current working directory.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file content fails validation.

    Returns:
        A fully-validated :class:`LegacyConfig` instance.
    """
    resolved = Path(path) if path is not None else Path(_DEFAULT_CONFIG_PATH)

    if not resolved.is_file():
        raise FileNotFoundError(f"Config file not found: {resolved}")

    with resolved.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    return LegacyConfig.model_validate(raw)
