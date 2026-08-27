# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""LRU cache helpers."""
from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from typing import Any

import cachetools


def hash_key(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()


def cache_get(
    cache: cachetools.LRUCache | None,
    lock: threading.Lock | None,
    op_tag: str,
    *key_parts: Any,
) -> tuple[str | None, str | None]:
    if cache is None:
        return None, None
    key = hash_key(op_tag, *key_parts)
    with lock:  # type: ignore[union-attr]
        if key in cache:
            return key, cache[key]
    return key, None


def cache_set(
    cache: cachetools.LRUCache | None,
    lock: threading.Lock | None,
    key: str | None,
    value: str,
) -> None:
    if cache is None or key is None:
        return
    with lock:  # type: ignore[union-attr]
        cache[key] = value


@dataclass
class CacheSlot:
    cache: cachetools.LRUCache
    lock: threading.Lock = field(default_factory=threading.Lock)

    def clear(self) -> None:
        with self.lock:
            self.cache.clear()

    def stats(self) -> dict[str, int]:
        with self.lock:
            return {"currsize": len(self.cache), "maxsize": self.cache.maxsize}
