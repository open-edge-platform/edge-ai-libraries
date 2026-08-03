# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""EventManager — SSE pub/sub system for real-time event broadcasting."""

import asyncio
import logging
from typing import Set

logger = logging.getLogger(__name__)


class EventManager:
    """
    Manages SSE subscriptions and event broadcasting.

    Usage:
        manager = EventManager()
        queue = await manager.subscribe()   # client connects
        await manager.broadcast("alert_action", {"source_id": "cam1", ...})
        await manager.unsubscribe(queue)    # client disconnects
    """

    def __init__(self, max_queue_size: int = 50):
        self._subscribers: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        self._max_queue_size = max_queue_size

    async def subscribe(self) -> asyncio.Queue:
        """Register a new SSE subscriber; returns a queue for that connection."""
        queue = asyncio.Queue(maxsize=self._max_queue_size)
        async with self._lock:
            self._subscribers.add(queue)
        logger.info(f"SSE subscriber added. Total: {len(self._subscribers)}")
        return queue

    async def unsubscribe(self, queue: asyncio.Queue):
        """Remove an SSE subscriber."""
        async with self._lock:
            self._subscribers.discard(queue)
        logger.info(f"SSE subscriber removed. Total: {len(self._subscribers)}")

    async def broadcast(self, event_type: str, data: dict):
        """
        Send an event to all connected SSE subscribers.

        Slow subscribers (full queues) are automatically removed.
        """
        if not self._subscribers:
            return

        payload = {"event": event_type, "data": data}

        async with self._lock:
            subscribers = list(self._subscribers)

        dead_queues = []
        for queue in subscribers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                dead_queues.append(queue)
                logger.warning("Removing slow SSE subscriber (queue full)")

        if dead_queues:
            async with self._lock:
                for q in dead_queues:
                    self._subscribers.discard(q)

    @property
    def subscriber_count(self) -> int:
        """Current number of connected SSE subscribers."""
        return len(self._subscribers)
