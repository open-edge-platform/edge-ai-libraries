# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Sliding-window aggregation, one bounded series per discovered field name."""
from __future__ import annotations

import logging
import statistics
from collections import deque
from typing import Deque, Dict


logger = logging.getLogger(__name__)

# Aggregation methods supported by ``method:`` in the aggregate spec.
_SUPPORTED_METHODS = frozenset(
    {"latest", "mean", "median", "p50", "p90", "p95", "p99", "ewma", "min", "max", "stdev"}
)


class MetricAggregator:
    """Aggregate each named series over its own sliding window.

    Every field name gets an independent bounded window; ``values()`` reduces
    each window to a single number using the configured ``method``. The total
    number of distinct series is capped (``max_series``) so a broad regex can't
    create a runaway number of windows.
    """

    def __init__(self, window: int, method: str, max_series: int):
        self.window = window
        self.method = method if method in _SUPPORTED_METHODS else "mean"
        if method not in _SUPPORTED_METHODS:
            logger.warning(
                "unknown aggregate method %r; falling back to 'mean'", method
            )
        self.max_series = max_series
        self._series: Dict[str, Deque[float]] = {}
        self._capped_warned = False

    def add(self, fields: Dict[str, float]) -> None:
        """Append this tick's ``{name: value}`` samples to their windows."""
        for name, value in fields.items():
            series = self._series.get(name)
            if series is None:
                if len(self._series) >= self.max_series:
                    if not self._capped_warned:
                        logger.warning(
                            "probe series cardinality cap (%d) reached; "
                            "dropping new series %r and beyond",
                            self.max_series, name,
                        )
                        self._capped_warned = True
                    continue
                series = deque(maxlen=self.window)
                self._series[name] = series
            series.append(value)

    def values(self) -> Dict[str, float]:
        """Reduce every window to a single aggregate under the configured method."""
        return {name: self._reduce(samples) for name, samples in self._series.items()}

    def _reduce(self, samples: Deque[float]) -> float:
        data = list(samples)
        method = self.method
        if not data:
            return 0.0
        if method == "latest":
            # Publish the most recent sample; the window still bounds retention
            # so a miss keeps the last good value until the next successful tick.
            return data[-1]
        if method in ("mean",):
            return statistics.fmean(data)
        if method in ("median", "p50"):
            return statistics.median(data)
        if method == "min":
            return min(data)
        if method == "max":
            return max(data)
        if method == "stdev":
            return statistics.pstdev(data) if len(data) > 1 else 0.0
        if method == "ewma":
            return self._ewma(data)
        if method in ("p90", "p95", "p99"):
            return self._percentile(data, int(method[1:]))
        return statistics.fmean(data)

    @staticmethod
    def _ewma(data: list[float]) -> float:
        """Exponentially weighted mean over the window (recent samples weigh more)."""
        alpha = 2.0 / (len(data) + 1.0)
        acc = data[0]
        for value in data[1:]:
            acc = alpha * value + (1.0 - alpha) * acc
        return acc

    @staticmethod
    def _percentile(data: list[float], pct: int) -> float:
        """Linear-interpolated percentile (nearest-rank for tiny windows)."""
        ordered = sorted(data)
        if len(ordered) == 1:
            return ordered[0]
        rank = (pct / 100.0) * (len(ordered) - 1)
        low = int(rank)
        high = min(low + 1, len(ordered) - 1)
        frac = rank - low
        return ordered[low] + (ordered[high] - ordered[low]) * frac
