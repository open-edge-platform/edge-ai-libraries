"""In-memory key-value store with TTL-based expiry for deduplication keys."""

from __future__ import annotations

import asyncio
import time
from typing import Optional


class MemoryStore:
    """Thread-safe in-memory store with automatic TTL expiry."""

    def __init__(self) -> None:
        self._store: dict[str, float] = {}  # key -> expiry_timestamp
        self._lock = asyncio.Lock()

    async def exists(self, key: str) -> bool:
        """Check if a key exists and is not expired."""
        async with self._lock:
            expiry = self._store.get(key)
            if expiry is None:
                return False
            if time.monotonic() > expiry:
                del self._store[key]
                return False
            return True

    async def set(self, key: str, ttl_seconds: int) -> None:
        """Set a key with a TTL in seconds."""
        async with self._lock:
            self._store[key] = time.monotonic() + ttl_seconds

    async def cleanup(self) -> int:
        """Remove all expired keys. Returns count of removed keys."""
        now = time.monotonic()
        async with self._lock:
            expired = [k for k, v in self._store.items() if now > v]
            for k in expired:
                del self._store[k]
            return len(expired)

    async def size(self) -> int:
        """Return the number of active (non-expired) keys."""
        now = time.monotonic()
        async with self._lock:
            return sum(1 for v in self._store.values() if now <= v)


# Module-level singleton
memory_store = MemoryStore()
