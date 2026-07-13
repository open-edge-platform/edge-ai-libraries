# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from src.config import settings, setup_logging
from src.core.event_manager import EventManager
from src.core.dedup.engine import DedupEngine
from src.core.ws_manager import ws_manager
from src.core.subscription import load_subscription_config, SubscriptionConfig
from src.schemas.monitor import AlertConfig, EscalationConfig
from src.schemas.request import (
    AlertActionRequest,
    AlertActionResponse,
    DedupConfig,
    Payload,
    ToolInvokeRequest,
    ToolInvokeResponse,
)
from src.agentic import (
    AlertActionAgent,
    get_available_tools,
    get_all_tools,
    reload_tools,
    register_mcp_tools,
    clear_mcp_tools,
)
from src.agentic.mcp_client import (
    initialize_mcp_servers,
    shutdown_mcp_servers,
    get_mcp_server_status,
    get_mcp_tools,
    get_mcp_servers,
)
from src.tools.snapshot_tool import capture_snapshot
from src.tools.webhook_tool import shutdown_webhook_session
from src.tools.mqtt_tool import shutdown_mqtt

setup_logging()
logger = logging.getLogger(__name__)

_startup_time: float = time.monotonic()

# ---------------------------------------------------------------------------
# Application state (initialised in lifespan)
# ---------------------------------------------------------------------------
agent: Optional[AlertActionAgent] = None
event_manager: EventManager = EventManager()
_dedup_engine: DedupEngine = DedupEngine()
_subscription_config: SubscriptionConfig = SubscriptionConfig()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent, _subscription_config

    logger.info(
        f"Starting Alert Agent Service | "
        f"ADK={'on' if settings.AGENT_MODE else 'off'} "
        f"MCP={'on' if settings.MCP_ENABLED else 'off'}"
    )

    # ── Subscription config ─────────────────────────────────────────────────
    _subscription_config = load_subscription_config(settings.SUBSCRIPTION_CONFIG_PATH)

    # ── MCP initialisation ──────────────────────────────────────────────────
    if settings.MCP_ENABLED:
        logger.info("Initialising MCP servers ...")
        mcp_tools, mcp_schemas = await initialize_mcp_servers()
        if mcp_tools:
            register_mcp_tools(mcp_tools, mcp_schemas)
        logger.info(f"MCP ready: {len(mcp_tools)} tool(s) available")
    else:
        mcp_tools = {}

    # ── Alert agent initialisation ──────────────────────────────────────────
    agent = AlertActionAgent()

    # Re-init ADK now that MCP tools are registered, so the LLM instruction
    # includes the full tool list
    if settings.MCP_ENABLED and mcp_tools and settings.AGENT_MODE:
        agent.reinit_adk()

    # ── Periodic dedup store cleanup task ───────────────────────────────────
    async def _dedup_cleanup_loop():
        """Evict expired entries from the dedup memory store every 60 seconds."""
        while True:
            try:
                await asyncio.sleep(60)
                evicted = await _dedup_engine._store.cleanup()
                if evicted:
                    logger.debug(f"Dedup cleanup: evicted {evicted} expired entries")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(f"Dedup cleanup error: {exc}")

    cleanup_task = asyncio.create_task(_dedup_cleanup_loop())

    logger.info("Alert Agent Service started and ready")

    yield

    # ── Graceful shutdown ───────────────────────────────────────────────────
    logger.info("Shutting down Alert Agent Service ...")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    # Close persistent tool connections
    await shutdown_webhook_session()
    shutdown_mqtt()

    if settings.MCP_ENABLED:
        clear_mcp_tools()
        await shutdown_mcp_servers()
    logger.info("Alert Agent Service stopped")


app = FastAPI(
    title="Alert Agent Service",
    description=(
        "Generic multimodal alert action dispatcher. "
        "Accepts text, image, audio, video, or binary payloads together with "
        "alert context and dispatches configured tools via Google ADK or "
        "rule-based mode."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API router with configurable prefix (default: /api/v1)
router = APIRouter()

ALERTS_INGEST_REQUEST_EXAMPLE = {
    "alert_type": "fire_detection",
    "source_id": "cam-01",
    "alert_name": "Fire Detection",
    "answer": "YES",
    "reason": "Visible flames near the loading bay door",
    "timestamp": "2026-06-19T08:30:00Z",
    "metadata": {
        "confidence": 0.95,
        "camera_id": "cam-01",
        "site": "warehouse-a",
    },
    "payload": {
        "severity": "critical",
        "evidence": [
            "Flame-colored region detected",
            "Rapid brightness increase",
        ],
    },
    "tools": ["log_alert", "trigger_webhook"],
}


def _require_agent() -> AlertActionAgent:
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialised")
    return agent


# ============================================================================
# Health
# ============================================================================

@router.get("/health", tags=["Observability"])
async def health():
    """Liveness probe — always returns 200 while the process is alive."""
    return {
        "status": "healthy",
        "adk_enabled": settings.AGENT_MODE,
        "mcp_enabled": settings.MCP_ENABLED,
        "uptime_seconds": round(time.monotonic() - _startup_time, 1),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


# ============================================================================
# Flexible alert ingestion (alert-service compatible)
# ============================================================================

@router.post(
    "/alerts",
    tags=["Alerts"],
    summary="Ingest alert payload",
    description=(
        "Accept a flexible JSON alert payload, matching the alert-service API. "
        "Unknown fields are preserved and normalized before the request is "
        "dispatched through the standard action pipeline."
    ),
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "additionalProperties": True,
                        "description": (
                            "Flexible alert-service compatible payload. "
                            "Common fields include alert_type, source_id, "
                            "alert_name, answer, reason, metadata, payload, "
                            "timestamp, and tools."
                        ),
                    },
                    "example": ALERTS_INGEST_REQUEST_EXAMPLE,
                }
            },
        }
    },
)
async def ingest_alert(request: Request) -> dict:
    """Accept a flexible JSON alert payload, matching alert-service API.

    Downstream callers can POST any JSON body.  The service normalises the
    payload into an ``AlertActionRequest`` and dispatches it through the
    standard action pipeline.  Unknown fields are preserved in a ``payloads``
    text entry so no data is lost.
    """
    try:
        raw_body = await request.json()
    except Exception:
        logger.exception("Failed to parse alert payload JSON; defaulting to empty payload")
        raw_body = {}

    body = raw_body if isinstance(raw_body, dict) else {}
    response_alert_type = body.get("alert_type") or body.get("alert_name") or "UNKNOWN"
    if not isinstance(response_alert_type, str):
        response_alert_type = str(response_alert_type)
    response_timestamp = datetime.now(timezone.utc).isoformat()

    # Normalise 'answer' from flexible inputs (bool, lowercase, etc.)
    raw_answer = body.get("answer", "YES")
    if isinstance(raw_answer, bool):
        answer = "YES" if raw_answer else "NO"
    else:
        answer = str(raw_answer).strip().upper()
        if answer in ("TRUE", "Y", "1"):
            answer = "YES"
        elif answer in ("FALSE", "N", "0"):
            answer = "NO"
    if answer not in ("YES", "NO"):
        answer = "YES"

    # Safely extract metadata and payload (must be dicts)
    metadata = body.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    payload_dict = body.get("payload", {})
    if not isinstance(payload_dict, dict):
        payload_dict = {}

    # Preserve the original event timestamp in metadata for downstream tools
    original_timestamp = body.get("timestamp")
    if original_timestamp and isinstance(original_timestamp, str):
        metadata.setdefault("_original_timestamp", original_timestamp)

    # --- source_id: try top-level, then common identifier fields in metadata ---
    source_id = body.get("source_id")
    if not source_id:
        for id_field in ("source_id", "camera_id", "sensor_id", "device_id",
                         "stream_id", "person_id", "alert_id"):
            val = metadata.get(id_field)
            if val:
                source_id = val
                break
    if not source_id:
        source_id = "unknown"
    if not isinstance(source_id, str):
        source_id = str(source_id)

    alert_name = body.get("alert_name")
    if alert_name is None:
        alert_name = body.get("alert_type", "UNKNOWN")
    if not isinstance(alert_name, str):
        alert_name = str(alert_name)

    alert_type = body.get("alert_type")
    if alert_type is not None and not isinstance(alert_type, str):
        alert_type = str(alert_type)

    # --- reason: try top-level, metadata, then synthesize from payload ---
    reason = body.get("reason")
    if not reason:
        reason = metadata.get("reason") or metadata.get("description")
    if not reason:
        reason = payload_dict.get("message") or metadata.get("message")
    if not reason:
        # Build a summary from evidence/severity when no explicit reason
        evidence = payload_dict.get("evidence") or metadata.get("evidence")
        severity = (payload_dict.get("severity") or metadata.get("severity") or "")
        if isinstance(evidence, list) and evidence:
            reason = "; ".join(str(e) for e in evidence[:5])
            if severity:
                reason = f"[{severity}] {reason}"
        elif severity:
            reason = f"Severity: {severity}"
    if not reason:
        reason = ""
    if not isinstance(reason, str):
        reason = str(reason)

    raw_consecutive_count = body.get("consecutive_count", 1)
    try:
        consecutive_count = int(raw_consecutive_count)
        if consecutive_count < 1:
            raise ValueError
    except (TypeError, ValueError):
        consecutive_count = 1

    raw_tools = body.get("tools", ["log_alert"])
    tools = raw_tools if isinstance(raw_tools, list) else ["log_alert"]

    tool_arguments = body.get("tool_arguments", {})
    if not isinstance(tool_arguments, dict):
        tool_arguments = {}

    payloads = body.get("payloads", [])
    if not isinstance(payloads, list):
        payloads = []

    # Build an AlertActionRequest from the flexible payload
    try:
        data = AlertActionRequest(
            source_id=source_id,
            alert_name=alert_name,
            alert_type=alert_type,
            answer=answer,
            reason=reason,
            consecutive_count=consecutive_count,
            escalated=body.get("escalated", False),
            tools=tools,
            tool_arguments=tool_arguments,
            payloads=payloads,
            metadata=metadata,
        )
        # If raw body has metadata not captured above, attach as text payload
        if metadata and not data.payloads:
            data.payloads = [Payload(
                kind="text",
                encoding="raw",
                data_text=json.dumps(body),
                metadata=metadata,
            )]

        await execute_action(data, original_payload=payload_dict)
    except Exception:
        logger.exception("Failed to dispatch alert payload")

    return {
        "status": "accepted",
        "alert_type": response_alert_type,
        "timestamp": response_timestamp,
    }


# ============================================================================
# Main dispatch endpoint
# ============================================================================

@router.post(
    "/actions/execute",
    response_model=AlertActionResponse,
    tags=["Actions"],
    summary="Dispatch alert actions",
    description=(
        "Submit an alert with optional multimodal payloads (text / image / audio / "
        "video / binary). The service runs the configured tools via ADK or "
        "rule-based dispatch and fans the result out to all SSE subscribers."
    ),
)
async def execute_action(data: AlertActionRequest, original_payload: Optional[dict] = None):
    _require_agent()

    if data.answer != "YES":
        return AlertActionResponse(
            event_id=data.event_id,
            source_id=data.source_id,
            alert_name=data.alert_name,
            actions_taken=[],
            duration_ms=0.0,
        )

    t0 = time.monotonic()

    # ── 1. Resolve subscription defaults (alert_type or alert_name lookup) ──
    sub = _subscription_config.get(data.alert_name) or (
        _subscription_config.get(data.alert_type) if data.alert_type else None
    )

    # Merge tools: request overrides subscription defaults (only if caller passed non-default list)
    effective_tools = list(data.tools)
    if not effective_tools or effective_tools == ["log_alert"]:
        if sub and sub.tools:
            effective_tools = list(sub.tools)

    # Merge tool_arguments: request overrides subscription defaults
    effective_tool_args = dict(sub.tool_arguments) if sub else {}
    effective_tool_args.update(data.tool_arguments)

    # Merge escalation: request overrides subscription defaults
    effective_escalation = data.escalation
    if effective_escalation is None and sub and sub.escalation:
        try:
            effective_escalation = EscalationConfig(**sub.escalation)
        except Exception:
            pass

    # ── 2. Dedup check ───────────────────────────────────────────────────────
    dedup_cfg: Optional[DedupConfig] = data.dedup
    if dedup_cfg is None and sub and sub.dedup:
        try:
            dedup_cfg = DedupConfig(**sub.dedup)
        except Exception:
            pass

    if dedup_cfg and dedup_cfg.enabled:
        dedup_context = {
            "source_id": data.source_id,
            "alert_name": data.alert_name,
            "alert_type": data.alert_type or data.alert_name,
            "reason": data.reason,
            "metadata": data.metadata,
        }
        if await _dedup_engine.is_duplicate(dedup_context, dedup_cfg):
            logger.info(f"[{data.event_id}] Deduplicated — skipping dispatch")
            return AlertActionResponse(
                event_id=data.event_id,
                source_id=data.source_id,
                alert_name=data.alert_name,
                actions_taken=[],
                duration_ms=round((time.monotonic() - t0) * 1000, 1),
            )

    # ── 3. Extract image bytes from payload ─────────────────────────────────
    image_bytes: Optional[bytes] = None
    image_mime_type: str = "image/jpeg"
    for p in data.payloads:
        if p.kind == "image":
            image_mime_type = p.mime_type
            if p.encoding == "base64" and p.data_base64:
                try:
                    image_bytes = base64.b64decode(p.data_base64)
                except Exception as exc:
                    logger.warning(f"[{data.event_id}] base64 image decode failed: {exc}")
            elif p.encoding == "uri" and p.uri:
                logger.info(
                    f"[{data.event_id}] image URI provided: {p.uri} "
                    "(snapshot will be skipped; pass encoding=base64 for disk snapshot)"
                )
            break

    # ── 4. Validate alert config ─────────────────────────────────────────────
    try:
        AlertConfig(
            name=data.alert_name,
            tools=effective_tools,
            tool_arguments=effective_tool_args,
            escalation=effective_escalation,
            enabled=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid alert config: {exc}")

    # ── 5. Capture snapshot (pre-dispatch, outside agent) ───────────────────
    snapshot_path: Optional[str] = None
    if "capture_snapshot" in effective_tools:
        snap = await capture_snapshot(
            source_id=data.source_id,
            alert_name=data.alert_name,
            image_bytes=image_bytes,
            mime_type=image_mime_type,
        )
        snapshot_path = snap.get("path")

    # ── 6. Dispatch remaining tools via agent ───────────────────────────────
    dispatch_cfg = AlertConfig(
        name=data.alert_name,
        tools=[t for t in effective_tools if t != "capture_snapshot"],
        tool_arguments=effective_tool_args,
        escalation=effective_escalation,
        enabled=True,
    )

    try:
        actions_taken = await agent.dispatch(
            source_id=data.source_id,
            alert_cfg=dispatch_cfg,
            answer=data.answer,
            reason=data.reason,
            consecutive_count=data.consecutive_count,
            escalated=data.escalated,
            snapshot_path=snapshot_path,
            metadata=data.metadata,
            original_payload=original_payload,
        )
    except Exception as exc:
        logger.error(f"[{data.event_id}] Dispatch failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Dispatch error: {exc}")

    if snapshot_path and "capture_snapshot" not in actions_taken:
        actions_taken = ["capture_snapshot"] + actions_taken

    duration_ms = round((time.monotonic() - t0) * 1000, 1)

    # ── 7. Fan out SSE + WebSocket events ────────────────────────────────────
    ts_now = datetime.now(tz=timezone.utc).isoformat()
    merged_metadata = {
        **data.metadata,
        "source_id": data.source_id,
        "reason": data.reason,
        "escalated": data.escalated,
        "consecutive_count": data.consecutive_count,
    }
    event_payload = {
        # alert-service compatible fields (AlertEnvelope.to_dict())
        "alert_type": data.alert_type or data.alert_name,
        "metadata": merged_metadata,
        "timestamp": ts_now,
        # agent-service extended fields
        "event_id": data.event_id,
        "source_id": data.source_id,
        "alert_name": data.alert_name,
        "answer": data.answer,
        "reason": data.reason,
        "actions_taken": actions_taken,
        "tools_requested": effective_tools,
        "consecutive_count": data.consecutive_count,
        "escalated": data.escalated,
        "snapshot_path": snapshot_path,
        "payload_kinds": [p.kind for p in data.payloads],
        "duration_ms": duration_ms,
    }
    await event_manager.broadcast("alert_action", event_payload)
    if ws_manager.active_count > 0:
        await ws_manager.broadcast(json.dumps(event_payload))

    return AlertActionResponse(
        event_id=data.event_id,
        source_id=data.source_id,
        alert_name=data.alert_name,
        actions_taken=actions_taken,
        snapshot_path=snapshot_path,
        duration_ms=duration_ms,
    )


# ============================================================================
# SSE stream
# ============================================================================

async def _event_generator(request: Request):
    """Generator yielding alert_action and keepalive SSE events."""
    queue = await event_manager.subscribe()
    try:
        yield {
            "event": "init",
            "data": json.dumps({
                "message": "Connected to Alert Agent Service SSE stream",
                "adk_enabled": settings.AGENT_MODE,
                "mcp_enabled": settings.MCP_ENABLED,
            }),
        }
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield {"event": event["event"], "data": json.dumps(event["data"])}
            except asyncio.TimeoutError:
                yield {"event": "keepalive", "data": json.dumps({"ts": time.monotonic()})}
    except (asyncio.CancelledError, GeneratorExit):
        pass
    except Exception as exc:
        logger.error(f"SSE error: {exc}")
        yield {"event": "error", "data": json.dumps({"message": str(exc)})}
    finally:
        await event_manager.unsubscribe(queue)


@router.get("/events", tags=["Streaming"])
async def sse_events(request: Request):
    """
    Server-Sent Events stream.

    Event types emitted:
    - ``init``          — on connect (service info)
    - ``alert_action``  — after each successful dispatch
    - ``keepalive``     — every 15 s to prevent proxy timeouts
    - ``error``         — on unexpected SSE error
    """
    return EventSourceResponse(
        _event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================================
# WebSocket stream
# ============================================================================

@router.websocket("/ws")
async def websocket_stream(ws: WebSocket):
    """WebSocket endpoint — same alert_action events as SSE."""
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ============================================================================
# Tools management
# ============================================================================

@router.get("/tools", tags=["Tools"])
async def list_tools():
    """List all registered action tools (built-in + MCP) and their status."""
    tools = get_available_tools()
    return JSONResponse(content={"tools": tools, "count": len(tools)})


@router.post("/tools/{tool_name}/invoke", tags=["Tools"])
async def invoke_tool(
    tool_name: str,
    request: ToolInvokeRequest = Body(default=None),
):
    """Manually invoke a registered built-in tool (for testing / debugging)."""
    all_tools, _ = get_all_tools()
    fn = all_tools.get(tool_name)
    if fn is None:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    params = request.parameters if request else {}
    t0 = time.monotonic()
    try:
        result = await fn(**params)
        return ToolInvokeResponse(
            tool=tool_name,
            status="success",
            result=result,
            duration_ms=round((time.monotonic() - t0) * 1000, 1),
        )
    except Exception as exc:
        return ToolInvokeResponse(
            tool=tool_name,
            status="error",
            result={"error": str(exc)},
            duration_ms=round((time.monotonic() - t0) * 1000, 1),
        )


@router.post("/tools/reload", tags=["Tools"])
async def reload_tools_endpoint():
    """Hot-reload resources/tools.json without restarting the service."""
    count = reload_tools()
    if agent is not None:
        agent.reinit_adk()
    return JSONResponse(content={"status": "ok", "tools_loaded": count})


# ============================================================================
# MCP management
# ============================================================================

@router.get("/mcp/status", tags=["MCP"])
async def mcp_status():
    """Get connection status of all configured MCP servers."""
    if not settings.MCP_ENABLED:
        return JSONResponse(content={"enabled": False, "servers": [], "total_tools": 0})

    servers = get_mcp_server_status()
    tools = get_mcp_tools()
    return JSONResponse(content={
        "enabled": True,
        "servers": servers,
        "total_tools": len(tools),
    })


@router.get("/mcp/tools", tags=["MCP"])
async def mcp_tools_list():
    """List all tools discovered from connected MCP servers."""
    if not settings.MCP_ENABLED:
        return JSONResponse(content={"tools": [], "count": 0})

    tools = get_mcp_tools()
    return JSONResponse(content={
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "server": t.server,
                "input_schema": t.input_schema,
            }
            for t in tools.values()
        ],
        "count": len(tools),
    })


@router.post("/mcp/reload", tags=["MCP"])
async def mcp_reload():
    """Reconnect to all MCP servers and refresh the tool registry."""
    if not settings.MCP_ENABLED:
        return JSONResponse(content={
            "status": "skipped",
            "reason": "MCP is disabled",
            "tools_loaded": 0,
        })

    try:
        clear_mcp_tools()
        await shutdown_mcp_servers()
        mcp_tools, mcp_schemas = await initialize_mcp_servers()
        if mcp_tools:
            register_mcp_tools(mcp_tools, mcp_schemas)
        if agent is not None:
            agent.reinit_adk()
        return JSONResponse(content={"status": "ok", "tools_loaded": len(mcp_tools)})
    except Exception as exc:
        logger.error(f"MCP reload failed: {exc}")
        raise HTTPException(status_code=500, detail=f"MCP reload failed: {exc}")


@router.post("/mcp/tools/{tool_name}/invoke", tags=["MCP"])
async def invoke_mcp_tool(
    tool_name: str,
    request: ToolInvokeRequest = Body(default=None),
):
    """Manually invoke an MCP tool (for testing / debugging)."""
    if not settings.MCP_ENABLED:
        raise HTTPException(status_code=503, detail="MCP is disabled")

    tools = get_mcp_tools()
    tool = tools.get(tool_name)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"MCP tool '{tool_name}' not found")

    servers = get_mcp_servers()
    server = servers.get(tool.server)
    if server is None:
        raise HTTPException(
            status_code=503,
            detail=f"MCP server '{tool.server}' is not connected",
        )

    params = request.parameters if request else {}
    t0 = time.monotonic()
    try:
        result = await server.call_tool(tool_name, params)
        return ToolInvokeResponse(
            tool=tool_name,
            status="success" if result.get("status") != "error" else "error",
            result=result,
            duration_ms=round((time.monotonic() - t0) * 1000, 1),
        )
    except Exception as exc:
        return ToolInvokeResponse(
            tool=tool_name,
            status="error",
            result={"error": str(exc)},
            duration_ms=round((time.monotonic() - t0) * 1000, 1),
        )


# ============================================================================
# Subscription config management
# ============================================================================

@router.get("/subscriptions", tags=["Subscriptions"])
async def list_subscriptions():
    """List all loaded subscription entries."""
    return JSONResponse(content={
        "subscriptions": [
            {
                "alert_name": s.alert_name,
                "tools": s.tools,
                "tool_arguments": s.tool_arguments,
                "dedup": s.dedup,
                "escalation": s.escalation,
            }
            for s in _subscription_config.subscriptions
        ],
        "count": len(_subscription_config.subscriptions),
    })


@router.post("/subscriptions/reload", tags=["Subscriptions"])
async def reload_subscriptions():
    """Hot-reload resources/config.yaml subscription defaults."""
    global _subscription_config
    _subscription_config = load_subscription_config(settings.SUBSCRIPTION_CONFIG_PATH)
    return JSONResponse(content={
        "status": "ok",
        "subscriptions_loaded": len(_subscription_config.subscriptions),
    })


# ============================================================================
# Mount router on app with API prefix
# ============================================================================

app.include_router(router, prefix=settings.API_V1_PREFIX)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
