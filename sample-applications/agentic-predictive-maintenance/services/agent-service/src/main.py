# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""FastAPI entry point for the agent-service."""

import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel

from .meta_agent import run_pipeline
from .mqtt_subscriber import start_subscriber, set_on_detection_callback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

# In-memory run store (keyed by run_id)
_runs: dict[str, dict] = {}

_CONFIG_PATH  = os.environ.get("AGENTS_CONFIG_PATH", None)
_PROMPTS_DIR  = os.environ.get("USE_CASE_PROMPTS_DIR", None)
_AUTO_RUN     = os.environ.get("AUTO_RUN_ON_DETECTION", "false").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start MQTT subscriber (non-blocking background thread)
    if os.environ.get("MQTT_DISABLED", "false").lower() != "true":
        if _AUTO_RUN:
            set_on_detection_callback(_auto_trigger)
        start_subscriber()
    yield


app = FastAPI(
    title="APM Agent Service",
    description="Agentic Predictive Maintenance — multi-agent orchestration service",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Request / Response models ─────────────────────────────────────────────────

class RunRequest(BaseModel):
    config_path: Optional[str] = None
    prompts_dir: Optional[str] = None


class RunResponse(BaseModel):
    run_id: str
    status: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/agents/run", response_model=RunResponse, status_code=202)
async def trigger_run(req: RunRequest, background_tasks: BackgroundTasks):
    """Trigger a new agent pipeline run (async background task)."""
    run_id = str(uuid.uuid4())
    _runs[run_id] = {"status": "running", "result": None}
    background_tasks.add_task(_execute_run, run_id, req.config_path, req.prompts_dir)
    return RunResponse(run_id=run_id, status="running")


@app.get("/agents/status/{run_id}")
def get_status(run_id: str):
    """Return the status of a pipeline run."""
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run_id": run_id, "status": _runs[run_id]["status"]}


@app.get("/agents/results/{run_id}")
def get_results(run_id: str):
    """Return the results of a completed pipeline run."""
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail="Run not found")
    run = _runs[run_id]
    if run["status"] == "running":
        raise HTTPException(status_code=202, detail="Run still in progress")
    return {"run_id": run_id, **run["result"]}


@app.get("/agents/runs")
def list_runs():
    """List all runs with their status."""
    return [{"run_id": k, "status": v["status"]} for k, v in _runs.items()]


@app.get("/health")
def health():
    return {"status": "ok", "service": "agent-service", "run_count": len(_runs)}


@app.get("/metrics")
def metrics():
    total   = len(_runs)
    done    = sum(1 for r in _runs.values() if r["status"] == "completed")
    failed  = sum(1 for r in _runs.values() if r["status"] == "error")
    running = sum(1 for r in _runs.values() if r["status"] == "running")
    lines = [
        "# HELP apm_agent_runs_total Total pipeline runs",
        "# TYPE apm_agent_runs_total counter",
        f"apm_agent_runs_total {total}",
        "# HELP apm_agent_runs_completed Completed pipeline runs",
        "# TYPE apm_agent_runs_completed counter",
        f"apm_agent_runs_completed {done}",
        "# HELP apm_agent_runs_failed Failed pipeline runs",
        "# TYPE apm_agent_runs_failed counter",
        f"apm_agent_runs_failed {failed}",
        "# HELP apm_agent_runs_running Currently running pipeline runs",
        "# TYPE apm_agent_runs_running gauge",
        f"apm_agent_runs_running {running}",
    ]
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _execute_run(run_id: str, config_path: str | None, prompts_dir: str | None):
    try:
        result = run_pipeline(
            config_path=config_path or _CONFIG_PATH,
            prompts_dir=prompts_dir or _PROMPTS_DIR,
        )
        _runs[run_id] = {"status": "completed", "result": result}
        log.info("Run %s completed", run_id)
    except Exception as exc:
        log.error("Run %s failed: %s", run_id, exc)
        _runs[run_id] = {"status": "error", "result": {"error": str(exc)}}


_auto_run_count = 0
_AUTO_RUN_THRESHOLD = int(os.environ.get("AUTO_RUN_THRESHOLD", "100"))


def _auto_trigger(detection_count: int):
    """Trigger a pipeline run automatically after accumulating enough detections."""
    global _auto_run_count
    _auto_run_count += detection_count
    if _auto_run_count >= _AUTO_RUN_THRESHOLD:
        _auto_run_count = 0
        run_id = str(uuid.uuid4())
        _runs[run_id] = {"status": "running", "result": None}
        import threading
        threading.Thread(
            target=_execute_run, args=(run_id, _CONFIG_PATH, _PROMPTS_DIR), daemon=True
        ).start()
        log.info("Auto-triggered run %s after %d detections", run_id, _AUTO_RUN_THRESHOLD)
