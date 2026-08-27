# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""FastAPI entry point for event-driven agent reasoning."""

import json
import logging
import os
import queue
import threading
import time
import uuid
from copy import deepcopy
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Optional

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, StrictInt, model_validator

from .batch_event_subscriber import (
    BatchDelivery,
    BatchEvent,
    set_on_batch_callback,
    start_subscriber,
)
from .meta_agent import run_pipeline
from .utility.output_store import AgentOutputStore, OutputStoreError
from .utility.runtime_config import load_runtime_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

_runs: dict[str, dict] = {}
_runs_lock = threading.RLock()
_pending_deliveries: dict[str, list[BatchDelivery]] = {}
_RUN_RETENTION_SECONDS = int(os.environ.get("RUN_RETENTION_SECONDS", "86400"))
_MAX_RETAINED_RUNS = int(os.environ.get("MAX_RETAINED_RUNS", "1000"))
_output_store = AgentOutputStore(
    os.environ.get("OUTPUT_DIR", "/tmp/agent-quality-handler-output")
)

_CONFIG_PATH = os.environ.get("AGENTS_CONFIG_PATH")
_PROMPTS_DIR = os.environ.get("USE_CASE_PROMPTS_DIR")


@dataclass(frozen=True)
class ReasoningWork:
    run_id: str
    config_path: str | None
    prompts_dir: str | None
    min_id: int | None
    max_id: int | None


_reasoning_queue: queue.Queue[ReasoningWork | None] = queue.Queue()
_reasoning_lock = threading.Lock()
_worker_lifecycle_lock = threading.Lock()
_worker_thread: threading.Thread | None = None


def _worker_loop() -> None:
    while True:
        work = _reasoning_queue.get()
        try:
            if work is None:
                return
            _execute_reasoning_run(work)
        finally:
            _reasoning_queue.task_done()


def _start_reasoning_worker() -> threading.Thread:
    global _worker_thread
    with _worker_lifecycle_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return _worker_thread
        _worker_thread = threading.Thread(
            target=_worker_loop,
            daemon=True,
            name="reasoning-worker",
        )
        _worker_thread.start()
        return _worker_thread


def _stop_reasoning_worker() -> None:
    global _worker_thread
    with _worker_lifecycle_lock:
        worker = _worker_thread
        if worker is None:
            return
        _reasoning_queue.put(None)
    worker.join()
    with _worker_lifecycle_lock:
        if _worker_thread is worker:
            _worker_thread = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_runtime_settings()
    app.state.runtime_settings = settings
    _output_store.ensure_files()
    _output_store.prune(_RUN_RETENTION_SECONDS, _MAX_RETAINED_RUNS)
    _start_reasoning_worker()
    mqtt_client = None

    try:
        if settings.mqtt_enabled:
            set_on_batch_callback(_handle_batch_event)
            mqtt_client = start_subscriber(settings)
        yield
    finally:
        if mqtt_client is not None:
            try:
                mqtt_client.disconnect()
            except Exception:
                log.exception("Failed to stop MQTT subscriber cleanly")
        set_on_batch_callback(None)
        _stop_reasoning_worker()


app = FastAPI(
    title="aqh Agent Service",
    description="Event-driven Agentic Predictive Maintenance reasoning service",
    version="1.0.0",
    lifespan=lifespan,
)


class RunRequest(BaseModel):
    config_path: Optional[str] = None
    prompts_dir: Optional[str] = None
    min_id: Optional[Annotated[StrictInt, Field(ge=0)]] = None
    max_id: Optional[Annotated[StrictInt, Field(ge=0)]] = None

    @model_validator(mode="after")
    def validate_bounds(self) -> "RunRequest":
        if (
            self.min_id is not None
            and self.max_id is not None
            and self.min_id >= self.max_id
        ):
            raise ValueError("min_id must be less than max_id")
        return self


class RunResponse(BaseModel):
    run_id: str
    status: str
    source: str
    min_id: int | None = None
    max_id: int | None = None


def _cleanup_runs(now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    persisted_removals = _output_store.prune(
        _RUN_RETENTION_SECONDS, _MAX_RETAINED_RUNS
    )
    with _runs_lock:
        for run_id in persisted_removals:
            _runs.pop(run_id, None)
        terminal = [
            (run_id, run)
            for run_id, run in _runs.items()
            if run.get("status") in {"completed", "error"}
            and run_id not in _pending_deliveries
        ]
        if _RUN_RETENTION_SECONDS >= 0:
            for run_id, run in terminal:
                completed_at = run.get("completed_at")
                if (
                    completed_at is not None
                    and now - completed_at >= _RUN_RETENTION_SECONDS
                ):
                    _runs.pop(run_id, None)

        excess = len(_runs) - _MAX_RETAINED_RUNS
        if excess > 0:
            terminal = sorted(
                (
                    (run.get("completed_at", float("inf")), run_id)
                    for run_id, run in _runs.items()
                    if run.get("status") in {"completed", "error"}
                    and run_id not in _pending_deliveries
                )
            )
            for _, run_id in terminal[:excess]:
                _runs.pop(run_id, None)


def _create_run(
    run_id: str,
    *,
    status: str = "queued",
    source: str,
    min_id: int | None = None,
    max_id: int | None = None,
    metadata: dict | None = None,
) -> None:
    _cleanup_runs()
    with _runs_lock:
        if run_id in _runs:
            raise ValueError(f"Run already exists: {run_id}")
        _runs[run_id] = {
            "status": status,
            "result": None,
            "created_at": time.monotonic(),
            "source": source,
            "min_id": min_id,
            "max_id": max_id,
            "metadata": deepcopy(metadata or {}),
        }


def _store_result(run_id: str, status: str, result: dict) -> None:
    if not isinstance(result, dict):
        raise TypeError("Pipeline result must be a JSON object")
    encoded = jsonable_encoder(result)
    serialized = json.loads(json.dumps(encoded, allow_nan=False))
    with _runs_lock:
        existing = deepcopy(_runs.get(run_id, {}))
    completed_at = time.time()
    _output_store.record_run(
        run_id,
        status=status,
        result=serialized,
        source=existing.get("source", "unknown"),
        min_id=existing.get("min_id"),
        max_id=existing.get("max_id"),
        metadata=existing.get("metadata", {}),
        completed_at=completed_at,
    )
    _output_store.prune(_RUN_RETENTION_SECONDS, _MAX_RETAINED_RUNS)
    with _runs_lock:
        _runs[run_id] = {
            "status": status,
            "result": serialized,
            "created_at": existing.get("created_at", time.monotonic()),
            "completed_at": time.monotonic(),
            "source": existing.get("source", "unknown"),
            "min_id": existing.get("min_id"),
            "max_id": existing.get("max_id"),
            "metadata": deepcopy(existing.get("metadata", {})),
        }
    _cleanup_runs()


def _store_unpersisted_error(run_id: str, exc: OutputStoreError) -> None:
    """Keep output-volume failures visible without terminating the worker."""
    result = _pipeline_error(exc)
    with _runs_lock:
        existing = _runs.get(run_id, {})
        _runs[run_id] = {
            "status": "error",
            "result": result,
            "created_at": existing.get("created_at", time.monotonic()),
            "completed_at": time.monotonic(),
            "source": existing.get("source", "unknown"),
            "min_id": existing.get("min_id"),
            "max_id": existing.get("max_id"),
            "metadata": deepcopy(existing.get("metadata", {})),
        }


def _finalize_run(run_id: str, status: str, result: dict) -> None:
    try:
        _store_result(run_id, status, result)
    except OutputStoreError as exc:
        log.error("Run %s output persistence failed: %s", run_id, exc)
        _store_unpersisted_error(run_id, exc)


def _run_payload(run_id: str, run: dict) -> dict:
    payload = {
        "run_id": run_id,
        "status": run["status"],
        "source": run.get("source", "unknown"),
    }
    if run.get("min_id") is not None:
        payload["min_id"] = run["min_id"]
    if run.get("max_id") is not None:
        payload["max_id"] = run["max_id"]
    return payload


@app.post(
    "/agents/run",
    response_model=RunResponse,
    response_model_exclude_none=True,
    status_code=202,
)
async def trigger_run(req: RunRequest):
    """Queue a bounded manual reasoning run."""
    run_id = str(uuid.uuid4())
    _create_run(
        run_id,
        source="http",
        min_id=req.min_id,
        max_id=req.max_id,
    )
    _reasoning_queue.put(
        ReasoningWork(
            run_id,
            req.config_path,
            req.prompts_dir,
            req.min_id,
            req.max_id,
        )
    )
    return RunResponse(
        run_id=run_id,
        status="queued",
        source="http",
        min_id=req.min_id,
        max_id=req.max_id,
    )


@app.get("/agents/status/{run_id}")
def get_status(run_id: str):
    _cleanup_runs()
    with _runs_lock:
        run = deepcopy(_runs.get(run_id))
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_payload(run_id, run)


@app.get("/agents/results/{run_id}")
def get_results(run_id: str):
    _cleanup_runs()
    with _runs_lock:
        run = deepcopy(_runs.get(run_id))
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run["status"] in {"queued", "running"}:
        raise HTTPException(
            status_code=202, detail=f"Run is {run['status']}"
        )
    response = {**run["result"], **_run_payload(run_id, run)}
    if run.get("metadata"):
        response["batch_metadata"] = run["metadata"]
    return response


@app.get("/agents/runs")
def list_runs(id: Optional[str] = None):
    _cleanup_runs()
    with _runs_lock:
        if id is not None:
            run = deepcopy(_runs.get(id))
            if run is None:
                raise HTTPException(status_code=404, detail="Run not found")
            return [_run_payload(id, run)]
        return [_run_payload(key, value) for key, value in _runs.items()]


@app.get("/agents/outputs/{agent}")
def list_agent_outputs(agent: str):
    """Return retained output records for one agent."""
    try:
        _cleanup_runs()
        return _output_store.get_agent(agent)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OutputStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/agents/outputs/{agent}/{run_id}")
def get_agent_output(agent: str, run_id: str):
    """Return one retained agent output by run ID."""
    try:
        _cleanup_runs()
        record = _output_store.get_run(agent, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OutputStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Agent output not found")
    return record


@app.get("/health")
def health():
    _cleanup_runs()
    with _runs_lock:
        run_count = len(_runs)
    return {"status": "ok", "service": "agent-service", "run_count": run_count}


@app.get("/metrics")
def metrics():
    _cleanup_runs()
    with _runs_lock:
        runs = list(_runs.values())
    total = len(runs)
    queued = sum(1 for run in runs if run["status"] == "queued")
    running = sum(1 for run in runs if run["status"] == "running")
    completed = sum(1 for run in runs if run["status"] == "completed")
    failed = sum(1 for run in runs if run["status"] == "error")
    lines = [
        "# HELP aqh_agent_runs_total Retained reasoning runs",
        "# TYPE aqh_agent_runs_total gauge",
        f"aqh_agent_runs_total {total}",
        "# HELP aqh_agent_runs_queued Queued reasoning runs",
        "# TYPE aqh_agent_runs_queued gauge",
        f"aqh_agent_runs_queued {queued}",
        "# HELP aqh_agent_runs_running Active reasoning runs",
        "# TYPE aqh_agent_runs_running gauge",
        f"aqh_agent_runs_running {running}",
        "# HELP aqh_agent_runs_completed Completed reasoning runs",
        "# TYPE aqh_agent_runs_completed gauge",
        f"aqh_agent_runs_completed {completed}",
        "# HELP aqh_agent_runs_failed Failed reasoning runs",
        "# TYPE aqh_agent_runs_failed gauge",
        f"aqh_agent_runs_failed {failed}",
    ]
    return PlainTextResponse(
        "\n".join(lines) + "\n", media_type="text/plain; version=0.0.4"
    )


def _pipeline_error(exc: Exception) -> dict:
    return {
        "use_case_id": None,
        "policy": {},
        "analysis": {},
        "evidence": {},
        "ticket": {},
        "errors": [
            {
                "agent": "pipeline",
                "status": "failed",
                "type": type(exc).__name__,
                "message": str(exc),
            }
        ],
        "error": str(exc),
    }


def _execute_reasoning_run(work: ReasoningWork) -> None:
    terminal = False
    try:
        with _reasoning_lock:
            with _runs_lock:
                run = _runs.get(work.run_id)
                if run is None or run["status"] != "queued":
                    terminal = bool(
                        run and run["status"] in {"completed", "error"}
                    )
                    return
                run["status"] = "running"

            try:
                result = run_pipeline(
                    config_path=work.config_path or _CONFIG_PATH,
                    prompts_dir=work.prompts_dir or _PROMPTS_DIR,
                    min_id=work.min_id,
                    max_id=work.max_id,
                )
                status = "error" if result.get("errors") else "completed"
                _finalize_run(work.run_id, status, result)
            except Exception as exc:
                log.error("Run %s failed: %s", work.run_id, exc)
                _finalize_run(work.run_id, "error", _pipeline_error(exc))
            terminal = True
    finally:
        if terminal:
            _acknowledge_pending(work.run_id)


def _upstream_error_result(event: BatchEvent) -> dict:
    message = event.error or f"Detection batch ended with {event.status}"
    return {
        "use_case_id": None,
        "policy": {},
        "analysis": {},
        "evidence": {},
        "ticket": {},
        "errors": [
            {
                "agent": "detection",
                "status": "failed",
                "type": "upstream_batch_error",
                "message": message,
                "pipeline_status": event.pipeline_status,
            }
        ],
        "error": message,
    }


def _acknowledge_pending(run_id: str) -> None:
    with _runs_lock:
        deliveries = _pending_deliveries.pop(run_id, [])
    failed = []
    for delivery in deliveries:
        try:
            if not delivery.acknowledge():
                failed.append(delivery)
        except Exception:
            log.exception("Failed to acknowledge MQTT delivery for run %s", run_id)
            failed.append(delivery)
    if failed:
        with _runs_lock:
            _pending_deliveries.setdefault(run_id, []).extend(failed)


def _handle_batch_event(event: BatchEvent, delivery: BatchDelivery) -> None:
    enqueue = False
    terminal = False
    with _runs_lock:
        existing = _runs.get(event.run_id)
        _pending_deliveries.setdefault(event.run_id, []).append(delivery)
        if existing is not None:
            terminal = existing["status"] in {"completed", "error"}
        elif event.status == "error":
            _create_run(
                event.run_id,
                source="mqtt",
                min_id=event.start_id,
                max_id=event.end_id,
                metadata=event.metadata(),
            )
            _finalize_run(
                event.run_id,
                "error",
                _upstream_error_result(event),
            )
            terminal = True
        else:
            _create_run(
                event.run_id,
                source="mqtt",
                min_id=event.start_id,
                max_id=event.end_id,
                metadata=event.metadata(),
            )
            enqueue = True

    if enqueue:
        _reasoning_queue.put(
            ReasoningWork(
                event.run_id,
                _CONFIG_PATH,
                _PROMPTS_DIR,
                event.start_id,
                event.end_id,
            )
        )
    elif terminal:
        _acknowledge_pending(event.run_id)
