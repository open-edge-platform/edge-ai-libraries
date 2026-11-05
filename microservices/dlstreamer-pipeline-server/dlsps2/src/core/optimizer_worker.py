#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Pipeline optimizer worker for DLSPS 2.0.

One process per optimizer job, so candidate pipelines run outside the API
process and a crashing candidate only ends its own job. Hosts
``DLSOptimizer`` from the DL Streamer optimizer scripts, located via
``DLSPS_OPTIMIZER_DIR`` (default ``/opt/intel/dlstreamer/scripts/optimizer``).

Protocol
--------
Commands are read from stdin, one JSON object per line. The first line must be ``start``::

    {"cmd": "start", "job_id": "<id>", "pipeline": "<gst-launch string>", "search_duration": 300, "sample_duration": 10, "allowed_devices": ["CPU"]}
    {"cmd": "cancel", "job_id": "<id>"}

Events are written to stdout, one JSON object per line::

    {"job_id": "<id>", "event": "baseline", "pipeline": "...", "metrics": {...}}
    {"job_id": "<id>", "event": "candidate", "pipeline": "...", "metrics": {...} | null, "candidates_evaluated": 3, "best": {"pipeline": "...", "metrics": {...}}}
    {"job_id": "<id>", "event": "finished", "cancelled": false, "candidates_evaluated": 3, "baseline": {...}, "best": {...}}
    {"job_id": "<id>", "event": "error", "reason": "..."}

``candidate`` events carry the best result found so far, so partial results are
available while the search runs.
"""

import json
import logging
import os
import sys
import threading
import time

_OPTIMIZER_DIR = os.environ.get("DLSPS_OPTIMIZER_DIR", "/opt/intel/dlstreamer/scripts/optimizer")
if _OPTIMIZER_DIR not in sys.path:
    # The optimizer modules import each other by bare module name.
    sys.path.insert(0, _OPTIMIZER_DIR)

logger = logging.getLogger("optimizer_worker")

_write_lock = threading.Lock()


def _emit(payload: dict) -> None:
    """Write one JSON event line to stdout and flush immediately."""
    with _write_lock:
        sys.stdout.write(json.dumps(payload, default=str) + "\n")
        sys.stdout.flush()


def _result(pipeline: str, metrics) -> dict:
    return {"pipeline": pipeline, "metrics": metrics}


class OptimizerWorker:
    """Runs one optimization job and reports progress, partial results and the final result."""

    def __init__(self, job_id: str) -> None:
        self._job_id = job_id
        self._cancel = threading.Event()

    def run(self, start: dict) -> int:
        threading.Thread(target=self._read_commands, name="optimizer-stdin", daemon=True).start()
        try:
            self._optimize(start)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Optimization failed")
            _emit({"job_id": self._job_id, "event": "error", "reason": str(exc)})
            return 1
        return 0

    def _read_commands(self) -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                command = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.error("Invalid control command (not JSON): %s (%r)", line, exc)
                continue

            if command.get("cmd") == "cancel" and command.get("job_id") == self._job_id:
                self._cancel.set()
            else:
                logger.error("Unexpected command: %s", command)

    def _optimize(self, start: dict) -> None:
        from optimizer import DLSOptimizer  # pylint: disable=import-outside-toplevel,no-name-in-module

        optimizer = DLSOptimizer()
        optimizer.set_sample_duration(float(start["sample_duration"]))
        if start.get("allowed_devices"):
            optimizer.set_allowed_devices(start["allowed_devices"])

        search_duration = float(start["search_duration"])
        started = time.monotonic()
        evaluated = 0
        baseline_sent = False
        cancelled = False

        search = optimizer.iter_optimize_for_fps(start["pipeline"])
        try:
            for pipeline, metrics in search:
                if not baseline_sent:
                    _emit({"job_id": self._job_id, "event": "baseline",
                           **_result(*optimizer.get_baseline_pipeline())})
                    baseline_sent = True

                evaluated += 1
                best_pipeline, best_metrics = optimizer.get_optimal_pipeline()
                _emit({
                    "job_id": self._job_id,
                    "event": "candidate",
                    "pipeline": pipeline,
                    "metrics": metrics,
                    "candidates_evaluated": evaluated,
                    "best": _result(best_pipeline, best_metrics),
                })

                if self._cancel.is_set():
                    cancelled = True
                    break
                if time.monotonic() - started > search_duration:
                    break
        finally:
            search.close()

        if not baseline_sent:
            _emit({"job_id": self._job_id, "event": "baseline",
                   **_result(*optimizer.get_baseline_pipeline())})

        best_pipeline, best_metrics = optimizer.get_optimal_pipeline()
        _emit({
            "job_id": self._job_id,
            "event": "finished",
            "cancelled": cancelled,
            "candidates_evaluated": evaluated,
            "baseline": _result(*optimizer.get_baseline_pipeline()),
            "best": _result(best_pipeline, best_metrics),
        })


def main() -> int:
    logging.basicConfig(
        level=getattr(logging, os.environ.get("APP_LOG_LEVEL", "INFO").upper(), logging.INFO),
        stream=sys.stderr,
        format="[%(name)s] [%(levelname)s] %(message)s",
    )

    first = sys.stdin.readline()
    try:
        start = json.loads(first)
    except json.JSONDecodeError:
        _emit({"job_id": None, "event": "error", "reason": "first command must be a JSON start command"})
        return 1

    job_id = start.get("job_id")
    if start.get("cmd") != "start" or not job_id:
        _emit({"job_id": job_id, "event": "error", "reason": "first command must be start with a job_id"})
        return 1

    return OptimizerWorker(job_id).run(start)


if __name__ == "__main__":
    sys.exit(main())
