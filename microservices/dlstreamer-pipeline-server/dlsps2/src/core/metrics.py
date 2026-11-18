# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Structured metric observations posted by DL Streamer on the pipeline bus.

DL Streamer producers post ``GST_MESSAGE_ELEMENT`` messages whose structure name
starts with ``dlstreamer/``. The worker forwards them unchanged as ``metric``
events; this module defines that event and merges observations between telemetry
exports. It has no GStreamer or OpenTelemetry dependency.

Kinds, each with its own schema version (see ``SUPPORTED_VERSIONS``):

``latency-window`` (version 1)
    One ``latency_tracer`` interval for one source→sink branch, posted on the
    sink, plus the partial window still open when EOS reaches the sink. Fields:
    ``pipeline``, ``source``, ``sink``, ``window_ms``, ``count``, ``sum_ms``,
    ``min_ms``, ``max_ms``, and from newer tracers the latency distribution:
    ``sum_sq_ms`` (sum of squared frame latencies, ms²), ``bucket_bounds_ms``
    (strictly increasing upper bucket bounds) and ``bucket_counts``
    (``len(bucket_bounds_ms) + 1`` counts, OpenTelemetry explicit-bucket layout,
    the last one being the overflow bucket). Requires
    ``GST_TRACERS="latency_tracer(flags=pipeline,post-metrics=true)"``.
    ``window_ms / count`` is the mean output frame period (1000 / fps), not a
    latency; the frame latency is ``sum_ms / count``, ``min_ms`` and ``max_ms``.
``genai-request`` (version 1)
    One ``gvagenai`` generation request, posted on the element. Fields:
    ``frames``, ``ttft_ms``, ``tpot_ms``, ``generate_duration_ms``,
    ``inference_duration_ms``, ``prepare_embeddings_duration_ms``,
    ``num_input_tokens``, ``num_generated_tokens``. Requires the element
    property ``post-metrics=true``; ``metrics=true`` only adds JSON metadata.

A message of an unknown kind, or of a schema version this module does not
support, is skipped with one warning per kind and version: its fields are never
interpreted. The latency distribution is optional within version 1: an export
period whose windows do not all carry it with the same bucket bounds exports no
stddev or percentiles, with one warning per reason.
"""

import logging
import math
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

METRIC_MESSAGE_PREFIX = "dlstreamer/"

LATENCY_WINDOW = "latency-window"
GENAI_REQUEST = "genai-request"

# Schema version consumed per kind. Any other version may change field meaning, so it is skipped.
SUPPORTED_VERSIONS = {LATENCY_WINDOW: 1, GENAI_REQUEST: 1}

# (metric name, unit, description) of the per-export latency gauges
LATENCY_GAUGES = (
    ("pipeline_latency_avg", "ms", "Mean frame latency, source to the element before the sink, over the export period"),
    ("pipeline_latency_min", "ms", "Minimum frame latency over the export period"),
    ("pipeline_latency_max", "ms", "Maximum frame latency over the export period"),
    ("pipeline_latency_frames", "", "Frames the latency statistics of the export period are computed from"),
    (
        "pipeline_latency_window", "ms",
        (
            "Tracer window time behind those frames, a throughput helper: window / frames is the mean output "
            "frame period (1000 / fps), not a latency"
        ),
    ),
    ("pipeline_latency_stddev", "ms", "Population standard deviation of frame latency over the export period"),
    (
        "pipeline_latency_p50", "ms",
        "Median frame latency over the export period, estimated from the tracer's latency buckets",
    ),
    (
        "pipeline_latency_p95", "ms",
        "95th percentile frame latency over the export period, estimated from the tracer's latency buckets",
    ),
    (
        "pipeline_latency_p99", "ms",
        "99th percentile frame latency over the export period, estimated from the tracer's latency buckets",
    ),
)

# (gauge name, quantile) estimated from the merged latency buckets
LATENCY_PERCENTILES = (("pipeline_latency_p50", 0.5), ("pipeline_latency_p95", 0.95), ("pipeline_latency_p99", 0.99))

# Reasons a period's latency distribution is not exported
NO_DISTRIBUTION = "window without latency distribution fields (older latency_tracer)"
MALFORMED_DISTRIBUTION = "malformed latency distribution fields"
MISMATCHED_BOUNDS = "latency windows with different bucket bounds"

# Explicit buckets for token counts; the SDK default buckets are meant for milliseconds.
TOKEN_BUCKETS = (0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536)

# genai-request field -> (histogram name, unit, description, bucket boundaries or None for the SDK default)
GENAI_HISTOGRAMS = {
    "ttft_ms": ("genai_ttft", "ms", "Time to first token of one generation request", None),
    "tpot_ms": ("genai_tpot", "ms", "Mean time per output token of one generation request", None),
    "generate_duration_ms": ("genai_generate_duration", "ms", "Duration of one generate() call", None),
    "inference_duration_ms": (
        "genai_inference_duration", "ms", "Model inference time of one generation request", None,
    ),
    "prepare_embeddings_duration_ms": (
        "genai_prepare_embeddings_duration", "ms", "Embedding preparation time of one generation request", None,
    ),
    "num_input_tokens": ("genai_input_tokens", "", "Input tokens of one generation request", TOKEN_BUCKETS),
    "num_generated_tokens": (
        "genai_generated_tokens", "", "Generated tokens of one generation request", TOKEN_BUCKETS,
    ),
}

Observation = Tuple[str, float, Dict[str, str]]

_warned_lock = threading.Lock()
_warned: Set[Tuple[str, str]] = set()


def _warn_unsupported_once(kind: str, version: Any) -> None:
    key = (kind, repr(version))
    with _warned_lock:
        if key in _warned:
            return
        _warned.add(key)
    if kind in SUPPORTED_VERSIONS:
        logger.warning(
            "Skipping %s%s messages with unsupported schema version %r (supported: %d)",
            METRIC_MESSAGE_PREFIX, kind, version, SUPPORTED_VERSIONS[kind],
        )
    else:
        logger.warning("Skipping %s%s messages: unknown metric kind", METRIC_MESSAGE_PREFIX, kind)


_distribution_warned: Set[str] = set()


def _warn_distribution_once(reason: str) -> None:
    with _warned_lock:
        if reason in _distribution_warned:
            return
        _distribution_warned.add(reason)
    logger.warning(
        "Not exporting latency stddev and percentiles for export periods with %s; avg, min and max are unaffected",
        reason,
    )


def metric_event(
    instance_id: str, element: Optional[str], structure_name: str, fields: Dict[str, Any]
) -> Optional[dict]:
    """Build the worker's ``metric`` event from a bus message, or None if it is not one.

    A message of an unknown kind or an unsupported schema version is skipped,
    with a warning logged once per kind and version, rather than misread.
    """
    if not structure_name.startswith(METRIC_MESSAGE_PREFIX):
        return None
    kind = structure_name[len(METRIC_MESSAGE_PREFIX):]
    version = fields.get("version")
    supported = SUPPORTED_VERSIONS.get(kind)
    if supported is None or isinstance(version, bool) or version != supported:
        _warn_unsupported_once(kind, version)
        return None
    return {
        "instance_id": instance_id,
        "event": "metric",
        "kind": kind,
        "element": element,
        "fields": {k: v for k, v in fields.items() if k != "version"},
    }


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _count(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    number = _finite(value)
    return int(number) if number is not None and number >= 0 and number.is_integer() else None


def _distribution(fields: Dict[str, Any], count: int) -> Tuple[Optional[tuple], Optional[str]]:
    """((sum_sq_ms, bounds, counts), None) of one window, or (None, reason) if it has no usable distribution."""
    if not all(name in fields for name in ("sum_sq_ms", "bucket_bounds_ms", "bucket_counts")):
        return None, NO_DISTRIBUTION
    sum_sq_ms = _finite(fields["sum_sq_ms"])
    raw_bounds, raw_counts = fields["bucket_bounds_ms"], fields["bucket_counts"]
    if sum_sq_ms is None or sum_sq_ms < 0 or not isinstance(raw_bounds, (list, tuple)) \
            or not isinstance(raw_counts, (list, tuple)):
        return None, MALFORMED_DISTRIBUTION
    bounds = tuple(_finite(b) for b in raw_bounds)
    counts = [_count(c) for c in raw_counts]
    if not bounds or None in bounds or None in counts or len(counts) != len(bounds) + 1 \
            or any(low >= high for low, high in zip(bounds, bounds[1:])) or sum(counts) != count:
        return None, MALFORMED_DISTRIBUTION
    return (sum_sq_ms, bounds, counts), None


@dataclass
class LatencyAccumulator:
    """Exact merge of latency windows: sums, counts and bucket counts add, extremes compare.

    The distribution (``sum_sq_ms`` and the buckets) is kept only while every
    merged window carries it with the same bucket bounds; one window without it,
    with other bounds or with malformed fields drops it for the whole period.
    """

    count: int = 0
    window_ms: float = 0.0
    sum_ms: float = 0.0
    min_ms: float = math.inf
    max_ms: float = 0.0
    sum_sq_ms: float = 0.0
    bucket_bounds_ms: Optional[Tuple[float, ...]] = None
    bucket_counts: Optional[List[int]] = None
    no_distribution: Optional[str] = None

    def add(self, fields: Dict[str, Any]) -> bool:
        """Merge one latency-window; returns False (and changes nothing) if it is malformed."""
        try:
            count = int(fields["count"])
        except (KeyError, TypeError, ValueError):
            return False
        sum_ms = _finite(fields.get("sum_ms"))
        min_ms = _finite(fields.get("min_ms"))
        max_ms = _finite(fields.get("max_ms"))
        window_ms = _finite(fields.get("window_ms"))
        if count <= 0 or sum_ms is None or min_ms is None or max_ms is None or window_ms is None:
            return False
        first = self.count == 0
        self.count += count
        self.window_ms += window_ms
        self.sum_ms += sum_ms
        self.min_ms = min(self.min_ms, min_ms)
        self.max_ms = max(self.max_ms, max_ms)
        self._add_distribution(fields, count, first)
        return True

    def _add_distribution(self, fields: Dict[str, Any], count: int, first: bool) -> None:
        if self.no_distribution is not None:
            return
        distribution, reason = _distribution(fields, count)
        if distribution is not None:
            sum_sq_ms, bounds, counts = distribution
            if first:
                self.sum_sq_ms, self.bucket_bounds_ms, self.bucket_counts = sum_sq_ms, bounds, counts
                return
            if bounds == self.bucket_bounds_ms:
                self.sum_sq_ms += sum_sq_ms
                self.bucket_counts = [a + b for a, b in zip(self.bucket_counts, counts)]
                return
            reason = MISMATCHED_BOUNDS
        self.no_distribution = reason
        self.sum_sq_ms, self.bucket_bounds_ms, self.bucket_counts = 0.0, None, None
        _warn_distribution_once(reason)

    @property
    def avg_ms(self) -> float:
        return self.sum_ms / self.count

    @property
    def has_distribution(self) -> bool:
        return self.count > 0 and self.no_distribution is None and self.bucket_counts is not None

    @property
    def stddev_ms(self) -> float:
        """Population standard deviation, exact from the summed squares."""
        mean = self.avg_ms
        return math.sqrt(max(0.0, self.sum_sq_ms / self.count - mean * mean))

    def percentile_ms(self, quantile: float) -> float:
        """Estimate a quantile from the merged buckets, interpolating linearly inside one bucket.

        As Prometheus ``histogram_quantile``, except that the first bucket starts
        at the merged minimum and the overflow bucket ends at the merged maximum.
        The result is clamped to [min, max].
        """
        bounds, counts = self.bucket_bounds_ms, self.bucket_counts
        rank = quantile * self.count
        cumulative = 0
        for index, bucket_count in enumerate(counts):
            if bucket_count and cumulative + bucket_count >= rank:
                lower = bounds[index - 1] if index > 0 else self.min_ms
                upper = bounds[index] if index < len(bounds) else self.max_ms
                estimate = lower + (upper - lower) * (rank - cumulative) / bucket_count
                return min(max(estimate, self.min_ms), self.max_ms)
            cumulative += bucket_count
        return self.max_ms

    def observations(self, attrs: Dict[str, str]) -> List[Observation]:
        observations = [
            ("pipeline_latency_avg", self.avg_ms, attrs),
            ("pipeline_latency_min", self.min_ms, attrs),
            ("pipeline_latency_max", self.max_ms, attrs),
            ("pipeline_latency_frames", float(self.count), attrs),
            ("pipeline_latency_window", self.window_ms, attrs),
        ]
        if self.has_distribution:
            observations.append(("pipeline_latency_stddev", self.stddev_ms, attrs))
            observations.extend((name, self.percentile_ms(q), attrs) for name, q in LATENCY_PERCENTILES)
        return observations


class LatencyWindows:
    """Latency windows received since the last drain, merged per instance and branch."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: Dict[Tuple[str, str, str], LatencyAccumulator] = {}

    def add(self, instance_id: str, fields: Dict[str, Any]) -> None:
        key = (instance_id, str(fields.get("source", "")), str(fields.get("sink", "")))
        with self._lock:
            accumulator = self._pending.get(key) or LatencyAccumulator()
            if accumulator.add(fields):
                self._pending[key] = accumulator

    def drain(self) -> List[Observation]:
        """Return merged observations for everything received since the previous drain."""
        with self._lock:
            pending, self._pending = self._pending, {}
        observations: List[Observation] = []
        for (instance_id, source, sink), accumulator in pending.items():
            attrs = {"pipeline_id": instance_id, "source": source, "sink": sink}
            observations.extend(accumulator.observations(attrs))
        return observations


def genai_values(fields: Dict[str, Any]) -> List[Tuple[str, float]]:
    """(histogram name, value) pairs of one genai-request; missing or non-finite fields are skipped."""
    values = []
    for field_name, (histogram, _unit, _description, _buckets) in GENAI_HISTOGRAMS.items():
        value = _finite(fields.get(field_name))
        if value is not None:
            values.append((histogram, value))
    return values
