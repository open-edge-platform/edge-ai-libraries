# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import Any

from src.schemas.request import DedupConfig
from .store import MemoryStore, memory_store
from .strategy import get_strategy

logger = logging.getLogger(__name__)


class DedupEngine:
    def __init__(self, store: MemoryStore | None = None) -> None:
        self._store = store or memory_store

    async def is_duplicate(self, context: dict[str, Any], config: DedupConfig) -> bool:
        """Return True if this alert is a duplicate (should be dropped)."""
        if not config.enabled:
            return False

        strategy = get_strategy(config.strategy)
        key = strategy.compute_key(context, config)

        if key is None:
            return False

        if await self._store.exists(key):
            logger.info("Duplicate alert: key=%s", key)
            return True

        await self._store.set(key, config.window_seconds)
        return False
