# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Logging configuration helpers."""

import logging

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"

def configure_logging(level: str) -> None:
    """Configure the logger """

    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.setLevel(level)
        return

    logging.basicConfig(level=level, format=LOG_FORMAT)
    logging.getLogger(__name__).debug("Logging initialised at level %s", level)
