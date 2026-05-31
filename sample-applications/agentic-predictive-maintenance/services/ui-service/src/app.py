# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""UI service — FastAPI web application for the agentic predictive maintenance blueprint."""

import logging
import os
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

_AGENT_URL   = os.environ.get("AGENT_SERVICE_URL",   "http://apm-agent:5002")
_STORAGE_URL = os.environ.get("STORAGE_SERVICE_URL", "http://apm-storage:5001")
_USE_CASE_ID = os.environ.get("USE_CASE_ID",         "unknown")
_TIMEOUT     = 15.0

app = FastAPI(title="APM UI", docs_url=None, redoc_url=None)

_src_dir = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(_src_dir, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(_src_dir, "templates"))


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            summary_r = await client.get(f"{_STORAGE_URL}/detections/summary")
            summary = summary_r.json() if summary_r.status_code == 200 else {}
        except Exception:
            summary = {}

        try:
            runs_r = await client.get(f"{_AGENT_URL}/agents/runs")
            runs = runs_r.json() if runs_r.status_code == 200 else []
        except Exception:
            runs = []

    return templates.TemplateResponse(
        request=request, name="index.html",
        context={"use_case_id": _USE_CASE_ID, "summary": summary, "runs": runs},
    )


@app.get("/detections", response_class=HTMLResponse)
async def detections_page(
    request: Request,
    label: Optional[str] = None,
    min_confidence: Optional[float] = None,
    limit: int = 100,
):
    params: dict = {"limit": limit}
    if label:
        params["label"] = label
    if min_confidence is not None:
        params["min_confidence"] = min_confidence

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            r = await client.get(f"{_STORAGE_URL}/detections", params=params)
            detections = r.json() if r.status_code == 200 else []
        except Exception:
            detections = []

    return templates.TemplateResponse(
        request=request, name="detections.html",
        context={
            "use_case_id": _USE_CASE_ID,
            "detections": detections,
            "filter_label": label or "",
            "filter_confidence": min_confidence or "",
        },
    )


@app.get("/results/{run_id}", response_class=HTMLResponse)
async def results_page(request: Request, run_id: str):
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            r = await client.get(f"{_AGENT_URL}/agents/results/{run_id}")
            if r.status_code == 404:
                raise HTTPException(status_code=404, detail="Run not found")
            result = r.json() if r.status_code == 200 else {"status": "running"}
        except HTTPException:
            raise
        except Exception as exc:
            result = {"error": str(exc)}

    return templates.TemplateResponse(
        request=request, name="results.html",
        context={"use_case_id": _USE_CASE_ID, "run_id": run_id, "result": result},
    )


# ── Actions ───────────────────────────────────────────────────────────────────

@app.post("/run")
async def trigger_run():
    """Trigger a new agent pipeline run via the agent-service."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.post(f"{_AGENT_URL}/agents/run", json={})
        r.raise_for_status()
        data = r.json()
    return RedirectResponse(url=f"/results/{data['run_id']}", status_code=303)


@app.post("/clear-detections")
async def clear_detections():
    """Clear all detections from storage."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        await client.delete(f"{_STORAGE_URL}/detections")
    return RedirectResponse(url="/", status_code=303)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "ui-service", "use_case_id": _USE_CASE_ID}
