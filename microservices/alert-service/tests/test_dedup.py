"""Tests for deduplication logic."""

from __future__ import annotations

import pytest

from src.core.config import DedupConfig, HashConfig
from src.core.models import AlertEnvelope
from src.dedup.engine import DedupEngine
from src.dedup.store import MemoryStore
from src.dedup.strategy import FieldHashStrategy, _extract_field


class TestExtractField:
    def test_top_level_field(self):
        """Extracts a top-level key from the alert dict."""
        data = {"alert_type": "TEST"}
        assert _extract_field(data, "alert_type") == "TEST"

    def test_nested_field(self):
        """Extracts a dot-notation nested field."""
        data = {"metadata": {"poi_id": "p1"}}
        assert _extract_field(data, "metadata.poi_id") == "p1"

    def test_missing_field_returns_none(self):
        """Returns None when the field path does not exist."""
        data = {"metadata": {}}
        assert _extract_field(data, "metadata.poi_id") is None

    def test_dedup_metadata_fallback(self):
        """Falls back to dedup_metadata when metadata key is missing."""
        data = {"dedup_metadata": {"poi_id": "p2"}}
        assert _extract_field(data, "metadata.poi_id") == "p2"

    def test_deeply_nested(self):
        """Extracts a deeply nested field (a.b.c)."""
        data = {"a": {"b": {"c": "deep"}}}
        assert _extract_field(data, "a.b.c") == "deep"


class TestFieldHashStrategy:
    def test_compute_key_with_fields(self, sample_concealment_alert):
        """Computes a truncated SHA-1 dedup key from configured fields."""
        envelope = AlertEnvelope.from_raw(sample_concealment_alert)
        config = DedupConfig(
            enabled=True,
            strategy="field_hash",
            fields=["metadata.poi_id", "metadata.camera_id"],
            window_seconds=30,
            on_missing="skip",
            hash=HashConfig(algorithm="sha1", truncate=16),
        )
        strategy = FieldHashStrategy()
        key = strategy.compute_key(envelope, config)

        assert key is not None
        assert key.startswith("dedup:CONCEALMENT:")
        assert len(key.split(":")[2]) == 16

    def test_compute_key_deterministic(self, sample_concealment_alert):
        """Same input always produces the same dedup key."""
        envelope = AlertEnvelope.from_raw(sample_concealment_alert)
        config = DedupConfig(
            enabled=True,
            fields=["metadata.poi_id", "metadata.camera_id"],
            hash=HashConfig(algorithm="sha1", truncate=16),
        )
        strategy = FieldHashStrategy()

        key1 = strategy.compute_key(envelope, config)
        key2 = strategy.compute_key(envelope, config)
        assert key1 == key2

    def test_compute_key_missing_field_skip(self):
        """Returns None when a required field is missing and on_missing=skip."""
        envelope = AlertEnvelope.from_raw({
            "alert_type": "TEST",
            "metadata": {},
        })
        config = DedupConfig(
            enabled=True,
            fields=["metadata.nonexistent"],
            on_missing="skip",
            hash=HashConfig(algorithm="sha1", truncate=16),
        )
        strategy = FieldHashStrategy()
        key = strategy.compute_key(envelope, config)
        assert key is None

    def test_compute_key_md5(self, sample_concealment_alert):
        """Computes a dedup key using MD5 algorithm."""
        envelope = AlertEnvelope.from_raw(sample_concealment_alert)
        config = DedupConfig(
            enabled=True,
            fields=["metadata.poi_id"],
            hash=HashConfig(algorithm="md5", truncate=16),
        )
        strategy = FieldHashStrategy()
        key = strategy.compute_key(envelope, config)
        assert key is not None


class TestMemoryStore:
    @pytest.fixture
    def store(self):
        return MemoryStore()

    async def test_set_and_exists(self, store):
        """Stores a key and confirms it exists."""
        await store.set("key1", ttl_seconds=60)
        assert await store.exists("key1") is True

    async def test_nonexistent_key(self, store):
        """Non-existent key returns False."""
        assert await store.exists("missing") is False

    async def test_expired_key(self, store):
        """Key with TTL=0 expires immediately."""
        await store.set("key1", ttl_seconds=0)
        # TTL=0 means it expires immediately
        assert await store.exists("key1") is False

    async def test_cleanup(self, store):
        """Cleanup removes expired keys and returns the count."""
        await store.set("key1", ttl_seconds=0)
        await store.set("key2", ttl_seconds=3600)
        removed = await store.cleanup()
        assert removed == 1

    async def test_size(self, store):
        """Size returns the number of active keys."""
        await store.set("a", ttl_seconds=3600)
        await store.set("b", ttl_seconds=3600)
        assert await store.size() == 2


class TestDedupEngine:
    @pytest.fixture
    def store(self):
        return MemoryStore()

    @pytest.fixture
    def engine(self, store):
        return DedupEngine(store=store)

    @pytest.fixture
    def dedup_config(self):
        return DedupConfig(
            enabled=True,
            strategy="field_hash",
            fields=["metadata.poi_id", "metadata.camera_id"],
            window_seconds=30,
            on_missing="skip",
            hash=HashConfig(algorithm="sha1", truncate=16),
        )

    async def test_first_alert_not_duplicate(
        self, engine, dedup_config, sample_concealment_alert
    ):
        """First occurrence of an alert is not a duplicate."""
        envelope = AlertEnvelope.from_raw(sample_concealment_alert)
        assert await engine.is_duplicate(envelope, dedup_config) is False

    async def test_second_alert_is_duplicate(
        self, engine, dedup_config, sample_concealment_alert
    ):
        """Second identical alert within the window is a duplicate."""
        envelope = AlertEnvelope.from_raw(sample_concealment_alert)
        await engine.is_duplicate(envelope, dedup_config)
        assert await engine.is_duplicate(envelope, dedup_config) is True

    async def test_dedup_disabled(self, engine, sample_concealment_alert):
        """No alert is considered duplicate when dedup is disabled."""
        config = DedupConfig(enabled=False)
        envelope = AlertEnvelope.from_raw(sample_concealment_alert)
        assert await engine.is_duplicate(envelope, config) is False

    async def test_different_alerts_not_duplicate(
        self, engine, dedup_config
    ):
        """Alerts with different field values are not duplicates."""
        alert1 = {
            "alert_type": "CONCEALMENT",
            "metadata": {"poi_id": "p1", "camera_id": "c1"},
        }
        alert2 = {
            "alert_type": "CONCEALMENT",
            "metadata": {"poi_id": "p2", "camera_id": "c2"},
        }
        e1 = AlertEnvelope.from_raw(alert1)
        e2 = AlertEnvelope.from_raw(alert2)

        assert await engine.is_duplicate(e1, dedup_config) is False
        assert await engine.is_duplicate(e2, dedup_config) is False
