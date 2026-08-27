# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""CompressionManager: compressor registry + auto-aggregation + cache owner.

Single-threaded registration; wrapper.compress() auto-observes metrics.
"""
import logging
import threading

import cachetools

from .aggregator import MetricsAggregator, _MetricSpec
from .base import BaseCompressor, CompressionContext, CompressorResult
from .cache import CacheSlot
from .health import HealthStatus

logger = logging.getLogger("adaptive_token_compressor.core.manager")
 

class _RegisteredCompressor:
    """Wrapper: inner.compress(ctx) + aggregator.observe(source, result.metrics)."""

    name: str

    def __init__(
        self,
        source: str,
        inner: BaseCompressor,
        aggregator: MetricsAggregator,
    ) -> None:
        self._source = source
        self._inner = inner
        self._aggregator = aggregator
        self.name = inner.name

    def compress(
        self,
        ctx: CompressionContext,
        *,
        req_id: str | None = None,
    ) -> CompressorResult:
        result = self._inner.compress(ctx)
        self._aggregator.observe(self._source, result.metrics, req_id=req_id)
        return result

    def health_check(self, *, timeout: float = 5.0) -> HealthStatus:
        return self._inner.health_check(timeout=timeout)

    @property
    def inner(self) -> BaseCompressor:
        return self._inner


class CompressionManager:
    """Compressor container + auto-aggregation."""

    def __init__(self, *, cache_size: int = 4096) -> None:
        self._compressors: dict[str, _RegisteredCompressor] = {}
        self._aggregator = MetricsAggregator()
        self._cache_size: int = cache_size
        self._cache_slots: dict[str, CacheSlot] = {}
        # ^ one CacheSlot (cachetools.LRUCache + threading.Lock) per registered
        #   compressor that implements set_cache(); ToolCompressor lacks set_cache
        #   so no slot is created for it.

    # ───── Registration ─────
    def register_compressor(
        self,
        source: str,
        compressor: BaseCompressor,
    ) -> _RegisteredCompressor:
        if source in self._compressors:
            raise ValueError(f"Compressor source '{source}' already registered")

        # Cache injection
        if hasattr(compressor, "set_cache") and callable(getattr(compressor, "set_cache")):
            slot = CacheSlot(
                cache=cachetools.LRUCache(maxsize=self._cache_size),
                lock=threading.Lock(),
            )
            self._cache_slots[source] = slot
            compressor.set_cache(slot.cache, slot.lock)

        wrapper = _RegisteredCompressor(source, compressor, self._aggregator)
        self._compressors[source] = wrapper
        return wrapper

    def register_metric(self, name: str, metric: _MetricSpec) -> None:
        # Validate sources exist
        if hasattr(metric, "sources"):
            sources = metric.sources if isinstance(metric.sources, list) else [metric.sources]
            for s in sources:
                if s not in self._compressors:
                    raise ValueError(
                        f"Metric '{name}' references unknown source '{s}'. "
                        f"Register compressor first."
                    )

        metric._emit_rules(name, self._aggregator)

    def set_per_anchor(self, source: str) -> None:
        if source not in self._compressors:
            raise ValueError(f"Anchor source '{source}' not registered")
        self._aggregator._set_anchor(source)

    # ───── Read ─────
    def __getitem__(self, source: str) -> _RegisteredCompressor:
        return self._compressors[source]

    def snapshot(self, source: str | None = None) -> dict[str, float]:
        return self._aggregator.snapshot(source=source)

    def cache_stats(self) -> dict[str, dict[str, int]]:
        stats = {}
        for source, slot in self._cache_slots.items():
            with slot.lock:
                stats[source] = {
                    "currsize": len(slot.cache),
                    "maxsize": slot.cache.maxsize,
                }
        return stats

    def reset(self, source: str | None = None) -> None:
        self._aggregator.reset(source=source)

        slots = self._cache_slots.items() if source is None else [(source, self._cache_slots.get(source))]
        for cache_source, slot in slots:
            if slot is None:
                continue
            with slot.lock:
                slot.cache.clear()

    # ───── Startup readiness ─────
    def check_backends(self, *, timeout: float = 5.0) -> None:
        from .health import HealthState

        unhealthy = []
        for source, wrapper in self._compressors.items():
            status = wrapper.health_check(timeout=timeout)
            if status.state is HealthState.DEGRADED:
                logger.warning(
                    "Compressor '%s' health check DEGRADED: %s",
                    source,
                    status.message or "(no message)",
                )
            elif status.state is HealthState.UNHEALTHY:
                unhealthy.append((source, status))

        if unhealthy:
            details = "; ".join(f"{src}: {st.message}" for src, st in unhealthy)
            raise RuntimeError(f"Backend health check failed for: {details}")
