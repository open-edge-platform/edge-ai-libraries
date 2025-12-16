# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Utility helpers to convert ov_genai performance metrics into API models."""

from __future__ import annotations

import asyncio
import inspect
from typing import Optional, Tuple

import openvino_genai as ov_genai

from src.utils.common import logger
from src.utils.data_models import ChatUsageStats, TelemetryMetrics


def _safe_call(getter, default=None):
    """Invoke a PerfMetrics getter defensively.

    Args:
        getter: Callable that returns a scalar or MeanStdPair from ``ov_genai.PerfMetrics``.
        default: Value to return when the getter raises (networked pipelines occasionally expose
            partially-populated metrics, so we avoid surfacing tracebacks to clients).

    Returns:
        The getter output if successful, otherwise ``default``.
    """
    try:
        result = getter()
        # Some pipelines expose async-aware metrics or temporarily omit values; treat anything
        # unusual as best-effort and avoid surfacing warnings/exceptions to API consumers.
        if inspect.isawaitable(result):
            if asyncio.iscoroutine(result):
                result.close()
            logger.debug(
                "Perf metric getter %s produced awaitable; ignoring",
                getattr(getter, "__name__", getter),
            )
            return default
        return result
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.debug("Failed to read perf metric via %s: %s", getattr(getter, "__name__", getter), exc)
        return default


def _extract_mean_std(pair) -> Tuple[Optional[float], Optional[float]]:
    """Normalize a MeanStd-like object into plain floats.

    Args:
        pair: Object with ``mean`` and ``std`` attributes (e.g., ``MeanStdPair``).

    Returns:
        Tuple of ``(mean, std)`` in milliseconds/tokens/s, or (None, None) when unavailable.
    """
    if pair is None:
        return None, None
    mean = getattr(pair, "mean", None)
    std = getattr(pair, "std", None)
    return mean, std


def build_usage_and_telemetry(
    perf_metrics: Optional[ov_genai.PerfMetrics],
) -> Tuple[Optional[ChatUsageStats], Optional[TelemetryMetrics]]:
    """Convert ``ov_genai`` perf metrics into API response shapes.

    Args:
        perf_metrics: Optional PerfMetrics emitted by ``pipe.generate``. ``None`` indicates metrics
            were not produced (e.g., legacy pipeline or streaming errors).

    Returns:
        Tuple of ``(ChatUsageStats, TelemetryMetrics)``; elements are ``None`` when the pipeline
        did not expose metrics.
    """

    if perf_metrics is None:
        return None, None

    prompt_tokens = _safe_call(perf_metrics.get_num_input_tokens)
    completion_tokens = _safe_call(perf_metrics.get_num_generated_tokens)
    total_tokens = 0
    if prompt_tokens is not None or completion_tokens is not None:
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

    # Throughput helps callers compute cost per token; std indicates variance across long outputs.
    throughput_mean, throughput_std = _extract_mean_std(
        _safe_call(perf_metrics.get_throughput)
    )
    ttft_mean, ttft_std = _extract_mean_std(_safe_call(perf_metrics.get_ttft))
    tpot_mean, tpot_std = _extract_mean_std(_safe_call(perf_metrics.get_tpot))
    generate_mean, generate_std = _extract_mean_std(
        _safe_call(perf_metrics.get_generate_duration)
    )
    tokenization_mean, tokenization_std = _extract_mean_std(
        _safe_call(perf_metrics.get_tokenization_duration)
    )
    detokenization_mean, detokenization_std = _extract_mean_std(
        _safe_call(perf_metrics.get_detokenization_duration)
    )
    embeddings_mean, embeddings_std = _extract_mean_std(
        _safe_call(perf_metrics.get_prepare_embeddings_duration)
    )

    usage = ChatUsageStats(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        tps=throughput_mean,
        time_to_first_token=ttft_mean,
        latency=generate_mean,
    )

    telemetry = TelemetryMetrics(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        load_time_ms=_safe_call(perf_metrics.get_load_time),
        generate_time_ms=generate_mean,
        generate_time_std_ms=generate_std,
        tokenization_time_ms=tokenization_mean,
        tokenization_time_std_ms=tokenization_std,
        detokenization_time_ms=detokenization_mean,
        detokenization_time_std_ms=detokenization_std,
        embeddings_prep_time_ms=embeddings_mean,
        embeddings_prep_time_std_ms=embeddings_std,
        ttft_ms=ttft_mean,
        ttft_std_ms=ttft_std,
        tpot_ms=tpot_mean,
        tpot_std_ms=tpot_std,
        throughput_tps=throughput_mean,
        throughput_std_tps=throughput_std,
    )

    return usage, telemetry
