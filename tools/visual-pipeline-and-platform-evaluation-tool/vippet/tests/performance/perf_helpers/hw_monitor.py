# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Hardware Metrics Monitor.

Samples CPU, GPU (Xe), and NPU KPIs in a background thread during benchmark runs.
Source: VIPPET metrics-manager JSON API (CPU, GPU, NPU, memory, temperature, power).
"""

import json
import logging
import threading
from typing import Any

import requests

logger = logging.getLogger(__name__)


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
        resp = requests.get(url, timeout=5, stream=True)
        resp.raise_for_status()

        raw = ""
        for line in resp.iter_lines(decode_unicode=True):
            if isinstance(line, str) and line.startswith("data: "):
                raw = line[6:]
                break
        resp.close()

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


class HardwareMonitor:
    """Background-thread hardware sampler.

    Usage:
        monitor = HardwareMonitor("http://localhost/metrics/stream")
        monitor.start()
        ... run workload ...
        hw_stats = monitor.stop()   # returns aggregated dict
    """

    def __init__(
        self,
        metrics_url: str = "http://localhost/metrics/stream",
        sample_interval: float = 2.0,
    ):
        self._metrics_url = metrics_url
        self._interval = sample_interval
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

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=max(self._interval * 2, 10))
        stats = self._aggregate()
        logger.debug("HardwareMonitor stopped (%d samples)", len(self._samples))
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

        # GPU (Xe) — per-engine utilization
        for engine, label in [
            ("rcs", "gpu_render_util_pct"),
            ("vcs", "gpu_video_util_pct"),
            ("vecs", "gpu_enhance_util_pct"),
            ("ccs", "gpu_compute_util_pct"),
        ]:
            val = mm.get(f"gpu_engine_usage_usage__{engine}")
            if val is not None:
                sample[label] = round(val, 2)

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

    def _aggregate(self) -> dict[str, Any]:
        if not self._samples:
            return {"sample_count": 0}

        keys = set()
        for s in self._samples:
            keys.update(s.keys())

        agg: dict[str, Any] = {"sample_count": len(self._samples)}

        for key in sorted(keys):
            values = [s[key] for s in self._samples if key in s]
            if not values:
                continue
            agg[f"{key}_avg"] = round(sum(values) / len(values), 2)
            agg[f"{key}_min"] = round(min(values), 2)
            agg[f"{key}_max"] = round(max(values), 2)

        # Combined GPU utilization: max(render, video) per sample, then averaged.
        combined_per_sample = []
        for s in self._samples:
            render = s.get("gpu_render_util_pct")
            video = s.get("gpu_video_util_pct")
            vals = [v for v in (render, video) if v is not None]
            if vals:
                combined_per_sample.append(max(vals))
        if combined_per_sample:
            agg["gpu_util_combined_avg"] = round(
                sum(combined_per_sample) / len(combined_per_sample), 2
            )
            agg["gpu_util_combined_max"] = round(max(combined_per_sample), 2)

        return agg
