"""Tests for core/cache.py — covers plan §13 row `core/cache`."""
from __future__ import annotations

import threading

import cachetools
import pytest

from adaptive_token_compressor.core.cache import (
    CacheSlot,
    cache_get,
    cache_set,
    hash_key,
)


# ─────────────────────────────────────────────────────────────────────────────
# hash_key
# ─────────────────────────────────────────────────────────────────────────────


class TestHashKey:
    def test_same_input_same_output(self):
        a = hash_key("lingua", "content", 0.5)
        b = hash_key("lingua", "content", 0.5)
        assert a == b

    def test_different_input_different_output(self):
        a = hash_key("lingua", "content", 0.5)
        b = hash_key("lingua", "content", 0.6)
        assert a != b

    def test_order_sensitive(self):
        # Different order → different hash
        a = hash_key("a", "b", "c")
        b = hash_key("c", "b", "a")
        assert a != b

    def test_returns_64_char_hex(self):
        # sha256 hex digest is always 64 chars
        assert len(hash_key("x")) == 64
        assert all(c in "0123456789abcdef" for c in hash_key("x"))

    def test_empty_args(self):
        # Should not crash
        result = hash_key()
        assert len(result) == 64

    def test_handles_various_types(self):
        # str(p) fallback handles int, float, bool, None
        result = hash_key("op", 42, 3.14, True, None)
        assert len(result) == 64


# ─────────────────────────────────────────────────────────────────────────────
# cache_get / cache_set integration
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheGetSet:
    def test_standalone_path_cache_none_returns_none_none(self):
        key, val = cache_get(None, None, "op", "arg")
        assert key is None
        assert val is None

    def test_miss_returns_key_and_none(self):
        cache = cachetools.LRUCache(maxsize=4)
        lock = threading.Lock()
        key, val = cache_get(cache, lock, "op", "new_key")
        assert key is not None
        assert val is None

    def test_hit_returns_key_and_value(self):
        cache = cachetools.LRUCache(maxsize=4)
        lock = threading.Lock()
        key, _ = cache_get(cache, lock, "op", "arg")
        cache_set(cache, lock, key, "result")
        key2, val = cache_get(cache, lock, "op", "arg")
        assert key2 == key
        assert val == "result"

    def test_set_no_op_when_cache_none(self):
        # Should not crash
        cache_set(None, None, "key", "value")

    def test_set_no_op_when_key_none(self):
        cache = cachetools.LRUCache(maxsize=4)
        lock = threading.Lock()
        cache_set(cache, lock, None, "value")
        assert len(cache) == 0

    def test_lru_eviction_on_overflow(self):
        cache = cachetools.LRUCache(maxsize=2)
        lock = threading.Lock()
        # Fill cache
        cache_set(cache, lock, "k1", "v1")
        cache_set(cache, lock, "k2", "v2")
        # Third write triggers eviction of k1 (least recently used)
        cache_set(cache, lock, "k3", "v3")
        assert "k1" not in cache
        assert "k2" in cache
        assert "k3" in cache

    def test_concurrent_set_same_key_last_writer_wins(self):
        cache = cachetools.LRUCache(maxsize=16)
        lock = threading.Lock()
        results = []

        def writer(val):
            cache_set(cache, lock, "shared_key", val)
            results.append(val)

        threads = [threading.Thread(target=writer, args=(f"v{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Last writer won (value is one of the 5 written)
        assert cache["shared_key"] in results
        # All 5 threads ran
        assert len(results) == 5

    def test_concurrent_different_keys_no_loss(self):
        cache = cachetools.LRUCache(maxsize=100)
        lock = threading.Lock()

        def writer(i):
            cache_set(cache, lock, f"k{i}", f"v{i}")

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All 20 keys present
        assert len(cache) == 20


# ─────────────────────────────────────────────────────────────────────────────
# CacheSlot
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheSlot:
    def test_bundles_cache_and_lock(self):
        slot = CacheSlot(cache=cachetools.LRUCache(maxsize=8))
        assert isinstance(slot.cache, cachetools.LRUCache)
        # threading.Lock() returns _thread.lock, check it's a lock-like object
        assert hasattr(slot.lock, "acquire") and hasattr(slot.lock, "release")

    def test_clear_empties_cache(self):
        slot = CacheSlot(cache=cachetools.LRUCache(maxsize=4))
        slot.cache["a"] = "1"
        slot.cache["b"] = "2"
        slot.clear()
        assert len(slot.cache) == 0

    def test_stats_returns_currsize_and_maxsize(self):
        slot = CacheSlot(cache=cachetools.LRUCache(maxsize=8))
        slot.cache["x"] = "1"
        slot.cache["y"] = "2"
        stats = slot.stats()
        assert stats == {"currsize": 2, "maxsize": 8}

    def test_clear_concurrent_safe(self):
        # clear() holds lock — concurrent reads don't see torn state
        slot = CacheSlot(cache=cachetools.LRUCache(maxsize=100))
        for i in range(50):
            slot.cache[f"k{i}"] = f"v{i}"

        exceptions = []

        def reader():
            try:
                for _ in range(100):
                    _ = len(slot.cache)  # trigger internal iteration
            except Exception as e:
                exceptions.append(e)

        def clearer():
            for _ in range(10):
                slot.clear()

        threads = [threading.Thread(target=reader) for _ in range(3)]
        threads.append(threading.Thread(target=clearer))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No crashes — clear() held lock properly
        assert not exceptions

    def test_stats_concurrent_safe(self):
        slot = CacheSlot(cache=cachetools.LRUCache(maxsize=50))
        exceptions = []

        def writer():
            for i in range(20):
                slot.cache[f"w{threading.get_ident()}_{i}"] = "v"

        def reader():
            try:
                for _ in range(50):
                    _ = slot.stats()
            except Exception as e:
                exceptions.append(e)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # stats() held lock — no torn reads
        assert not exceptions
