# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Logging configuration helpers.

The MCP server intentionally uses the standard :mod:`logging` module — no
third-party logger — so that it composes cleanly with whatever logging stack
the host process already has in place (e.g. ``uvicorn``, container orchestrators).
"""

from __future__ import annotations

import logging

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def configure_logging(level: str) -> None:
    """Configure the root logger once and update its level on later calls.

    On the first invocation this installs a single :class:`StreamHandler` with
    a structured, machine-greppable format. Subsequent calls only adjust the
    level so that calling ``configure_logging`` from multiple bootstrap paths
    (CLI, embedded use, tests) is safe and idempotent.

    Args:
        level: A standard logging level name (e.g. ``"INFO"``, ``"DEBUG"``).
    """

    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.setLevel(level)
        return

    logging.basicConfig(level=level, format=LOG_FORMAT)
    logging.getLogger(__name__).debug("Logging initialised at level %s", level)
