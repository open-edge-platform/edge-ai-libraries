"""WebSocket endpoint for real-time alert streaming."""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.delivery.ws_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """Accept a WebSocket connection and keep it alive for alert broadcasts."""
    await ws_manager.connect(ws)
    try:
        while True:
            # Keep connection alive; ignore any client messages
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
