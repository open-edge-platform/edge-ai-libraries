# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging

from src.common.settings import settings


_LOGGING_CONFIGURED = False


def _resolve_log_level(level_name: str) -> int:
    """Translate configured log level names into stdlib logging constants."""
    return getattr(logging, level_name.upper(), logging.INFO)


def get_logger(name: str = "vector_retriever") -> logging.Logger:
    """Return a logger after applying the shared service log configuration once."""
    global _LOGGING_CONFIGURED
    if not _LOGGING_CONFIGURED:
        logging.basicConfig(
            level=_resolve_log_level(settings.LOG_LEVEL),
            format="%(asctime)s - %(levelname)s - %(message)s",
        )
        _LOGGING_CONFIGURED = True
    return logging.getLogger(name)
