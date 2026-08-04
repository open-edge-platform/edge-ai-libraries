# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import time


class MemoryStore:
    """In-memory TTL store for dedup keys."""

    def __init__(self) -> None:
        self._store: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def exists(self, key: str) -> bool:
        async with self._lock:
            expiry = self._store.get(key)
            if expiry is None:
                return False
            if time.monotonic() > expiry:
                del self._store[key]
                return False
            return True

    async def set(self, key: str, ttl_seconds: int) -> None:
        async with self._lock:
            self._store[key] = time.monotonic() + ttl_seconds

    async def cleanup(self) -> int:
        now = time.monotonic()
        async with self._lock:
            expired = [k for k, v in self._store.items() if now > v]
            for k in expired:
                del self._store[k]
            return len(expired)

    async def size(self) -> int:
        now = time.monotonic()
        async with self._lock:
            return sum(1 for v in self._store.values() if now <= v)


memory_store = MemoryStore()
