"""Score computation and aggregation for benchmark runs.

A benchmark score has three components:

- ``performance`` - raw throughput (total FPS).
- ``efficiency`` - throughput per unit of resource cost (FPS per Watt, or FPS
  per mean utilization percent when power is unavailable).
- ``total`` - the geometric mean of performance and efficiency, so a workload
  cannot mask a poor efficiency score with a large FPS number (or vice versa).

The same shape is used at every level: per test case, per workload (aggregating
its test cases) and per suite (aggregating its workloads).
"""

import math
from typing import Protocol


class _ScoredRun(Protocol):
    """A run that carries a status and per-component scores."""

    status: str
    score_performance: float | None
    score_efficiency: float | None


def geometric_total(
    performance: float | None, efficiency: float | None
) -> float | None:
    """Return the geometric mean of two positive scores, or ``None``.

    Args:
        performance: Performance component.
        efficiency: Efficiency component.

    Returns:
        ``sqrt(performance * efficiency)`` when both are present and positive,
        otherwise ``None``.
    """
    if (
        performance is not None
        and efficiency is not None
        and performance > 0
        and efficiency > 0
    ):
        return math.sqrt(performance * efficiency)
    return None


def compute_test_case_scores(
    total_fps: float | None,
    cpu_usage: float | None,
    gpu_usage: float | None,
    npu_usage: float | None,
    media_usage: float | None,
    power_usage: float | None,
) -> tuple[float | None, float | None, float | None]:
    """Compute ``(performance, efficiency, total)`` for one completed test case.

    Efficiency prefers FPS-per-Watt and falls back to FPS per mean non-zero
    utilization (cpu/gpu/npu/media) when power is not measured. Returns
    ``(None, None, None)`` when there is no positive throughput.

    Args:
        total_fps: Total pipeline throughput in frames per second.
        cpu_usage: Mean CPU utilization percent, or ``None``.
        gpu_usage: Mean GPU utilization percent, or ``None``.
        npu_usage: Mean NPU utilization percent, or ``None``.
        media_usage: Mean media-engine utilization percent, or ``None``.
        power_usage: Mean package power in watts, or ``None``.

    Returns:
        Tuple of ``(score_performance, score_efficiency, score_total)``.
    """
    if total_fps is None or total_fps <= 0:
        return None, None, None

    score_performance = float(total_fps)

    score_efficiency: float | None = None
    if power_usage is not None and power_usage > 0:
        score_efficiency = score_performance / float(power_usage)
    else:
        utilizations = [
            float(v)
            for v in (cpu_usage, gpu_usage, npu_usage, media_usage)
            if v is not None and v > 0
        ]
        if utilizations:
            avg_utilization = sum(utilizations) / len(utilizations)
            score_efficiency = score_performance / avg_utilization

    return (
        score_performance,
        score_efficiency,
        geometric_total(score_performance, score_efficiency),
    )


def aggregate_scores(
    runs: list[_ScoredRun],
) -> tuple[float | None, float | None, float | None]:
    """Aggregate child run scores into a parent-level score.

    Only ``completed`` runs contribute. Performance and efficiency are averaged
    independently (skipping ``None`` entries) and the total is the geometric
    mean of the two aggregates, mirroring :func:`compute_test_case_scores`.

    Args:
        runs: Child runs exposing ``status``, ``score_performance`` and
            ``score_efficiency``.

    Returns:
        Tuple of ``(score_performance, score_efficiency, score_total)``.
    """
    performance_values = [
        run.score_performance
        for run in runs
        if run.status == "completed" and run.score_performance is not None
    ]
    efficiency_values = [
        run.score_efficiency
        for run in runs
        if run.status == "completed" and run.score_efficiency is not None
    ]

    score_performance = (
        sum(performance_values) / len(performance_values)
        if performance_values
        else None
    )
    score_efficiency = (
        sum(efficiency_values) / len(efficiency_values) if efficiency_values else None
    )

    return (
        score_performance,
        score_efficiency,
        geometric_total(score_performance, score_efficiency),
    )
