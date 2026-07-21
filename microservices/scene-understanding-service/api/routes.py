# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""REST API routes for Store-wide Loss Prevention."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
import structlog

from services.alert_service_client import AlertServiceClient
from services.config import ConfigService
from services.session_manager import SessionManager

logger = structlog.get_logger(__name__)

router = APIRouter()


def _get_alert_service_client(request: Request) -> AlertServiceClient:
    return request.app.state.alert_service_client


def _get_session_manager(request: Request) -> SessionManager:
    return request.app.state.session_manager


def _get_config(request: Request) -> ConfigService:
    return request.app.state.config


# ---- Alerts ------------------------------------------------------------------

@router.get("/alerts", response_model=List[Dict[str, Any]])
async def get_alerts(
    request: Request,
    alert_type: Optional[str] = Query(None, description="Filter by alert type"),
    object_id: Optional[str] = Query(None, description="Filter by person object_id"),
    limit: int = Query(50, ge=1, le=500),
) -> List[Dict[str, Any]]:
    """Proxy to alert-service for recent alerts."""
    client = _get_alert_service_client(request)
    result = await client.get_alerts(alert_type=alert_type, object_id=object_id, limit=limit)
    return result or []


@router.get("/alerts/count")
async def get_alert_count(request: Request) -> Dict[str, int]:
    client = _get_alert_service_client(request)
    alerts = await client.get_alerts(limit=1)
    # alert-service doesn't expose a count endpoint; return 0 if unavailable
    return {"total": len(alerts) if alerts else 0}


# ---- Sessions ----------------------------------------------------------------

@router.get("/sessions", response_model=List[Dict[str, Any]])
async def get_sessions(request: Request, include_pending: bool = False) -> List[Dict[str, Any]]:
    """Return active person sessions with per-zone visit summary.

    By default, only sessions whose SceneScape re-id state has progressed
    beyond initial collection are returned, so flickering/transient ghost
    tracks don't show up in the UI.  Pass ?include_pending=true to see
    everything (including ``pending_collection`` tracks).
    """
    sm = _get_session_manager(request)
    config = _get_config(request)
    sessions = sm.get_all_sessions()
    if not include_pending:
        sessions = {
            k: s for k, s in sessions.items()
            if not s.reid_state
            or s.reid_state in ("matched", "query_no_match")
        }
    return [_serialize_session(s, config) for s in sessions.values()]


@router.get("/sessions/{object_id}")
async def get_session_detail(request: Request, object_id: str, scene_id: str = "") -> Dict[str, Any]:
    """Return full detail for a single person session including zone visit history."""
    sm = _get_session_manager(request)
    config = _get_config(request)
    session = sm.get_session(object_id, scene_id=scene_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _serialize_session(session, config, include_visits=True)


def _serialize_session(session, config: ConfigService, include_visits: bool = False) -> Dict[str, Any]:
    """Build a JSON-friendly session dict with resolved zone names and dwell summaries."""
    # Per-zone summary: name, type, visit count, total dwell
    zone_summary: Dict[str, Dict[str, Any]] = {}
    for visit in session.region_visits:
        rid = visit.region_id
        if rid not in zone_summary:
            zone_summary[rid] = {
                "region_id": rid,
                "zone_name": config.get_zone_name(rid) or visit.region_name,
                "zone_type": visit.zone_type,
                "visit_count": 0,
                "total_dwell_seconds": 0.0,
                "currently_inside": rid in session.current_zones,
            }
        zone_summary[rid]["visit_count"] += 1
        zone_summary[rid]["total_dwell_seconds"] += round(visit.duration_seconds, 1)

    scene_name = config.get_scene_id_reverse(session.scene_id) or session.scene_id or ""

    result: Dict[str, Any] = {
        "object_id": session.object_id,
        "scene_name": scene_name,
        "first_seen": session.first_seen.isoformat(),
        "last_seen": session.last_seen.isoformat(),
        "current_cameras": session.current_cameras,
        "current_zones": {
            zid: {
                "zone_name": config.get_zone_name(zid) or zid,
                "zone_type": config.get_zone_type(zid) or "UNKNOWN",
                "entry_time": ts,
            }
            for zid, ts in session.current_zones.items()
        },
        "visited_checkout": session.visited_checkout,
        "visited_high_value": session.visited_high_value,
        "visited_exit": session.visited_exit,
        "concealment_suspected": session.concealment_suspected,
        "zone_summary": list(zone_summary.values()),
        "loiter_alerted": {
            config.get_zone_name(zid) or zid: v
            for zid, v in session.loiter_alerted.items()
        },
        "frame_buffer_size": len(session.frame_buffer),
    }

    if include_visits:
        result["visit_history"] = [
            {
                "region_id": v.region_id,
                "zone_name": config.get_zone_name(v.region_id) or v.region_name,
                "zone_type": v.zone_type,
                "entry_time": v.entry_time.isoformat(),
                "exit_time": v.exit_time.isoformat() if v.exit_time else None,
                "dwell_seconds": round(v.duration_seconds, 1),
            }
            for v in session.region_visits
        ]

    return result


@router.get("/sessions/count")
async def get_session_count(request: Request) -> Dict[str, Any]:
    sm = _get_session_manager(request)
    sessions = sm.get_all_sessions()
    # Count unique persons per camera (a person on multiple cameras counts once per camera)
    per_camera: Dict[str, int] = {}
    for s in sessions.values():
        for cam in s.current_cameras:
            per_camera[cam] = per_camera.get(cam, 0) + 1
    return {
        "active_sessions": len(sessions),
        "per_camera": per_camera,
    }


# ---- Health ------------------------------------------------------------------

@router.get("/status")
async def get_status(request: Request) -> Dict[str, Any]:
    """Service health and basic statistics."""
    sm = _get_session_manager(request)
    config = _get_config(request)
    zones = config.get_zones()
    return {
        "status": "operational",
        "active_sessions": sm.get_active_count(),
        "zones_configured": len(zones),
        "zone_types": {
            zt: sum(1 for z in zones.values() if z.get("type") == zt)
            for zt in ("HIGH_VALUE", "CHECKOUT", "EXIT", "RESTRICTED")
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


# ---- Zones (Option A + C) ---------------------------------------------------

class ZoneInput(BaseModel):
    name: str
    type: str  # HIGH_VALUE | CHECKOUT | EXIT | RESTRICTED

VALID_ZONE_TYPES = {"HIGH_VALUE", "CHECKOUT", "EXIT", "RESTRICTED"}


@router.get("/zones")
async def get_zones(request: Request) -> Dict[str, Any]:
    """Return all configured zone mappings."""
    config = _get_config(request)
    return config.get_zones()


@router.put("/zones/{region_id}")
async def set_zone(
    request: Request, region_id: str, body: ZoneInput
) -> Dict[str, Any]:
    """Add or update a zone mapping at runtime (no restart needed)."""
    if body.type not in VALID_ZONE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid zone type '{body.type}'. Must be one of: {sorted(VALID_ZONE_TYPES)}",
        )
    config = _get_config(request)
    config.set_zone(region_id, body.name, body.type)
    return {"region_id": region_id, "name": body.name, "type": body.type}


@router.delete("/zones/{region_id}")
async def delete_zone(request: Request, region_id: str) -> Dict[str, str]:
    """Remove a zone mapping."""
    config = _get_config(request)
    removed = config.remove_zone(region_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Zone not found")
    return {"status": "removed", "region_id": region_id}


@router.post("/zones/discover")
async def discover_zones(request: Request) -> Dict[str, Any]:
    """Trigger re-discovery of zones from SceneScape API."""
    ss_client = getattr(request.app.state, "scenescape_client", None)
    if not ss_client:
        raise HTTPException(status_code=503, detail="SceneScape client not configured")

    config = _get_config(request)
    regions = await ss_client.fetch_regions()
    if not regions:
        return {"status": "no_regions", "discovered": 0, "total": len(config.get_zones())}

    new_zones = ss_client.map_zones(regions)
    added = config.merge_zones(new_zones)
    return {
        "status": "ok",
        "discovered": len(new_zones),
        "added": added,
        "total": len(config.get_zones()),
    }


@router.get("/zones/names")
async def get_zone_name_map(request: Request) -> Dict[str, str]:
    """Return the zone name → zone type map from config."""
    config = _get_config(request)
    return config.get_zone_name_map()
