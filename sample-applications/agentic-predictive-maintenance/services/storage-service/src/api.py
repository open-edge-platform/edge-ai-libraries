# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Storage Service — FastAPI REST wrapper over SQLite for detection persistence.

Endpoints:
  POST   /detections          Insert one detection
  POST   /detections/batch    Bulk insert detections
  GET    /detections          Query detections (filter by label, confidence)
  GET    /detections/summary  Per-class statistics
  DELETE /detections          Clear all detections
  GET    /health              Health check
  GET    /metrics             Prometheus-style metrics
"""

import os
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from src.sqlite_client import SQLiteClient

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("storage-service")

# ── Config ───────────────────────────────────────────────────────────────────
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "/data/detections.db")

# ── Startup ───────────────────────────────────────────────────────────────────
db: SQLiteClient | None = None
_start_time = time.time()
_request_count = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db
    db = SQLiteClient(SQLITE_DB_PATH)
    logger.info("Storage service started. DB: %s", SQLITE_DB_PATH)
    yield
    logger.info("Storage service shutting down.")


app = FastAPI(
    title="APM Storage Service",
    description="SQLite REST API for agentic predictive maintenance detections",
    version="1.0.0",
    lifespan=lifespan,
)

# ── Pydantic Models ───────────────────────────────────────────────────────────


class Detection(BaseModel):
    frame_id: int = Field(..., description="Source frame identifier")
    label: str = Field(..., description="Defect class name")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence score")
    x: float = Field(..., description="Bounding box center X")
    y: float = Field(..., description="Bounding box center Y")
    width: float = Field(..., description="Bounding box width")
    height: float = Field(..., description="Bounding box height")


class DetectionBatch(BaseModel):
    detections: list[Detection]


class InsertResponse(BaseModel):
    inserted: int


# ── Routes ────────────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    global db
    try:
        count = db.count()
        return {"status": "ok", "detections_count": count}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/detections", response_model=InsertResponse, status_code=201)
def insert_detection(detection: Detection):
    global db, _request_count
    _request_count += 1
    row_id = db.insert_detection(
        detection.frame_id, detection.label, detection.confidence,
        detection.x, detection.y, detection.width, detection.height,
    )
    return {"inserted": 1}


@app.post("/detections/batch", response_model=InsertResponse, status_code=201)
def insert_batch(batch: DetectionBatch):
    global db, _request_count
    _request_count += 1
    records = [d.model_dump() for d in batch.detections]
    count = db.insert_many(records)
    return {"inserted": count}


@app.get("/detections")
def get_detections(
    label: str | None = Query(None, description="Filter by defect class"),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0),
    limit: int | None = Query(None, ge=1),
):
    global db, _request_count
    _request_count += 1
    return db.get_detections(label=label, min_confidence=min_confidence, limit=limit)


@app.get("/detections/summary")
def get_summary():
    global db
    return db.get_summary()


@app.delete("/detections", status_code=204)
def clear_detections():
    global db
    db.clear()


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    global db, _start_time, _request_count
    uptime = time.time() - _start_time
    count = db.count() if db else 0
    return (
        f"# HELP apm_storage_detections_total Total detections stored\n"
        f"# TYPE apm_storage_detections_total gauge\n"
        f"apm_storage_detections_total {count}\n"
        f"# HELP apm_storage_requests_total Total HTTP requests handled\n"
        f"# TYPE apm_storage_requests_total counter\n"
        f"apm_storage_requests_total {_request_count}\n"
        f"# HELP apm_storage_uptime_seconds Service uptime in seconds\n"
        f"# TYPE apm_storage_uptime_seconds gauge\n"
        f"apm_storage_uptime_seconds {uptime:.1f}\n"
    )
