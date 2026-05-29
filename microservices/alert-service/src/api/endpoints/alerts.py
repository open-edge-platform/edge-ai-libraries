"""Alert ingestion endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from src.core.models import AlertEnvelope

router = APIRouter(tags=["alerts"])


@router.post("/alerts")
async def ingest_alert(request: Request) -> dict:
    """Accept a flexible JSON alert payload, enqueue for async processing."""
    body: dict[str, Any] = await request.json()
    envelope = AlertEnvelope.from_raw(body)

    worker = request.app.state.worker
    await worker.enqueue(envelope)

    return {
        "status": "accepted",
        "alert_type": envelope.alert_type,
        "timestamp": envelope.timestamp,
    }
