# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Concurrency tracking and admission control.

Inspired by vLLM's ``load_aware_call`` decorator. Used as a FastAPI yield
dependency so the in-flight counter is decremented after the full response
(including streaming bodies) has been sent.
"""

import logging
from typing import AsyncIterator

from fastapi import HTTPException


logger = logging.getLogger(__name__)


# Module-level state. We keep these private and expose accessor helpers so
# tests and the health endpoint don't reach into globals directly.
_active_requests: int = 0
_max_concurrency: int = 0  # 0 = unlimited


def set_max_concurrency(value: int) -> None:
    """Set the max concurrent in-flight requests. ``0`` disables the limit."""
    global _max_concurrency
    _max_concurrency = max(0, int(value))
    logger.info(
        f"Max concurrency: {'unlimited' if _max_concurrency <= 0 else _max_concurrency}"
    )


def get_max_concurrency() -> int:
    """Return the configured max concurrency. ``0`` means unlimited."""
    return _max_concurrency


def get_active_requests() -> int:
    """Return the current count of in-flight requests."""
    return _active_requests


async def concurrency_guard() -> AsyncIterator[None]:
    """FastAPI yield dependency that enforces ``max_concurrency``.

    Increments ``_active_requests`` on entry and decrements after the response
    has finished streaming. Raises HTTP 429 when the limit is reached.
    """
    global _active_requests

    if _max_concurrency > 0 and _active_requests >= _max_concurrency:
        logger.warning(
            f"Concurrency limit reached: active={_active_requests}, max={_max_concurrency}"
        )
        raise HTTPException(
            status_code=429,
            detail=(
                f"Server busy: {_active_requests}/{_max_concurrency} concurrent "
                "requests. Retry later."
            ),
        )

    _active_requests += 1
    try:
        yield
    finally:
        _active_requests -= 1
