import logging
import os
from asyncio import Lock
from typing import Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

router = APIRouter()
logger = logging.getLogger("api.routes.metrics")
logger.setLevel(os.environ.get("METRICS_LOG_LEVEL", "INFO").upper())

# Single collector websocket (None if not connected)
collector_ws: Optional[WebSocket] = None
collector_lock = Lock()

# Set of client websockets
client_connections: Set[WebSocket] = set()
clients_lock = Lock()


@router.websocket("/ws/collector")
async def collector_websocket(websocket: WebSocket):
    """
    **WebSocket endpoint for a single metrics collector.**

    ## Operation

    1. Accepts exactly one collector connection at a time
    2. Receives metric batches from the collector as JSON (mode="binary")
    3. Broadcasts every received payload to all connected client websockets at /ws/clients as JSON (mode="text")

    ## Protocol

    - Client opens WebSocket handshake
    - On success, server replies with HTTP 101 (Switching Protocols)
    - If another collector is already connected:
      - New connection is accepted
      - Sent message: "Collector already connected; only one allowed."
      - Then closed with code 1008 (Policy Violation)

    ## Conditions

    ### ✅ Success
    - Single collector connected and sending JSON messages
    - All messages are forwarded to currently connected clients

    ### ❌ Failure
    - Second collector connection attempt → connection closed with 1008
    - Network/protocol error → WebSocketDisconnect, logged and cleaned up
    - Unexpected exception → logged; collector slot is released

    ## Example Message

    Collector request (JSON):
    ```json
    [
      {
        "name": "total_fps",
        "description": "Total FPS over all streams",
        "timestamp": 1715000000000,
        "value": 512.4
      },
      {
        "name": "cpu_usage",
        "description": "CPU utilization in percent",
        "timestamp": 1715000000000,
        "value": 75.3
      }
    ]
    ```

    Forwarded to /ws/clients: Same JSON payload as received.
    """
    global collector_ws
    await websocket.accept()
    logger.debug("Collector connected from %s", websocket.client)
    async with collector_lock:
        if collector_ws is not None:
            logger.warning("Rejecting new collector: one is already connected.")
            # Optionally, send a message then close
            await websocket.send_text("Collector already connected; only one allowed.")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        collector_ws = websocket
    try:
        while True:
            data = await websocket.receive_json(mode="binary")
            logger.debug("Received metrics from collector: %s", data)

            # Broadcast to all clients
            disconnects = []
            async with clients_lock:
                clients = list(client_connections)
            for client in clients:
                try:
                    await client.send_json(data, mode="text")
                    logger.debug("Forwarded metrics to client %s", client.client)
                except Exception as e:
                    logger.error("Error sending to client %s: %s", client.client, e)
                    disconnects.append(client)
            # Cleanup disconnected clients
            if disconnects:
                async with clients_lock:
                    for client in disconnects:
                        client_connections.discard(client)
                logger.debug("Cleaned up %d disconnected clients", len(disconnects))
    except WebSocketDisconnect:
        logger.info("Collector disconnected: %s", websocket.client)
    except Exception as e:
        logger.error("Exception in collector handler: %s", e)
    finally:
        async with collector_lock:
            if collector_ws == websocket:
                collector_ws = None
        logger.debug("Collector slot released")


@router.websocket("/ws/clients")
async def clients_websocket(websocket: WebSocket):
    """
    **WebSocket endpoint for clients that receive live metrics.**

    ## Operation

    1. Accepts any number of client connections
    2. Keeps connection open and pushes every metrics payload received from /ws/collector as JSON to each client
    3. Messages sent from clients are ignored and only logged

    ## Protocol

    - Client opens WebSocket handshake
    - On success, server replies with HTTP 101 (Switching Protocols)
    - Client should keep connection alive (e.g. via ping/pong)
    - Text messages sent by the client are read but not processed

    ## Conditions

    ### ✅ Success
    - Client connection stays open and receives broadcast metrics

    ### ❌ Failure
    - Network/protocol error → WebSocketDisconnect, connection removed
    - Unexpected exception → logged; connection removed from the set

    ## Example Message

    Message received by client:
    ```json
    [
      {
        "name": "total_fps",
        "description": "Total FPS over all streams",
        "timestamp": 1715000000000,
        "value": 512.4
      }
    ]
    ```
    """
    await websocket.accept()
    logger.debug("Client connected: %s", websocket.client)
    async with clients_lock:
        client_connections.add(websocket)
    try:
        while True:
            # Either wait for ping/pong, or just sleep to keep connection open.
            msg = await websocket.receive_text()
            logger.debug("Received message from client (ignored): %s", msg)
    except WebSocketDisconnect:
        logger.debug("Client disconnected: %s", websocket.client)
    except Exception as e:
        logger.error("Exception in client handler: %s", e)
    finally:
        async with clients_lock:
            client_connections.discard(websocket)
