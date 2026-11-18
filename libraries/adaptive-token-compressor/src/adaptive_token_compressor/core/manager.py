# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""CompressionManager: compressor registry + auto-aggregation + cache owner.

Single-threaded registration; wrapper.compress() auto-observes metrics.

Keyed metrics: register_compressor(..., metrics_keys=["provider", "user"])
declares the keys a compressor is counted by; compress(..., metrics_values=
{"provider": "vllm", "user": "alice"}) additionally observes into one
process-wide aggregator per (key, value) bucket. A bucket only holds the metrics
of compressors called with it: a metric is registered there when the first
compressor it tracks is called with the bucket. Only metric accounting is split;
compressors, caches and session state are shared.
"""
import logging
import threading
from typing import Callable, Mapping, Sequence

import cachetools

from .aggregator import MetricsAggregator, _MetricSpec
from .base import BaseCompressor, CompressionContext, CompressorResult
from .cache import CacheSlot
from .health import HealthStatus

logger = logging.getLogger("adaptive_token_compressor.core.manager")

# Value that absorbs a key's values beyond CompressionManager(max_metric_values=...).
OVERFLOW_METRICS_VALUE = "other"


def _validate_metrics_keys(metrics_keys: Sequence[str] | None) -> tuple[str, ...]:
    if metrics_keys is None:
        return ()
    if isinstance(metrics_keys, str):
        raise TypeError("metrics_keys must be a list of key names, e.g. ['provider']")
    keys = tuple(metrics_keys)
    for key in keys:
        if not isinstance(key, str) or not key:
            raise ValueError(f"metrics_keys entries must be non-empty strings, got {key!r}")
    if len(set(keys)) != len(keys):
        raise ValueError(f"metrics_keys contains duplicates: {list(keys)}")
    return keys


def _spec_sources(metric: _MetricSpec) -> frozenset[str] | None:
    """Sources a metric spec tracks; None for source-agnostic specs (RequestCount)."""
    sources = getattr(metric, "sources", None)
    if sources is None:
        return None
    return frozenset([sources]) if isinstance(sources, str) else frozenset(sources)


class _RegisteredCompressor:
    """Wrapper: inner.compress(ctx) + aggregator.observe(source, result.metrics)."""

    name: str

    def __init__(
        self,
        source: str,
        inner: BaseCompressor,
        aggregator: MetricsAggregator,
        keyed: Callable[[str, str, str], MetricsAggregator] | None = None,
        metrics_keys: tuple[str, ...] = (),
    ) -> None:
        self._source = source
        self._inner = inner
        self._aggregator = aggregator
        self._keyed = keyed
        self._metrics_keys = metrics_keys
        self.name = inner.name

    def compress(
        self,
        ctx: CompressionContext,
        *,
        req_id: str | None = None,
        metrics_values: Mapping[str, str | None] | None = None,
    ) -> CompressorResult:
        """Compress and record metrics.

        `metrics_values` maps each key declared at registration to this call's
        value; undeclared keys are ignored, and None/"" skips that key.
        req_id dedups requests within a bucket; metrics_values picks the buckets.
        """
        buckets = self._buckets(metrics_values)
        result = self._inner.compress(ctx)
        self._aggregator.observe(self._source, result.metrics, req_id=req_id)
        if self._keyed is not None:
            for key, value in buckets:
                agg = self._keyed(key, value, self._source)
                agg.observe(self._source, result.metrics, req_id=req_id)
        return result

    def _buckets(self, metrics_values: Mapping[str, str | None] | None) -> list[tuple[str, str]]:
        """(key, value) buckets for this call; validated before compressing."""
        if metrics_values is None:
            return []
        if not isinstance(metrics_values, Mapping):
            raise TypeError(
                "metrics_values must be a mapping of key to value, e.g. {'provider': 'vllm'}"
            )
        buckets = []
        for key in self._metrics_keys:
            value = metrics_values.get(key)
            if value is None or value == "":
                continue
            if not isinstance(value, str):
                raise TypeError(f"metrics_values[{key!r}] must be a string, got {value!r}")
            buckets.append((key, value))
        return buckets

    def health_check(self, *, timeout: float = 5.0) -> HealthStatus:
        return self._inner.health_check(timeout=timeout)

    @property
    def inner(self) -> BaseCompressor:
        return self._inner


class CompressionManager:
    """Compressor container + auto-aggregation."""

    def __init__(self, *, cache_size: int = 4096, max_metric_values: int = 64) -> None:
        if max_metric_values < 1:
            raise ValueError("max_metric_values must be >= 1")
        self._compressors: dict[str, _RegisteredCompressor] = {}
        self._aggregator = MetricsAggregator()
        # Keyed aggregators (key -> value -> aggregator) are created on first
        # use. A metric is registered in a bucket when the first source it
        # tracks is called with that bucket; _keyed_sources[key][value] =
        # sources whose metrics are registered there.
        self._specs: list[tuple[str, _MetricSpec]] = []
        self._anchor: str | None = None
        self._keyed_aggs: dict[str, dict[str, MetricsAggregator]] = {}
        self._keyed_sources: dict[str, dict[str, set[str]]] = {}
        self._keyed_lock = threading.Lock()
        self._max_metric_values: int = max_metric_values
        self._overflow_warned: set[str] = set()
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
        *,
        metrics_keys: Sequence[str] | None = None,
    ) -> _RegisteredCompressor:
        """Register `compressor` as `source`.

        `metrics_keys` declares the keys this compressor's metrics are also
        counted by (e.g. ["provider", "user"]); compress() gives their values.
        """
        if source in self._compressors:
            raise ValueError(f"Compressor source '{source}' already registered")
        keys = _validate_metrics_keys(metrics_keys)

        # Cache injection
        if hasattr(compressor, "set_cache") and callable(getattr(compressor, "set_cache")):
            slot = CacheSlot(
                cache=cachetools.LRUCache(maxsize=self._cache_size),
                lock=threading.Lock(),
            )
            self._cache_slots[source] = slot
            compressor.set_cache(slot.cache, slot.lock)

        wrapper = _RegisteredCompressor(
            source, compressor, self._aggregator, self._keyed, metrics_keys=keys
        )
        self._compressors[source] = wrapper
        return wrapper

    def register_metric(self, name: str, metric: _MetricSpec) -> None:
        # Validate sources exist
        sources = _spec_sources(metric)
        for s in sorted(sources or ()):
            if s not in self._compressors:
                raise ValueError(
                    f"Metric '{name}' references unknown source '{s}'. "
                    f"Register compressor first."
                )

        metric._emit_rules(name, self._aggregator)
        with self._keyed_lock:
            self._specs.append((name, metric))
            for key, aggs in self._keyed_aggs.items():
                for value, agg in aggs.items():
                    if sources is None or sources & self._keyed_sources[key][value]:
                        metric._emit_rules(name, agg)

    def set_per_anchor(self, source: str) -> None:
        if source not in self._compressors:
            raise ValueError(f"Anchor source '{source}' not registered")
        self._aggregator._set_anchor(source)
        with self._keyed_lock:
            self._anchor = source
            for aggs in self._keyed_aggs.values():
                for agg in aggs.values():
                    agg._set_anchor(source)

    def _keyed(self, key: str, value: str, source: str) -> MetricsAggregator:
        """Shared aggregator for bucket (key, value), with the metrics tracking `source` registered.

        Created on first use (source-agnostic metrics only); a key's values
        beyond max_metric_values go to "other".
        """
        with self._keyed_lock:
            aggs = self._keyed_aggs.setdefault(key, {})
            sources = self._keyed_sources.setdefault(key, {})
            agg = aggs.get(value)
            if agg is None and len(aggs) >= self._max_metric_values:
                if key not in self._overflow_warned:
                    logger.warning(
                        "metrics value limit (%d) reached for key '%s'; "
                        "further values are counted under '%s'",
                        self._max_metric_values,
                        key,
                        OVERFLOW_METRICS_VALUE,
                    )
                    self._overflow_warned.add(key)
                value = OVERFLOW_METRICS_VALUE
                agg = aggs.get(value)
            if agg is None:
                agg = MetricsAggregator()
                for name, metric in self._specs:
                    if _spec_sources(metric) is None:
                        metric._emit_rules(name, agg)
                if self._anchor is not None:
                    agg._set_anchor(self._anchor)
                aggs[value] = agg
                sources[value] = set()

            registered = sources[value]
            if source not in registered:
                # A metric is new to this key iff none of its sources came before.
                for name, metric in self._specs:
                    sources = _spec_sources(metric)
                    if sources is not None and source in sources and not sources & registered:
                        metric._emit_rules(name, agg)
                registered.add(source)
            return agg

    # ───── Read ─────
    def __getitem__(self, source: str) -> _RegisteredCompressor:
        return self._compressors[source]

    def snapshot(
        self,
        source: str | None = None,
        key: str | None = None,
        value: str | None = None,
    ) -> dict[str, float]:
        """One bucket: global without `key`, else bucket (key, value)."""
        if (key is None) != (value is None):
            raise ValueError("snapshot() needs both key and value, or neither")
        if key is None:
            return self._aggregator.snapshot(source=source)
        return self._keyed_snapshot(key, value, source)

    def snapshot_by_keys(self, source: str | None = None) -> dict[str, dict[str, dict[str, float]]]:
        """{key: {value: snapshot}} for every bucket that has observed data."""
        with self._keyed_lock:
            buckets = [(key, list(aggs)) for key, aggs in self._keyed_aggs.items()]
        result: dict[str, dict[str, dict[str, float]]] = {}
        for key, values in buckets:
            for value in values:
                snap = self._keyed_snapshot(key, value, source)
                if snap:
                    result.setdefault(key, {})[value] = snap
        return result

    def _keyed_snapshot(self, key: str, value: str, source: str | None) -> dict[str, float]:
        """`{}` if the bucket (or `source` under it) has no registered metrics or no data."""
        with self._keyed_lock:
            agg = self._keyed_aggs.get(key, {}).get(value)
            registered = set(self._keyed_sources.get(key, {}).get(value, ()))
        if agg is None:
            return {}
        if source is not None:
            return agg.snapshot(source=source) if source in registered else {}
        # Every source reset → only source-agnostic metrics with no denominator left.
        return agg.snapshot() if agg._seen_sources() else {}

    def cache_stats(self) -> dict[str, dict[str, int]]:
        stats = {}
        for source, slot in self._cache_slots.items():
            with slot.lock:
                stats[source] = {
                    "currsize": len(slot.cache),
                    "maxsize": slot.cache.maxsize,
                }
        return stats

    def reset(
        self,
        source: str | None = None,
        key: str | None = None,
        value: str | None = None,
    ) -> None:
        """Clear metrics (global + keyed). With `key`, only that key's buckets;
        with `key` and `value`, only bucket (key, value).

        Content caches are cleared only when `key` is None.
        """
        if value is not None and key is None:
            raise ValueError("reset() with value needs key")
        if key is not None:
            with self._keyed_lock:
                if source is None:
                    if value is None:
                        self._keyed_aggs.pop(key, None)
                        self._keyed_sources.pop(key, None)
                        self._overflow_warned.discard(key)
                    else:
                        self._keyed_aggs.get(key, {}).pop(value, None)
                        self._keyed_sources.get(key, {}).pop(value, None)
                    return
                aggs = self._keyed_aggs.get(key, {})
                aggs = list(aggs.values()) if value is None else [aggs.get(value)]
            for agg in aggs:
                if agg is not None:
                    agg.reset(source=source)
            return

        self._aggregator.reset(source=source)
        with self._keyed_lock:
            if source is None:
                self._keyed_aggs.clear()
                self._keyed_sources.clear()
                self._overflow_warned.clear()
                aggs = []
            else:
                aggs = [agg for by_value in self._keyed_aggs.values() for agg in by_value.values()]
        for agg in aggs:
            agg.reset(source=source)

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
