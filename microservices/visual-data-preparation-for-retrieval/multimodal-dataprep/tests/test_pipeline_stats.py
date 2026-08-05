# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for pipeline telemetry math in ``embedding_helper``.

These lock in the fix for a ``ZeroDivisionError`` that crashed the result-worker
thread (and stalled the request) whenever a pipeline stage recorded zero elapsed
time or zero items — most notably when object detection is disabled, leaving the
detect stage with a ``total`` of ``0``.
"""

from src.core.embedding.embedding_helper import _safe_div, _summarize_stage_times


def test_safe_div_zero_denominator_returns_zero():
    """A zero denominator yields ``0.0`` instead of raising ``ZeroDivisionError``."""
    assert _safe_div(10.0, 0) == 0.0
    assert _safe_div(0, 0) == 0.0


def test_safe_div_normal_division():
    """A non-zero denominator divides normally."""
    assert _safe_div(10.0, 2.0) == 5.0
    assert _safe_div(3.0, 4.0) == 0.75


def test_summarize_stage_times_empty_has_zero_total():
    """An empty sample set reports a zero ``total`` that ``_safe_div`` tolerates."""
    summary = _summarize_stage_times([])
    assert summary["total"] == 0.0
    # Simulates the detect-stage throughput calc when detection is disabled.
    assert _safe_div(100, summary["total"]) == 0.0
