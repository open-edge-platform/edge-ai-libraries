# SPDX-License-Identifier: Apache-2.0

"""
API routes for timeseries pipeline data (wind turbine anomaly detection PoC).

- Reads ingestion data from a JSONL file on the shared /metadata volume
- Polls Kapacitor logs directly for analytics timing metrics
- No extra Docker service needed
"""

import asyncio
import json
import logging
import os
import re

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter()
logger = logging.getLogger("api.routes.timeseries")

METADATA_DIR = os.getenv("METADATA_DIR", "/metadata")
INGESTION_FILE = os.path.join(METADATA_DIR, "timeseries-ingestion.jsonl")

RE_INFERENCE = re.compile(r"Inference time:\s*([\d.]+)\s*milliseconds")
RE_E2E = re.compile(r"End to end time:\s*([\d.]+)\s*milliseconds")
RE_POINT_TIME = re.compile(r"Processing point time:\s*(\d+)")


def _read_ingestion_snapshot(limit: int = 100) -> list[dict]:
    """Read last N records from the ingestion JSONL file."""
    if not os.path.exists(INGESTION_FILE):
        return []
    records: list[dict] = []
    try:
        with open(INGESTION_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        return []
    return records[-limit:]


DOCKER_SOCKET = "/var/run/docker.sock"
TSAM_CONTAINER = "ia-time-series-analytics-microservice"


def _fetch_kapacitor_analytics() -> list[dict]:
    """Read TSAM container logs via Docker Engine API and extract timing records."""
    if not os.path.exists(DOCKER_SOCKET):
        logger.debug("Docker socket not available at %s", DOCKER_SOCKET)
        return []

    url = f"http://docker/containers/{TSAM_CONTAINER}/logs"
    params = {"stdout": "1", "stderr": "1", "tail": "200", "timestamps": "1"}
    try:
        transport = httpx.HTTPTransport(uds=DOCKER_SOCKET)
        with httpx.Client(transport=transport, timeout=5) as client:
            resp = client.get(url, params=params)
            if resp.status_code != 200:
                logger.debug("Docker logs returned %d", resp.status_code)
                return []
            log_bytes = resp.content
    except Exception as e:
        logger.debug("Could not fetch TSAM container logs: %s", e)
        return []

    # Docker multiplexed stream: each frame has 8-byte header (stream type + size)
    # Parse frames to extract text
    lines: list[str] = []
    offset = 0
    while offset + 8 <= len(log_bytes):
        frame_size = int.from_bytes(log_bytes[offset + 4 : offset + 8], "big")
        if offset + 8 + frame_size > len(log_bytes):
            break
        frame_data = log_bytes[offset + 8 : offset + 8 + frame_size]
        lines.append(frame_data.decode("utf-8", errors="replace"))
        offset += 8 + frame_size

    records: list[dict] = []
    current_inf: float | None = None
    current_e2e: float | None = None
    current_pt: int | None = None

    for line in lines:
        m = RE_INFERENCE.search(line)
        if m:
            current_inf = float(m.group(1))
        m = RE_E2E.search(line)
        if m:
            current_e2e = float(m.group(1))
        m = RE_POINT_TIME.search(line)
        if m:
            current_pt = int(m.group(1))

        if current_inf is not None and current_e2e is not None and current_pt is not None:
            records.append({
                "inference_time_ms": current_inf,
                "end_to_end_time_ms": current_e2e,
                "processing_point_time": current_pt,
            })
            current_inf = None
            current_e2e = None
            current_pt = None

    return records


@router.get("/data")
async def get_timeseries_data(limit: int = 100):
    """
    # Get Timeseries Pipeline Data

    Returns ingestion sensor values and analytics timing metrics in one call.
    """
    limit = min(limit, 1000)
    ingestion = _read_ingestion_snapshot(limit)
    analytics = _fetch_kapacitor_analytics()[-limit:]
    return JSONResponse(content={"ingestion": ingestion, "analytics": analytics})


async def _tail_ingestion():
    """SSE generator that tails the ingestion JSONL file."""
    waited = 0
    while not os.path.exists(INGESTION_FILE) and waited < 60:
        yield ": waiting\n\n"
        await asyncio.sleep(3)
        waited += 3

    if not os.path.exists(INGESTION_FILE):
        yield "data: {\"error\": \"No ingestion data yet\"}\n\n"
        return

    with open(INGESTION_FILE, "r") as f:
        f.seek(0, 2)
        while True:
            line = f.readline()
            if line:
                line = line.strip()
                if line:
                    yield f"data: {line}\n\n"
            else:
                yield ": keepalive\n\n"
                await asyncio.sleep(2)


@router.get("/ingestion/stream")
async def stream_ingestion():
    """SSE stream of ingestion sensor data."""
    return StreamingResponse(
        _tail_ingestion(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
