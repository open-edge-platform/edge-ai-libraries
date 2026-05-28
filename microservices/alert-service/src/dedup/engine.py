"""Deduplication engine that orchestrates strategy + store."""

from __future__ import annotations

import logging

from src.core.config import DedupConfig
from src.core.models import AlertEnvelope
from src.dedup.store import MemoryStore, memory_store
from src.dedup.strategy import get_strategy

logger = logging.getLogger(__name__)


class DedupEngine:
    """Checks whether an alert is a duplicate based on config."""

    def __init__(self, store: MemoryStore | None = None) -> None:
        self._store = store or memory_store

    async def is_duplicate(
        self, envelope: AlertEnvelope, config: DedupConfig
    ) -> bool:
        """Return True if the alert is a duplicate and should be dropped."""
        if not config.enabled:
            return False

        strategy = get_strategy(config.strategy)
        key = strategy.compute_key(envelope, config)

        if key is None:
            # Strategy decided to skip dedup (e.g., missing fields)
            return False

        if await self._store.exists(key):
            logger.info("Duplicate alert detected: key=%s", key)
            return True

        await self._store.set(key, config.window_seconds)
        return False
