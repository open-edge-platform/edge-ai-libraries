# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from prometheus_client.parser import text_string_to_metric_families

from .settings import get_settings

router = APIRouter(tags=["sse"])

_STREAM_UI_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Metrics Stream</title>
</head>
<body>
  <h1>Metrics Stream</h1>
  <pre id="output"></pre>
  <script>
    const es = new EventSource("/metrics/stream");
    es.onmessage = (e) => {
      const data = JSON.parse(e.data);
      document.getElementById("output").textContent = JSON.stringify(data, null, 2);
    };
  </script>
</body>
</html>"""


async def fetch_metrics() -> str:
    settings = get_settings()
    url = f"{settings.prometheus_telegraf_endpoint}/metrics"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=5)
        resp.raise_for_status()

    ts = int(datetime.now(UTC).timestamp() * 1000)
    metrics = []
    for family in text_string_to_metric_families(resp.text):
        for sample in family.samples:
            metrics.append({
                "name": sample.name,
                "labels": dict(sample.labels),
                "value": sample.value,
                "timestamp": int(sample.timestamp * 1000) if sample.timestamp else ts,
            })

    return json.dumps({"timestamp": ts, "metrics": metrics})


async def event_stream():
    settings = get_settings()
    interval = settings.prometheus_poller_interval_ms / 1000
    while True:
        try:
            data = await fetch_metrics()
            yield f"data: {data}\n\n"
        except Exception as e:
            ts = int(datetime.now(UTC).timestamp() * 1000)
            yield f"data: {json.dumps({'error': str(e), 'timestamp': ts})}\n\n"
        await asyncio.sleep(interval)


@router.get("/metrics/stream")
async def metrics_stream(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept and "text/event-stream" not in accept:
        return HTMLResponse(content=_STREAM_UI_HTML)
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


