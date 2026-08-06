# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Metrics aggregator: rule engine + 14 MetricSpec dataclasses.

Engine layer (private): _SumRule/_CountRule/_RatioRule/_RequestRatioRule + MetricsAggregator.
Declaration layer (public): 14 MetricSpec dataclasses emit rules via _emit_rules(name, agg).
"""
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Protocol, runtime_checkable

from .metrics import CompressorMetrics

logger = logging.getLogger("adaptive_token_compressor.core.aggregator")


_METRIC_FIELDS: frozenset[str] = frozenset({
    "tokens_before",
    "tokens_after",
    "duration_ms",
    "saved_tokens",  # derived @property = tokens_before - tokens_after
})


# ───────────────────────── Engine layer (private) ─────────────────────────

@dataclass(frozen=True)
class _SumRule:
    name: str
    field: str
    sources: frozenset[str]
    hidden: bool = False


@dataclass(frozen=True)
class _CountRule:
    name: str
    sources: frozenset[str]
    hidden: bool = False


@dataclass(frozen=True)
class _RatioRule:
    """snapshot() computes num/den; returns 0.0 when den==0."""
    name: str
    num: str
    den: str


@dataclass(frozen=True)
class _RequestRatioRule:
    """snapshot() computes num/request_count(); returns 0.0 when denominator==0."""
    name: str
    num: str


@dataclass(frozen=True)
class _RequestCountRule:
    """snapshot() emits request_count() directly (unique req_ids, anchor fallback)."""
    name: str


@dataclass
class _SourceState:
    buckets: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    seen_req_ids: set[str] = field(default_factory=set)
    observe_count: int = 0


class MetricsAggregator:
    """Rule-driven aggregator. O(rules + unique_req_ids) memory.

    Thread-safe: `observe` / `snapshot` / `reset` / `request_count` take
    `_lock` so concurrent `compress()` calls (e.g. a threaded/async server
    running compressors off the event loop) can't interleave the non-atomic
    read-modify-write on `_buckets` / `_observe_counts`. Rule registration
    (`_add_*` / `_set_anchor`) happens at setup time and is not locked.
    """

    def __init__(self) -> None:
        self._rules: list[
            _SumRule | _CountRule | _RatioRule | _RequestRatioRule | _RequestCountRule
        ] = []
        self._states: dict[str, _SourceState] = {}
        self._global_buckets: dict[str, float] = defaultdict(float)
        self._global_seen_req_ids: set[str] = set()
        self._global_observe_counts: dict[str, int] = {}
        self._global_dirty: bool = False
        self._anchor: str | None = None
        self._lock = threading.Lock()

    def _get_or_create_state(self, source: str) -> _SourceState:
        state = self._states.get(source)
        if state is None:
            state = _SourceState()
            self._states[source] = state
        return state

    def _selected_sources(self, source: str | None) -> frozenset[str] | None:
        if source is None:
            return None
        return frozenset([source])

    def _bucket_value_nolock(self, bucket_name: str, sources: frozenset[str] | None) -> float:
        if sources is None:
            self._ensure_global_cache_nolock()
            return self._global_buckets.get(bucket_name, 0.0)
        total = 0.0
        for src in sources:
            state = self._states.get(src)
            if state is None:
                continue
            total += state.buckets.get(bucket_name, 0.0)
        return total

    def _ensure_global_cache_nolock(self) -> None:
        if not self._global_dirty:
            return
        self._global_buckets = defaultdict(float)
        self._global_seen_req_ids.clear()
        self._global_observe_counts = {}
        for source, state in self._states.items():
            for bucket_name, value in state.buckets.items():
                self._global_buckets[bucket_name] += value
            self._global_seen_req_ids.update(state.seen_req_ids)
            self._global_observe_counts[source] = state.observe_count
        self._global_dirty = False

    def _add_sum(
        self,
        name: str,
        field: str,
        sources: Iterable[str],
        hidden: bool = False,
    ) -> None:
        if field not in _METRIC_FIELDS:
            raise ValueError(f"Invalid field '{field}'; must be one of {_METRIC_FIELDS}")
        if any(r.name == name for r in self._rules):
            raise ValueError(f"Duplicate rule name '{name}'")
        self._rules.append(_SumRule(name, field, frozenset(sources), hidden))

    def _add_count(
        self,
        name: str,
        sources: Iterable[str],
        hidden: bool = False,
    ) -> None:
        if any(r.name == name for r in self._rules):
            raise ValueError(f"Duplicate rule name '{name}'")
        self._rules.append(_CountRule(name, frozenset(sources), hidden))

    def _add_ratio(self, name: str, num: str, den: str) -> None:
        if any(r.name == name for r in self._rules):
            raise ValueError(f"Duplicate rule name '{name}'")
        # num/den buckets must be defined by prior _SumRule or _CountRule
        known_buckets = {r.name for r in self._rules if isinstance(r, (_SumRule, _CountRule))}
        if num not in known_buckets:
            raise ValueError(f"Ratio numerator '{num}' references unknown bucket")
        if den not in known_buckets:
            raise ValueError(f"Ratio denominator '{den}' references unknown bucket")
        self._rules.append(_RatioRule(name, num, den))

    def _add_request_ratio(self, name: str, num: str) -> None:
        if any(r.name == name for r in self._rules):
            raise ValueError(f"Duplicate rule name '{name}'")
        known_buckets = {r.name for r in self._rules if isinstance(r, (_SumRule, _CountRule))}
        if num not in known_buckets:
            raise ValueError(f"RequestRatio numerator '{num}' references unknown bucket")
        self._rules.append(_RequestRatioRule(name, num))

    def _add_request_count(self, name: str) -> None:
        if any(r.name == name for r in self._rules):
            raise ValueError(f"Duplicate rule name '{name}'")
        self._rules.append(_RequestCountRule(name))

    def _set_anchor(self, source: str) -> None:
        if self._anchor is not None and self._anchor != source:
            raise RuntimeError(
                f"Anchor already set to '{self._anchor}'; cannot change to '{source}'"
            )
        self._anchor = source

    def _has_denominator(self, source: str | None = None) -> bool:
        selected = self._selected_sources(source)
        return self._has_denominator_nolock(selected)

    def _has_denominator_nolock(self, selected: frozenset[str] | None) -> bool:
        if selected is None:
            self._ensure_global_cache_nolock()
            return bool(self._global_seen_req_ids) or self._anchor is not None

        for src in selected:
            state = self._states.get(src)
            if state is not None and state.seen_req_ids:
                return True
        return self._anchor is not None and self._anchor in selected

    def request_count(self, source: str | None = None) -> int:
        with self._lock:
            return self._request_count_nolock(self._selected_sources(source))

    def _request_count_nolock(self, selected: frozenset[str] | None) -> int:
        # Caller must hold `_lock` (or be at setup time). `snapshot` calls this
        # while already holding the lock — a plain Lock isn't reentrant, so the
        # locked entry point and the internal one are kept separate.
        if selected is None:
            self._ensure_global_cache_nolock()
            if self._global_seen_req_ids:
                return len(self._global_seen_req_ids)
            if self._anchor is not None:
                return self._global_observe_counts.get(self._anchor, 0)
            return 0

        req_ids: set[str] = set()
        for src in selected:
            state = self._states.get(src)
            if state is None:
                continue
            req_ids.update(state.seen_req_ids)
        if req_ids:
            return len(req_ids)
        if self._anchor is not None and self._anchor in selected:
            anchor_state = self._states.get(self._anchor)
            return 0 if anchor_state is None else anchor_state.observe_count
        return 0

    def observe(
        self,
        source: str,
        metrics: CompressorMetrics,
        req_id: str | None = None,
    ) -> None:
        with self._lock:
            state = self._get_or_create_state(source)
            if req_id is not None:
                state.seen_req_ids.add(req_id)
            state.observe_count += 1

            if not self._global_dirty:
                if req_id is not None:
                    self._global_seen_req_ids.add(req_id)
                self._global_observe_counts[source] = (
                    self._global_observe_counts.get(source, 0) + 1
                )

            for r in self._rules:
                if isinstance(r, _SumRule) and source in r.sources:
                    value = getattr(metrics, r.field)
                    state.buckets[r.name] += value
                    if not self._global_dirty:
                        self._global_buckets[r.name] += value
                elif isinstance(r, _CountRule) and source in r.sources:
                    state.buckets[r.name] += 1
                    if not self._global_dirty:
                        self._global_buckets[r.name] += 1

    def snapshot(self, source: str | None = None) -> dict[str, float]:
        # Locked so a concurrent observe() can't be seen half-applied (e.g. a
        # ratio computed from a numerator that advanced but a denominator that
        # hasn't yet). Uses the nolock request_count since we already hold it.
        with self._lock:
            selected = self._selected_sources(source)
            source_prefix = f"{source}." if source is not None else None

            # Per-request metrics need a denominator (a seen req_id or a
            # configured anchor). Checked here — not at registration — because
            # snapshot is the only point where req_id / anchor are fully known.
            has_per_request = any(
                isinstance(r, (_RequestRatioRule, _RequestCountRule))
                and (source_prefix is None or r.name.startswith(source_prefix))
                for r in self._rules
            )
            if has_per_request and not self._has_denominator_nolock(selected):
                raise RuntimeError(
                    "PerRequest metric requires a denominator. Either pass req_id "
                    "to wrapper.compress() or call mgr.set_per_anchor(<source>) first."
                )

            result: dict[str, float] = {}
            # Copy non-hidden buckets
            for r in self._rules:
                if source_prefix is not None and not r.name.startswith(source_prefix):
                    continue
                if isinstance(r, (_SumRule, _CountRule)) and not r.hidden:
                    result[r.name] = self._bucket_value_nolock(r.name, selected)

            # Compute derived ratios
            for r in self._rules:
                if source_prefix is not None and not r.name.startswith(source_prefix):
                    continue
                if isinstance(r, _RatioRule):
                    num_val = self._bucket_value_nolock(r.num, selected)
                    den_val = self._bucket_value_nolock(r.den, selected)
                    result[r.name] = num_val / den_val if den_val != 0 else 0.0
                elif isinstance(r, _RequestRatioRule):
                    num_val = self._bucket_value_nolock(r.num, selected)
                    den_val = self._request_count_nolock(selected)
                    result[r.name] = num_val / den_val if den_val != 0 else 0.0
                elif isinstance(r, _RequestCountRule):
                    result[r.name] = float(self._request_count_nolock(selected))

            return result

    def reset(self, source: str | None = None) -> None:
        with self._lock:
            if source is None:
                self._states.clear()
                self._global_buckets = defaultdict(float)
                self._global_seen_req_ids.clear()
                self._global_observe_counts = {}
                self._global_dirty = False
                return

            self._states.pop(source, None)
            self._global_dirty = True


# ───────────────────────── Declaration layer (public) ─────────────────────

@runtime_checkable
class _MetricSpec(Protocol):
    def _emit_rules(self, name: str, agg: MetricsAggregator) -> None: ...


def _to_set(sources: str | list[str]) -> frozenset[str]:
    if isinstance(sources, str):
        return frozenset([sources])
    return frozenset(sources)


# ----- First-order: direct sum / count -----

@dataclass(frozen=True)
class CallCount:
    sources: str | list[str]

    def _emit_rules(self, name: str, agg: MetricsAggregator) -> None:
        agg._add_count(name, _to_set(self.sources))


@dataclass(frozen=True)
class TotalInput:
    sources: str | list[str]

    def _emit_rules(self, name: str, agg: MetricsAggregator) -> None:
        agg._add_sum(name, "tokens_before", _to_set(self.sources))


@dataclass(frozen=True)
class TotalOutput:
    sources: str | list[str]

    def _emit_rules(self, name: str, agg: MetricsAggregator) -> None:
        agg._add_sum(name, "tokens_after", _to_set(self.sources))


@dataclass(frozen=True)
class TotalSaved:
    sources: str | list[str]

    def _emit_rules(self, name: str, agg: MetricsAggregator) -> None:
        agg._add_sum(name, "saved_tokens", _to_set(self.sources))


@dataclass(frozen=True)
class TotalDuration:
    sources: str | list[str]

    def _emit_rules(self, name: str, agg: MetricsAggregator) -> None:
        agg._add_sum(name, "duration_ms", _to_set(self.sources))


# ----- Second-order: derived ratio (no anchor required) -----

@dataclass(frozen=True)
class CompressionRatio:
    """sum(tokens_after) / sum(tokens_before). Lower = stronger compression."""
    sources: str | list[str]

    def _emit_rules(self, name: str, agg: MetricsAggregator) -> None:
        sources_set = _to_set(self.sources)
        # Hidden buckets: __<name>_in, __<name>_out
        in_bucket = f"__{name}_in"
        out_bucket = f"__{name}_out"
        agg._add_sum(in_bucket, "tokens_before", sources_set, hidden=True)
        agg._add_sum(out_bucket, "tokens_after", sources_set, hidden=True)
        agg._add_ratio(name, out_bucket, in_bucket)


@dataclass(frozen=True)
class AvgSavedPerCall:
    sources: str | list[str]

    def _emit_rules(self, name: str, agg: MetricsAggregator) -> None:
        sources_set = _to_set(self.sources)
        s_bucket = f"__{name}_s"
        n_bucket = f"__{name}_n"
        agg._add_sum(s_bucket, "saved_tokens", sources_set, hidden=True)
        agg._add_count(n_bucket, sources_set, hidden=True)
        agg._add_ratio(name, s_bucket, n_bucket)


@dataclass(frozen=True)
class AvgDurationPerCall:
    sources: str | list[str]

    def _emit_rules(self, name: str, agg: MetricsAggregator) -> None:
        sources_set = _to_set(self.sources)
        d_bucket = f"__{name}_d"
        n_bucket = f"__{name}_n"
        agg._add_sum(d_bucket, "duration_ms", sources_set, hidden=True)
        agg._add_count(n_bucket, sources_set, hidden=True)
        agg._add_ratio(name, d_bucket, n_bucket)


@dataclass(frozen=True)
class AvgInputPerCall:
    sources: str | list[str]

    def _emit_rules(self, name: str, agg: MetricsAggregator) -> None:
        sources_set = _to_set(self.sources)
        i_bucket = f"__{name}_i"
        n_bucket = f"__{name}_n"
        agg._add_sum(i_bucket, "tokens_before", sources_set, hidden=True)
        agg._add_count(n_bucket, sources_set, hidden=True)
        agg._add_ratio(name, i_bucket, n_bucket)


@dataclass(frozen=True)
class AvgOutputPerCall:
    sources: str | list[str]

    def _emit_rules(self, name: str, agg: MetricsAggregator) -> None:
        sources_set = _to_set(self.sources)
        o_bucket = f"__{name}_o"
        n_bucket = f"__{name}_n"
        agg._add_sum(o_bucket, "tokens_after", sources_set, hidden=True)
        agg._add_count(n_bucket, sources_set, hidden=True)
        agg._add_ratio(name, o_bucket, n_bucket)


# ----- Third-order: per-request (requires req_id or anchor fallback) -----

@dataclass(frozen=True)
class AvgSavedPerRequest:
    sources: str | list[str]

    def _emit_rules(self, name: str, agg: MetricsAggregator) -> None:
        sources_set = _to_set(self.sources)
        s_bucket = f"__{name}_s"
        n_bucket = f"__{name}_n"
        agg._add_sum(s_bucket, "saved_tokens", sources_set, hidden=True)
        agg._add_count(n_bucket, sources_set, hidden=True)  # For anchor fallback
        agg._add_request_ratio(name, s_bucket)


@dataclass(frozen=True)
class AvgDurationPerRequest:
    sources: str | list[str]

    def _emit_rules(self, name: str, agg: MetricsAggregator) -> None:
        sources_set = _to_set(self.sources)
        d_bucket = f"__{name}_d"
        n_bucket = f"__{name}_n"
        agg._add_sum(d_bucket, "duration_ms", sources_set, hidden=True)
        agg._add_count(n_bucket, sources_set, hidden=True)  # For anchor fallback
        agg._add_request_ratio(name, d_bucket)


@dataclass(frozen=True)
class AvgInputPerRequest:
    sources: str | list[str]

    def _emit_rules(self, name: str, agg: MetricsAggregator) -> None:
        sources_set = _to_set(self.sources)
        i_bucket = f"__{name}_i"
        n_bucket = f"__{name}_n"
        agg._add_sum(i_bucket, "tokens_before", sources_set, hidden=True)
        agg._add_count(n_bucket, sources_set, hidden=True)  # For anchor fallback
        agg._add_request_ratio(name, i_bucket)


@dataclass(frozen=True)
class AvgOutputPerRequest:
    sources: str | list[str]

    def _emit_rules(self, name: str, agg: MetricsAggregator) -> None:
        sources_set = _to_set(self.sources)
        o_bucket = f"__{name}_o"
        n_bucket = f"__{name}_n"
        agg._add_sum(o_bucket, "tokens_after", sources_set, hidden=True)
        agg._add_count(n_bucket, sources_set, hidden=True)  # For anchor fallback
        agg._add_request_ratio(name, o_bucket)


@dataclass(frozen=True)
class RequestCount:
    def _emit_rules(self, name: str, agg: MetricsAggregator) -> None:
        agg._add_request_count(name)
