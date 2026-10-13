# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Hardware Metrics Monitor.

Samples CPU, GPU (Xe), and NPU KPIs in a background thread during benchmark runs.
Source: VIPPET metrics-manager JSON API (CPU, GPU, NPU, memory, temperature, power).
"""

import json
import logging
import threading
import time
import warnings
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Fraction of time-ordered samples trimmed from each end before averaging,
# to discard warm-up/wind-down outliers. Mirrors
# ``managers.benchmark_metrics.TRIM_FRACTION`` — VIPPET's built-in benchmark
# applies the same edge trimming before averaging.
DEFAULT_TRIM_FRACTION = 0.1

# Per-family KPI keys collected into the aggregated hw_metrics dict (without
# the _avg/_min/_max suffixes added by `_aggregate`). Used both to compute
# each family's per-sample count and, by reporters.py, to map a CSV/HTML
# column back to the device family it belongs to.
FAMILY_KPI_KEYS: dict[str, tuple[str, ...]] = {
    "CPU": ("cpu_util_pct", "cpu_freq_mhz", "cpu_temperature", "mem_used_percent"),
    "GPU": (
        "gpu_render_util_pct",
        "gpu_video_util_pct",
        "gpu_enhance_util_pct",
        "gpu_compute_util_pct",
        "gpu_copy_util_pct",
        "gpu_util_combined",
        "gpu_freq_mhz",
        "gpu_power_w",
        "pkg_power_w",
    ),
    "NPU": (
        "npu_utilization",
        "npu_power",
        "npu_frequency",
        "npu_temperature",
        "npu_memory_mb",
        "npu_bandwidth",
    ),
}

# Keys whose value, if ever nonzero across the run, proves the family's
# hardware was actually doing work. Checked as a union (not a strict
# ordered fallback): the first key with a nonzero value anywhere decides
# "ok". This deliberately looks across *all* of a GPU's per-engine
# utilization keys rather than just "render", because
# ``gpu_render_util_pct`` has been observed to always read 0 on tested
# hardware (see the TODO in ``_collect`` below) — relying on it alone
# would misclassify an active GPU as idle.
#
# For NPU this set is exactly "npu_utilization, falling back to
# npu_frequency / npu_power" as specced: if utilization is always 0/absent,
# a nonzero frequency or power reading still proves the NPU was awake.
FAMILY_ACTIVITY_KEYS: dict[str, tuple[str, ...]] = {
    "CPU": ("cpu_util_pct",),
    "GPU": (
        "gpu_render_util_pct",
        "gpu_video_util_pct",
        "gpu_enhance_util_pct",
        "gpu_compute_util_pct",
        "gpu_copy_util_pct",
    ),
    "NPU": ("npu_utilization", "npu_frequency", "npu_power"),
}


def _fetch_metrics_manager(url: str) -> dict[str, float]:
    """Fetch latest metrics from VIPPET metrics-manager JSON API.

    Returns flat dict of metric_key -> value.
    Tagged metrics use composite keys (e.g. gpu_power__gpu_cur_power).
    Only gpu_id=0 is collected for GPU metrics with multiple IDs.

    Handles two response formats:
      - SSE stream (``data: {json}\\n``) — reads the last complete event
      - Plain JSON with ``metrics`` as a list or dict
    """
    try:
        raw = ""
        for attempt in range(3):
            with httpx.stream("GET", url, timeout=5) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if line.startswith("data: "):
                        raw = line[6:]
                        break
            if raw:
                break
            time.sleep(1)

        if not raw:
            return {}

        data = json.loads(raw)
        metrics = data.get("metrics", data)
        result: dict[str, float] = {}

        if isinstance(metrics, list):
            for entry in metrics:
                name = entry.get("name", "")
                val = entry.get("value")
                if val is None or not name:
                    continue
                labels = entry.get("labels", {})

                gpu_id = labels.get("gpu_id")
                if gpu_id is not None and gpu_id != "0":
                    continue

                type_tag = labels.get("type") or labels.get("engine")
                composite = f"{name}__{type_tag}" if type_tag else name
                result[composite] = float(val)
        elif isinstance(metrics, dict):
            for key, entry in metrics.items():
                if isinstance(entry, dict):
                    val = entry.get("fields", {}).get("value")
                    if val is None:
                        continue
                    name = entry.get("name", key.split("{")[0])
                    tags = entry.get("tags", {})

                    gpu_id = tags.get("gpu_id")
                    if gpu_id is not None and gpu_id != "0":
                        continue

                    type_tag = tags.get("type") or tags.get("engine")
                    composite = f"{name}__{type_tag}" if type_tag else name
                    result[composite] = float(val)
                elif isinstance(entry, (int, float)):
                    result[key] = float(entry)

        return result
    except Exception as e:
        logger.debug("metrics-manager fetch failed: %s", e)
        return {}


def _trim_edge_samples(
    samples: list[dict[str, float]], trim_fraction: float
) -> list[dict[str, float]]:
    """Trim ``trim_fraction`` of the time-ordered *samples* from each end.

    This copies the logic of ``managers.benchmark_metrics._trim_metric_edge_values``
    (VIPPET's built-in benchmark trimming) rather than importing it, because
    this harness runs as an external HTTP client against a deployed VIPPET
    instance and does not import its internal modules.
    """
    if not samples:
        return []
    trim_count = int(len(samples) * trim_fraction)
    if trim_count == 0 or trim_count * 2 >= len(samples):
        return samples
    return samples[trim_count:-trim_count]


def _family_sample_count(samples: list[dict[str, float]], family: str) -> int:
    """Count samples that reported at least one of *family*'s KPI keys."""
    keys = FAMILY_KPI_KEYS.get(family, ())
    return sum(1 for s in samples if any(k in s for k in keys))


def _family_kpi_status(samples: list[dict[str, float]], family: str) -> str:
    """Classify *family*'s hardware activity across the sampled run.

    Returns one of:
      - ``"no_samples"``: none of the family's activity keys were ever
        reported by metrics-manager (missing hardware, unwired sensor, or
        the harness never got a single successful poll).
      - ``"idle"``: samples exist for the family but every activity value
        was zero for the whole run (hardware present but never dispatched
        work — e.g. a pipeline variant that doesn't actually run inference
        on this device).
      - ``"ok"``: at least one activity value was nonzero somewhere in the
        run.
    """
    activity_keys = FAMILY_ACTIVITY_KEYS.get(family, ())
    present = False
    for key in activity_keys:
        for s in samples:
            if key in s:
                present = True
                if s[key] != 0:
                    return "ok"
    return "idle" if present else "no_samples"


class HardwareMonitor:
    """Background-thread hardware sampler.

    Usage:
        monitor = HardwareMonitor("http://localhost/metrics/stream")
        monitor.start()
        ... run workload ...
        hw_stats = monitor.stop(["GPU", "NPU"])   # returns aggregated dict
    """

    def __init__(
        self,
        metrics_url: str = "http://localhost/metrics/stream",
        sample_interval: float = 2.0,
        trim_fraction: float = DEFAULT_TRIM_FRACTION,
    ):
        self._metrics_url = metrics_url
        self._interval = sample_interval
        self._trim_fraction = trim_fraction
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._samples: list[dict[str, float]] = []

    def start(self) -> None:
        self._stop.clear()
        self._samples.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="hw-monitor"
        )
        self._thread.start()
        logger.debug("HardwareMonitor started (interval=%.1fs)", self._interval)

    def stop(self, families: list[str] | None = None) -> dict[str, Any]:
        """Stop sampling and return the aggregated hardware stats.

        Args:
            families: Device families the caller expects data for (e.g.
                ``["GPU", "NPU"]`` — typically
                ``pipeline_case.device_family.split("_")``). When given,
                the result carries a per-family ``kpi_status`` (``ok`` /
                ``no_samples`` / ``idle``), a per-family sample count
                (``<family>_sample_count``, lowercased), and a
                ``kpi_warnings`` summary string. A warning is logged and
                raised via :mod:`warnings` for any requested family whose
                status isn't ``ok`` — so missing/idle hardware shows up in
                the pytest summary instead of silently producing blank
                report cells.
        """
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=max(self._interval * 2, 10))
        stats = self._aggregate(families or [])
        logger.debug("HardwareMonitor stopped (%d samples)", len(self._samples))

        for family, status in stats.get("kpi_status", {}).items():
            if status == "ok":
                continue
            count = stats.get(f"{family.lower()}_sample_count", 0)
            message = (
                f"HardwareMonitor: device family {family!r} reported "
                f"kpi_status={status!r} ({count} of {stats.get('sample_count', 0)} "
                f"sample(s) carried a {family} KPI key)"
            )
            logger.warning(message)
            warnings.warn(message, stacklevel=2)

        return stats

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                sample = self._collect()
                if sample:
                    self._samples.append(sample)
            except Exception as e:
                logger.debug("hw sample error: %s", e)
            self._stop.wait(self._interval)

    def _collect(self) -> dict[str, float]:
        sample: dict[str, float] = {}

        mm = _fetch_metrics_manager(self._metrics_url)

        # CPU
        idle = mm.get("cpu_usage_idle")
        if idle is not None:
            sample["cpu_util_pct"] = round(100.0 - idle, 2)
        for key in ("cpu_usage_user", "cpu_usage_system", "mem_used_percent"):
            if key in mm:
                sample[key] = mm[key]
        freq = mm.get("cpu_frequency_avg_frequency")
        if freq is not None:
            sample["cpu_freq_mhz"] = round(freq / 1000.0, 0)
        temp = mm.get("temp_temp")
        if temp is not None:
            sample["cpu_temperature"] = temp

        # GPU (Xe/i915) — per-engine utilization.
        # NOTE: ``gpu_render_util_pct`` (engine="render"/"rcs") has been
        # observed to always read 0 on tested hardware, even when the GPU
        # is clearly busy per "video"/"compute". This looks like an
        # upstream qmassa/metrics-manager reporting gap for the render
        # engine specifically, not a bug in this harness — tracked as a
        # separate follow-up issue rather than fixed here. The per-family
        # activity check (FAMILY_ACTIVITY_KEYS) deliberately unions across
        # all GPU engine keys so this doesn't cause false "idle" GPU
        # classifications.
        for label, aliases in [
            ("gpu_render_util_pct", ("render", "rcs")),
            ("gpu_video_util_pct", ("video", "vcs")),
            ("gpu_enhance_util_pct", ("video-enhance", "vecs")),
            ("gpu_compute_util_pct", ("compute", "ccs")),
            ("gpu_copy_util_pct", ("copy", "bcs")),
        ]:
            for engine in aliases:
                val = mm.get(f"gpu_engine_usage_usage__{engine}")
                if val is not None:
                    sample[label] = round(val, 2)
                    break

        # GPU frequency
        val = mm.get("gpu_frequency__cur_freq")
        if val is not None:
            sample["gpu_freq_mhz"] = val

        # GPU power
        val = mm.get("gpu_power__gpu_cur_power")
        if val is not None:
            sample["gpu_power_w"] = round(val, 3)
        val = mm.get("gpu_power__pkg_cur_power")
        if val is not None:
            sample["pkg_power_w"] = round(val, 3)

        # NPU
        for key in (
            "npu_utilization",
            "npu_frequency",
            "npu_power",
            "npu_temperature",
            "npu_memory_mb",
            "npu_bandwidth",
        ):
            if key in mm:
                sample[key] = mm[key]

        return sample

    def _aggregate(self, families: list[str]) -> dict[str, Any]:
        agg: dict[str, Any] = {"sample_count": len(self._samples)}

        if self._samples:
            # Trim warm-up/wind-down samples from both ends before
            # averaging (see DEFAULT_TRIM_FRACTION / _trim_edge_samples).
            # _min / _max are computed from the *untrimmed* samples so a
            # real transient peak still shows in the report.
            trimmed = _trim_edge_samples(self._samples, self._trim_fraction)

            keys: set[str] = set()
            for s in self._samples:
                keys.update(s.keys())

            for key in sorted(keys):
                all_values = [s[key] for s in self._samples if key in s]
                if not all_values:
                    continue
                trimmed_values = [s[key] for s in trimmed if key in s]
                avg_source = trimmed_values or all_values
                agg[f"{key}_avg"] = round(sum(avg_source) / len(avg_source), 2)
                agg[f"{key}_min"] = round(min(all_values), 2)
                agg[f"{key}_max"] = round(max(all_values), 2)

            # Combined GPU utilization: max(render, video) per sample, then
            # averaged (over the trimmed samples); max is over all samples.
            combined_all = []
            for s in self._samples:
                render = s.get("gpu_render_util_pct")
                video = s.get("gpu_video_util_pct")
                vals = [v for v in (render, video) if v is not None]
                if vals:
                    combined_all.append(max(vals))
            if combined_all:
                agg["gpu_util_combined_max"] = round(max(combined_all), 2)

                combined_trimmed = []
                for s in trimmed:
                    render = s.get("gpu_render_util_pct")
                    video = s.get("gpu_video_util_pct")
                    vals = [v for v in (render, video) if v is not None]
                    if vals:
                        combined_trimmed.append(max(vals))
                combined_avg_source = combined_trimmed or combined_all
                agg["gpu_util_combined_avg"] = round(
                    sum(combined_avg_source) / len(combined_avg_source), 2
                )

        if families:
            kpi_status = {f: _family_kpi_status(self._samples, f) for f in families}
            agg["kpi_status"] = kpi_status
            for f in families:
                agg[f"{f.lower()}_sample_count"] = _family_sample_count(
                    self._samples, f
                )
            agg["kpi_warnings"] = ";".join(
                f"{f}:{s}" for f, s in kpi_status.items() if s != "ok"
            )

        return agg
