"""Telegraf/InfluxDB metric parsing and per-engine usage extraction for benchmarks.

This module contains the pure functions used by ``BenchmarkManager`` to turn the
raw metrics text collected during a performance run into averaged per-engine
utilization figures (CPU, GPU, NPU, media, memory and power).

All functions are side-effect free and operate on already parsed metric events
(``list[dict]``) so the same parsed payload can be reused across extractors.
"""

import json
import logging

logger = logging.getLogger("benchmark_metrics")

# Fraction of samples trimmed from each end before averaging to discard
# ramp-up/ramp-down outliers.
TRIM_FRACTION = 0.1

# Telegraf metric names.
_CPU_METRIC = "cpu_usage_user"
_MEMORY_METRIC = "mem_used_percent"
_NPU_METRIC = "npu_utilization"
_GPU_ENGINE_METRIC = "gpu_engine_usage_usage"
_GPU_POWER_METRIC = "gpu_power"

# GPU engine label groups.
_GPU_COMPUTE_LABELS = {"compute", "ccs"}
_GPU_RENDER_LABELS = {"render", "rcs"}
_MEDIA_ENGINE_LABELS = ("video", "vcs", "video-enhance", "vecs")


def parse_metrics_text(metrics_text: str | None) -> list[dict]:
    """Parse the raw metrics JSON text into a list of metric event dicts.

    Args:
        metrics_text: JSON encoded list of metric events, or ``None``.

    Returns:
        A list of dict events. Returns an empty list when the text is missing,
        cannot be decoded, or is not a JSON list.
    """
    if not metrics_text:
        logger.warning("parse_metrics_text: metrics_text is None or empty")
        return []

    try:
        parsed = json.loads(metrics_text)
    except Exception as e:
        logger.error(f"parse_metrics_text: Failed to parse JSON: {e}")
        return []

    if not isinstance(parsed, list):
        logger.warning(f"parse_metrics_text: Expected list, got {type(parsed)}")
        return []

    result = [item for item in parsed if isinstance(item, dict)]
    logger.debug(
        f"parse_metrics_text: Parsed {len(result)} dict items from {len(parsed)} total items"
    )
    return result


def _extract_metric_field_value(metric: dict, field_key: str) -> float | None:
    """Return the numeric value carried by a single metric entry.

    Looks for the value under ``fields.value``, ``fields.<field_key>``, a single
    ``fields`` entry, or a top-level ``value`` key, in that order.

    Args:
        metric: A single metric dict.
        field_key: The metric name, used as a fallback field key.

    Returns:
        The value as a float, or ``None`` when no numeric value is present.
    """
    fields = metric.get("fields")
    raw_value = None
    if isinstance(fields, dict):
        if "value" in fields:
            raw_value = fields.get("value")
        elif field_key in fields:
            raw_value = fields.get(field_key)
        elif len(fields) == 1:
            raw_value = next(iter(fields.values()))
    elif "value" in metric:
        raw_value = metric.get("value")

    if isinstance(raw_value, (int, float)):
        return float(raw_value)
    return None


def _collect_metric_values(parsed_metrics: list[dict], metric_name: str) -> list[float]:
    """Collect every numeric sample for ``metric_name`` across all events."""
    values: list[float] = []

    for event in parsed_metrics:
        metrics = event.get("metrics")
        if not isinstance(metrics, list):
            continue

        for metric in metrics:
            if not isinstance(metric, dict) or metric.get("name") != metric_name:
                continue

            value = _extract_metric_field_value(metric, metric_name)
            if value is not None:
                values.append(value)

    return values


def _trim_metric_edge_values(values: list[float]) -> list[float]:
    """Trim ``TRIM_FRACTION`` of the samples from each end of ``values``."""
    if not values:
        logger.debug("_trim_metric_edge_values: Empty values list")
        return []

    trim_count = int(len(values) * TRIM_FRACTION)
    if trim_count == 0 or trim_count * 2 >= len(values):
        logger.debug(
            f"_trim_metric_edge_values: Not trimming (len={len(values)}, trim_count={trim_count})"
        )
        return values

    trimmed = values[trim_count:-trim_count]
    logger.debug(
        f"_trim_metric_edge_values: Trimmed {trim_count} items from each end "
        f"(before={len(values)}, after={len(trimmed)})"
    )
    return trimmed


def _mean_of_trimmed(values: list[float]) -> float | None:
    """Return the mean of ``values`` after edge trimming, or ``None`` if empty."""
    trimmed_values = _trim_metric_edge_values(values)
    if not trimmed_values:
        return None
    return sum(trimmed_values) / len(trimmed_values)


def average_metric(parsed_metrics: list[dict], metric_name: str) -> float | None:
    """Return the trimmed mean of a single named metric."""
    return _mean_of_trimmed(_collect_metric_values(parsed_metrics, metric_name))


def _iter_engine_samples(parsed_metrics: list[dict]):
    """Yield ``(engine_label, value)`` pairs for every GPU engine usage sample.

    Shared by the GPU and media extractors, which both bucket
    ``gpu_engine_usage_usage`` samples by their engine label.
    """
    for event in parsed_metrics:
        if not isinstance(event, dict):
            continue

        metrics = event.get("metrics")
        if isinstance(metrics, list):
            metric_entries = metrics
        elif event.get("name") == _GPU_ENGINE_METRIC:
            metric_entries = [event]
        else:
            continue

        for metric in metric_entries:
            if not isinstance(metric, dict) or metric.get("name") != _GPU_ENGINE_METRIC:
                continue

            labels = metric.get("labels")
            engine = metric.get("engine")
            engine_label = None

            if isinstance(labels, dict):
                engine_label = labels.get("engine") or labels.get("engine.labels")

            if engine_label is None and isinstance(engine, dict):
                engine_label = engine.get("labels")

            value = _extract_metric_field_value(metric, _GPU_ENGINE_METRIC)
            if value is None:
                continue

            yield engine_label, value


def cpu_usage(parsed_metrics: list[dict]) -> float | None:
    """Average CPU utilization (percent)."""
    return average_metric(parsed_metrics, _CPU_METRIC)


def memory_usage(parsed_metrics: list[dict]) -> float | None:
    """Average memory utilization (percent)."""
    return average_metric(parsed_metrics, _MEMORY_METRIC)


def npu_usage(parsed_metrics: list[dict]) -> float | None:
    """Average NPU utilization (percent)."""
    return average_metric(parsed_metrics, _NPU_METRIC)


def gpu_usage(parsed_metrics: list[dict]) -> float | None:
    """Average GPU compute utilization (percent).

    Prefers the compute/ccs engines and falls back to render/rcs, selecting the
    engine set with the most non-zero samples (ties favouring compute/ccs).
    """
    primary_values: list[float] = []
    fallback_values: list[float] = []

    for engine_label, value in _iter_engine_samples(parsed_metrics):
        if engine_label in _GPU_COMPUTE_LABELS:
            primary_values.append(value)
        elif engine_label in _GPU_RENDER_LABELS:
            fallback_values.append(value)

    # Phase 1: select the set with the most non-zero values.
    # Break ties by preferring compute/ccs over render/rcs.
    nonzero_primary_count = sum(1 for v in primary_values if v > 0)
    nonzero_fallback_count = sum(1 for v in fallback_values if v > 0)
    if nonzero_primary_count >= nonzero_fallback_count and nonzero_primary_count > 0:
        selected_values = primary_values
    elif nonzero_fallback_count > 0:
        selected_values = fallback_values
    else:
        selected_values = primary_values or fallback_values

    # Phase 2: calculate the average from the selected set.
    return _mean_of_trimmed(selected_values)


def media_usage(parsed_metrics: list[dict]) -> float | None:
    """Average media-engine utilization (percent).

    Groups samples by supported media engine label and returns the highest
    trimmed average, because different platforms report the same workload under
    different engine buckets.
    """
    buckets: dict[str, list[float]] = {label: [] for label in _MEDIA_ENGINE_LABELS}

    for engine_label, value in _iter_engine_samples(parsed_metrics):
        if engine_label in buckets:
            buckets[engine_label].append(value)

    averages = [
        avg
        for avg in (_mean_of_trimmed(values) for values in buckets.values())
        if avg is not None
    ]
    if not averages:
        return None

    return max(averages)


def power_usage(parsed_metrics: list[dict]) -> float | None:
    """Average package power draw (watts) from ``gpu_power`` / ``pkg_cur_power``."""
    values: list[float] = []

    for event in parsed_metrics:
        metrics = event.get("metrics")
        if not isinstance(metrics, list):
            continue

        for metric in metrics:
            if not isinstance(metric, dict) or metric.get("name") != _GPU_POWER_METRIC:
                continue

            labels = metric.get("labels")
            if not isinstance(labels, dict) or labels.get("type") != "pkg_cur_power":
                continue

            value = _extract_metric_field_value(metric, _GPU_POWER_METRIC)
            if value is not None:
                values.append(value)

    return _mean_of_trimmed(values)
