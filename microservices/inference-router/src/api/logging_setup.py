# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Logging configuration helpers shared by ``main.py``."""

import logging
import os
from pathlib import Path
from typing import Optional

from src.config import RouterConfig
from src.router.logging_utils import (
    is_verbose_enabled,
    is_verbose_full_enabled,
    log_to_gateway_file,
)


_LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def setup_logging(config: RouterConfig, *, logger_name: str = "gateway") -> None:
    """Configure root logging from ``config.log_level``.

    ``force=True`` so this can override any handlers attached at import time
    (e.g. the bootstrap ``logging.basicConfig`` in ``main.py``).
    """
    level_name = (config.log_level or "info").lower()
    log_level = _LEVEL_MAP.get(level_name, logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,
    )

    logger = logging.getLogger(logger_name)
    logger.setLevel(log_level)
    logger.info(f"Logging initialized at {level_name.upper()} level")


def resolve_log_dir() -> Optional[Path]:
    """Return the log directory configured via ``GATEWAY_LOG_DIR``, or None.

    Creates the directory and writes the ``Gateway Started`` banner so the
    file format matches the legacy gateway exactly.
    """
    log_base = os.getenv("GATEWAY_LOG_DIR")
    if not log_base:
        return None

    log_dir = Path(log_base)
    log_dir.mkdir(parents=True, exist_ok=True)
    msg = f"📝 Gateway logs will be saved to: {log_dir}"
    print(msg)
    log_to_gateway_file(msg, log_dir)
    log_to_gateway_file("=" * 80, log_dir)
    log_to_gateway_file("Gateway Started", log_dir)
    log_to_gateway_file("=" * 80, log_dir)
    return log_dir


def resolve_verbose_flags() -> tuple[bool, bool]:
    """Read the ``GATEWAY_VERBOSE`` / ``GATEWAY_VERBOSE_FULL`` env flags.

    Returns ``(verbose, verbose_full)``. ``verbose_full`` implies ``verbose``.
    """
    verbose = is_verbose_enabled()
    verbose_full = is_verbose_full_enabled()
    return verbose, verbose_full
