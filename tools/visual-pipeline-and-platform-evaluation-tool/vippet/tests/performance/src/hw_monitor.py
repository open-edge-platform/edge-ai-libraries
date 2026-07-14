"""
Hardware Metrics Monitor

Samples CPU, GPU (Xe), and NPU KPIs in a background thread during benchmark runs.

Source: VIPPET metrics-manager JSON API (CPU, GPU, NPU, memory, temperature, power).
"""

import logging
import threading
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


def _fetch_metrics_manager(url: str) -> Dict[str, float]:
    """
    Fetch latest metrics from VIPPET metrics-manager JSON API.
    Returns flat dict of metric_key -> value.
    Tagged metrics use composite keys (e.g. gpu_power__gpu_cur_power).
    Only gpu_id=0 is collected for GPU metrics with multiple IDs.
    """
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        metrics = data.get("metrics", data)
        result: Dict[str, float] = {}
        for key, entry in metrics.items():
            if isinstance(entry, dict):
                val = entry.get("fields", {}).get("value")
                if val is None:
                    continue
                name = entry.get("name", key.split("{")[0])
                tags = entry.get("tags", {})

                # For GPU metrics with multiple gpu_ids, only use gpu_id=0
                gpu_id = tags.get("gpu_id")
                if gpu_id is not None and gpu_id != "0":
                    continue

                # Create composite key for metrics needing tag disambiguation
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
    """
    Background-thread hardware sampler.

    Usage:
        monitor = HardwareMonitor("http://localhost:9090/api/v1/metrics/latest")
        monitor.start()
        ... run workload ...
        hw_stats = monitor.stop()   # returns aggregated dict
    """

    def __init__(self, metrics_url: str = "http://localhost:9090/api/v1/metrics/latest",
                 sample_interval: float = 2.0):
        self._metrics_url = metrics_url
        self._interval = sample_interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._samples: List[Dict[str, float]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._stop.clear()
        self._samples.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="hw-monitor")
        self._thread.start()
        logger.debug("HardwareMonitor started (interval=%.1fs)", self._interval)

    def stop(self) -> Dict[str, Any]:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=max(self._interval * 2, 10))
        stats = self._aggregate()
        logger.debug("HardwareMonitor stopped (%d samples)", len(self._samples))
        return stats

    # ------------------------------------------------------------------
    # Sampling
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                sample = self._collect()
                if sample:
                    self._samples.append(sample)
            except Exception as e:
                logger.debug("hw sample error: %s", e)
            self._stop.wait(self._interval)

    def _collect(self) -> Dict[str, float]:
        sample: Dict[str, float] = {}

        mm = _fetch_metrics_manager(self._metrics_url)

        # ── CPU ──
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

        # ── GPU (Xe) — per-engine utilization ──
        for engine, label in [("rcs", "gpu_render_util_pct"),
                              ("vcs", "gpu_video_util_pct"),
                              ("vecs", "gpu_enhance_util_pct"),
                              ("ccs", "gpu_compute_util_pct")]:
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

        # ── NPU ──
        for key in ("npu_utilization", "npu_frequency",
                     "npu_power", "npu_temperature", "npu_memory_mb",
                     "npu_bandwidth"):
            if key in mm:
                sample[key] = mm[key]

        return sample

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _aggregate(self) -> Dict[str, Any]:
        if not self._samples:
            return {"sample_count": 0}

        keys = set()
        for s in self._samples:
            keys.update(s.keys())

        agg: Dict[str, Any] = {"sample_count": len(self._samples)}

        for key in sorted(keys):
            values = [s[key] for s in self._samples if key in s]
            if not values:
                continue
            agg[f"{key}_avg"] = round(sum(values) / len(values), 2)
            agg[f"{key}_min"] = round(min(values), 2)
            agg[f"{key}_max"] = round(max(values), 2)

        # Convenience: combined GPU util (average of render + video engines)
        render_vals = [s.get("gpu_render_util_pct") for s in self._samples if "gpu_render_util_pct" in s]
        video_vals = [s.get("gpu_video_util_pct") for s in self._samples if "gpu_video_util_pct" in s]
        if render_vals or video_vals:
            all_vals = render_vals + video_vals
            agg["gpu_util_combined_avg"] = round(sum(all_vals) / len(all_vals), 2)

        return agg
