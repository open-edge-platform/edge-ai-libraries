# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Performance monitoring tool management utilities.

This module manages the Metrics Manager microservice as the resource-metrics
collector for profiling runs. It starts the service as a Docker container,
polls its Prometheus metrics endpoint into a log file using a background
thread, and generates utilization graphs (CPU, memory, temperature, GPU and NPU)
from the collected metrics.

The public functions (`start_perf_tool`, `stop_perf_tool`, `plot_graphs`,
`copy_perf_tools_logs`) keep the same signatures used by the profiling flow in
`src/base.py`, so the overall execution flow is unchanged.
"""

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import requests

# Files produced inside the perf_tool_logs directory.
_STREAM_LOG_NAME = "metrics_stream.log"
_PLOT_NAME = "resource_utilization.png"
_SUMMARY_CSV = "metrics_summary.csv"

# Metrics Manager container settings.
_CONTAINER_NAME = "metrics-manager-sizing"
_DEFAULT_IMAGE = "intel/metrics-manager:2026.1.0"
_HEALTH_URL = "http://localhost:9091/health"

# Prometheus endpoint exposed by the Metrics Manager container (host side).
# This is the same data the SSE stream relays; we poll it directly.
_PROMETHEUS_URL = os.environ.get(
    "METRICS_MANAGER_PROMETHEUS_URL", "http://localhost:9274/metrics"
)

# How often (in seconds) to poll the Prometheus endpoint.
_POLL_INTERVAL = 1.0

# Background metrics collector thread and its stop signal (managed by
# start_perf_tool / stop_perf_tool).
_collector_thread = None
_collector_stop = None


def _wait_for_health(url=_HEALTH_URL, timeout=120, interval=3):
    """Poll the Metrics Manager health endpoint until it is ready or times out."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(url, timeout=5).status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(interval)
    return False


# Prometheus exposition parsing: one label pair key="value" (escapes allowed).
_LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:\\.|[^"\\])*)"')
# A metric sample line: name{labels} value [timestamp]
_SAMPLE_RE = re.compile(
    r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{.*\})?\s+(\S+)(?:\s+(-?\d+(?:\.\d+)?))?\s*$'
)


def _parse_prometheus_text(text, keep=None):
    """Parse Prometheus exposition text into a list of metric records.

    Returns a list of ``{"name", "labels", "value", "timestamp"}`` dicts, where
    ``timestamp`` is in milliseconds (from the exposition line) or ``None``.
    Non-finite values (NaN / +Inf / -Inf) are skipped.

    If ``keep`` is provided, it is a callable ``keep(name) -> bool`` used to
    discard unwanted metric names *before* the costly label parsing, so only
    the metrics that are actually plotted are parsed and retained. This keeps
    the collector lightweight (minimal CPU) since Telegraf's Prometheus
    endpoint exposes many more series than the graphs consume.
    """
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _SAMPLE_RE.match(line)
        if not match:
            continue
        name, label_block, raw_value, raw_ts = match.groups()
        if keep is not None and not keep(name):
            continue
        try:
            value = float(raw_value)
        except ValueError:
            continue
        if value != value or value in (float("inf"), float("-inf")):
            continue

        labels = {}
        if label_block:
            for key, val in _LABEL_RE.findall(label_block):
                labels[key] = (
                    val.replace('\\"', '"').replace("\\\\", "\\").replace("\\n", "\n")
                )

        timestamp = int(raw_ts) if raw_ts else None
        records.append(
            {"name": name, "labels": labels, "value": value, "timestamp": timestamp}
        )
    return records


def _poll_worker(url, output, stop_event, interval=_POLL_INTERVAL):
    """Poll the Prometheus endpoint and append a metrics event per poll.

    Each line written to ``output`` is a JSON object matching the previous SSE
    format::

        {"timestamp": <ms>, "metrics": [{"name", "labels", "value", "timestamp"}, ...]}
    """
    with open(output, "a", encoding="utf-8") as sink:
        while not stop_event.is_set():
            start = time.time()
            try:
                resp = requests.get(url, timeout=5)
                resp.raise_for_status()
                metrics = _parse_prometheus_text(resp.text, keep=_wanted_metric)
                if metrics:
                    poll_ms = int(time.time() * 1000)
                    sink.write(
                        json.dumps({"timestamp": poll_ms, "metrics": metrics}) + "\n"
                    )
                    sink.flush()
            except requests.RequestException:
                # Service may still be starting or briefly unavailable; retry.
                pass
            except Exception:
                pass
            # Sleep the remainder of the interval, waking promptly on stop.
            elapsed = time.time() - start
            stop_event.wait(max(0.0, interval - elapsed))


def start_perf_tool(repo_url, report_dir):
    """
    Start the Metrics Manager microservice and begin streaming its metrics.

    This function starts the Metrics Manager container with ``docker run``
    (pulling the published image automatically) and launches a background thread
    that polls the service's Prometheus endpoint and appends every metrics sample
    to ``metrics_stream.log`` inside the log directory.

    Args:
        repo_url: Metrics Manager image reference (e.g.
            ``intel/metrics-manager:2026.1.0``). Ignored if it points at a git
            repository; the default published image is used instead.
        report_dir: Path to the report directory where performance logs
            will be stored.

    Returns:
        tuple: (absolute log directory path, container name).
    """
    global _collector_thread, _collector_stop

    # Create log directory
    abs_log_dir = (Path(report_dir) / "perf_tool_logs").resolve()
    abs_log_dir.mkdir(parents=True, exist_ok=True)

    # Use the configured value as the image reference unless it is a git URL.
    image = repo_url if (repo_url and not repo_url.endswith('.git')) else _DEFAULT_IMAGE

    try:
        # Remove any stale container from a previous run.
        subprocess.run(
            ['docker', 'rm', '-f', _CONTAINER_NAME],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # Start the Metrics Manager container.
        print("Starting Metrics Manager container, it takes some time to initialize...")
        subprocess.run(
            [
                'docker', 'run', '-d', '--name', _CONTAINER_NAME,
                '--privileged',
                '--device', '/dev/dri:/dev/dri',
                '-v', '/sys:/sys:ro',
                '-v', '/run:/run:ro',
                '--pid', 'host',
                '-p', '9091:9090',
                '-p', '9274:9273',
                '-e', 'METRICS_PORT=9090',
                '-e', 'TELEGRAF_PORT=9273',
                image,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Wait until the service reports healthy before streaming.
        if not _wait_for_health():
            print("Warning: Metrics Manager did not report healthy in time; "
                  "metrics collection may be incomplete.")

        # Start polling the Prometheus endpoint into the log directory (in-process thread).
        stream_log = abs_log_dir / _STREAM_LOG_NAME
        prometheus_url = os.environ.get('METRICS_MANAGER_PROMETHEUS_URL', _PROMETHEUS_URL)
        _collector_stop = threading.Event()
        _collector_thread = threading.Thread(
            target=_poll_worker,
            args=(prometheus_url, str(stream_log), _collector_stop),
            daemon=True,
        )
        _collector_thread.start()
        print(f"Metrics Manager started. Polling metrics to: {stream_log}")

    except subprocess.CalledProcessError as e:
        print(f"Error during Metrics Manager setup: {e}")
        if e.stderr:
            print(f"Error details: {e.stderr.decode('utf-8', errors='ignore')}")
    except OSError as e:
        print(f"File system error during Metrics Manager setup: {e}")
    except Exception as e:
        print(f"Unexpected error during Metrics Manager setup: {e}")

    return str(abs_log_dir), _CONTAINER_NAME


def stop_perf_tool(container_name, log_dir):
    """
    Stop the metrics collector thread and remove the Metrics Manager container.

    This function signals the background polling thread to stop, waits briefly for
    any buffered metrics to flush, then removes the Metrics Manager container.

    Args:
        container_name: Name of the Metrics Manager container to remove.
        log_dir: Path to the log directory (kept for signature compatibility).
    """
    global _collector_thread, _collector_stop

    try:
        # Signal the metrics collector thread to stop and wait for it to finish.
        if _collector_stop is not None:
            _collector_stop.set()
        if _collector_thread is not None:
            _collector_thread.join(timeout=20)
        _collector_thread = None
        _collector_stop = None

        # Brief delay to ensure metrics are flushed
        time.sleep(2)

        # Stop and remove the Metrics Manager container.
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30
        )

        print("Metrics Manager stopped.")

    except subprocess.TimeoutExpired:
        print("Warning: Docker container removal timed out.")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        print(f"Error stopping Metrics Manager: {error_msg}")
    except FileNotFoundError:
        print("Error: Docker command not found. Ensure Docker is installed and in PATH.")
    except Exception as e:
        print(f"Unexpected error stopping Metrics Manager: {e}")


# ==============================================================================
# Metrics Manager metric categorisation and graphing
# ==============================================================================

# Ordered list of graph panels rendered when data is available.
_CATEGORY_ORDER = [
    "CPU (%)",
    "GPU (%)",
    "NPU (%)",
    "Memory (%)",
    "Temperature (\u00b0C)",
]


def _categorize(name):
    """Map a Prometheus/SSE metric name to one of the five graph panels.

    Only the single "actual usage" metric per resource is kept, so each panel
    renders exactly one line: CPU user utilization, GPU utilization, NPU
    utilization, memory usage and temperature.
    """
    if name == "cpu_usage_user":
        return "CPU (%)"
    if name == "mem_used_percent":
        return "Memory (%)"
    if name == "temp_temp":
        return "Temperature (\u00b0C)"
    if name.startswith("gpu_engine_usage"):
        return "GPU (%)"
    if name == "npu_utilization":
        return "NPU (%)"
    return None


def _wanted_metric(name):
    """Return True only for metric names that end up on a graph panel.

    Used to filter the Prometheus scrape down to the handful of plotted series
    (see ``_categorize``), keeping collection lightweight and the log small.
    """
    return _categorize(name) is not None


def _series_label(name, labels):
    """Build a human-readable legend label for the single series per panel."""
    if name == "cpu_usage_user":
        return "CPU user utilization"
    if name == "mem_used_percent":
        return "Memory usage"
    if name == "temp_temp":
        return "Temperature"
    if name.startswith("gpu_engine_usage"):
        return "GPU utilization"
    if name == "npu_utilization":
        return "NPU utilization"
    return name


def _load_stream(stream_log):
    """Parse the SSE log into a nested structure of time series.

    Returns:
        tuple: (series, t0) where ``series`` maps category -> label ->
        list[(timestamp_ms, value)] and ``t0`` is the earliest timestamp seen.
    """
    series = {}
    t0 = None

    with open(stream_log, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            metrics = event.get("metrics")
            if not isinstance(metrics, list):
                continue
            event_ts = event.get("timestamp")

            for metric in metrics:
                name = metric.get("name")
                category = _categorize(name) if name else None
                if category is None:
                    continue
                try:
                    value = float(metric.get("value"))
                except (TypeError, ValueError):
                    continue

                ts = metric.get("timestamp") or event_ts
                if ts is None:
                    continue

                if t0 is None or ts < t0:
                    t0 = ts

                label = _series_label(name, metric.get("labels", {}) or {})
                series.setdefault(category, {}).setdefault(label, []).append((ts, value))

    return series, t0


def _write_summary(series, summary_path):
    """Write per-series avg/min/max statistics to a CSV file."""
    import csv

    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Category", "Series", "Avg", "Min", "Max", "Samples"])
        for category in _CATEGORY_ORDER:
            if category not in series:
                continue
            for label, points in sorted(series[category].items()):
                values = [v for _, v in points]
                if not values:
                    continue
                writer.writerow([
                    category,
                    label,
                    round(sum(values) / len(values), 2),
                    round(min(values), 2),
                    round(max(values), 2),
                    len(values),
                ])


def plot_graphs(log_dir):
    """
    Generate resource-utilization graphs from the Metrics Manager SSE log.

    Parses ``metrics_stream.log`` in the log directory and renders one panel per
    available metric category (CPU, memory, temperature, GPU and NPU) into
    ``resource_utilization.png``. A ``metrics_summary.csv`` with per-series statistics is
    also written.

    Args:
        log_dir: Path to the directory containing the streamed metrics log.
    """
    stream_log = Path(log_dir) / _STREAM_LOG_NAME
    plot_path = Path(log_dir) / _PLOT_NAME
    summary_path = Path(log_dir) / _SUMMARY_CSV

    if not stream_log.exists():
        print(f"No metrics stream log found at {stream_log}; skipping graphs.")
        return

    try:
        series, t0 = _load_stream(stream_log)

        categories = [c for c in _CATEGORY_ORDER if c in series and series[c]]
        if not categories or t0 is None:
            print(f"No plottable metrics found in {stream_log}.")
            return   

        print(f"Generating usage graphs from {stream_log}...")

        cols = 2 if len(categories) > 1 else 1
        rows = math.ceil(len(categories) / cols)
        fig, axes = plt.subplots(
            rows, cols, figsize=(7 * cols, 3.2 * rows), squeeze=False
        )

        for idx, category in enumerate(categories):
            ax = axes[idx // cols][idx % cols]
            for label, points in sorted(series[category].items()):
                points.sort()
                xs = [(ts - t0) / 1000.0 for ts, _ in points]
                ys = [v for _, v in points]
                ax.plot(xs, ys, label=label, linewidth=1.2)
            ax.set_title(category, fontsize=10)
            ax.set_xlabel("Elapsed time (s)")
            ax.grid(True, alpha=0.3)
            ax.legend(fontsize=7, loc="upper right")

        # Hide any unused axes in the grid.
        for j in range(len(categories), rows * cols):
            axes[j // cols][j % cols].axis("off")

        fig.suptitle("Metrics Manager - Resource Utilization", fontsize=14)
        fig.tight_layout(rect=(0, 0, 1, 0.98))
        fig.savefig(plot_path, dpi=120)
        plt.close(fig)

        _write_summary(series, summary_path)

        print(f"Performance graphs successfully generated in: {log_dir}")

    except FileNotFoundError as e:
        print(f"Error: metrics stream log not found: {e}")
    except Exception as e:
        print(f"Unexpected error during graph generation: {e}")


def copy_perf_tools_logs(logs_dir, report_dir):
    """
    Copy performance tools logs to the report directory.
    
    Args:
        logs_dir: Source directory containing performance logs.
        report_dir: Destination report directory.
        
    Returns:
        str: Path to the copied logs directory, or None on error.
    """
    if not Path(logs_dir).exists():
        print(f"Logs directory {logs_dir} does not exist.")
        return None
    
    try:
        report_logs_dir = Path(report_dir) / "perf_tools_logs"
        report_logs_dir.mkdir(parents=True, exist_ok=True)
        
        for src_file in Path(logs_dir).iterdir():
            dest_file = report_logs_dir / src_file.name
            if src_file.is_file():
                with src_file.open('rb') as fsrc, dest_file.open('wb') as fdest:
                    fdest.write(fsrc.read())
        return str(report_logs_dir)
    except Exception as e:
        print(f"Failed to copy logs: {e}")
        return None
