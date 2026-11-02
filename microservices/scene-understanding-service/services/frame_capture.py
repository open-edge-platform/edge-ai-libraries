# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Frame capture service.

Receives camera-image MQTT messages, decides which active HIGH_VALUE-zone
sessions the frame belongs to, and stores the cropped frame to SeaweedFS
via ``FrameManager``.

This service does NOT publish ba/requests -- the
``BehavioralAnalysisOrchestrator`` owns the BA cadence and emits one
ba/requests per batch of stored frames.
"""

from __future__ import annotations

import asyncio
import base64
import threading
from datetime import datetime, timezone
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class CapturedFrameTracker:
    """Per (scene_id, person_id, region_id) state shared between
    FrameCaptureService and BehavioralAnalysisOrchestrator.

    Holds two pieces of state:
      * ``_latest`` -- the most recent SceneScape ISO timestamp the
        capture service has stored for this key. Read once per cycle by
        the orchestrator and published as ``last_frame_ts``.
      * ``_remaining`` -- a per-cycle quota the orchestrator sets
        immediately before issuing its burst of ``getimage`` commands.
        FrameCaptureService decrements it on each accepted frame and
        ignores further frames once it hits zero, so we never store more
        than ``frame_capture_count`` frames per cycle even if SceneScape
        publishes additional unsolicited images on the camera topic.
    """

    def __init__(self) -> None:
        self._latest: dict[tuple[str, str, str], str] = {}
        self._remaining: dict[tuple[str, str, str], int] = {}
        self._lock = threading.Lock()

    # ---- last-frame-ts ----------------------------------------------------

    def record(self, scene_id: str, person_id: str, region_id: str, scenescape_frame_ts: str) -> None:
        if not scenescape_frame_ts:
            return
        with self._lock:
            self._latest[(scene_id, person_id, region_id)] = scenescape_frame_ts

    def get_latest(self, scene_id: str, person_id: str, region_id: str) -> Optional[str]:
        with self._lock:
            return self._latest.get((scene_id, person_id, region_id))

    def clear(self, scene_id: str, person_id: str, region_id: str) -> None:
        with self._lock:
            self._latest.pop((scene_id, person_id, region_id), None)
            self._remaining.pop((scene_id, person_id, region_id), None)

    # ---- per-cycle quota --------------------------------------------------

    def set_remaining(self, scene_id: str, person_id: str, region_id: str, count: int) -> None:
        """Reset the per-cycle frame quota (called by orchestrator)."""
        with self._lock:
            self._remaining[(scene_id, person_id, region_id)] = max(int(count), 0)

    def try_consume(self, scene_id: str, person_id: str, region_id: str) -> bool:
        """Atomically claim one slot for this cycle.

        Returns True if the caller may store this frame; False if the
        cycle's quota has already been exhausted (or never set).
        """
        key = (scene_id, person_id, region_id)
        with self._lock:
            remaining = self._remaining.get(key, 0)
            if remaining <= 0:
                return False
            self._remaining[key] = remaining - 1
            return True


class FrameCaptureService:
    """Glue between camera image events and frame storage."""

    def __init__(
        self,
        config,
        session_manager,
        frame_manager,
        frame_tracker=None,
    ) -> None:
        self._config = config
        self._sessions = session_manager
        self._frame_mgr = frame_manager
        self._tracker = frame_tracker

    async def on_camera_image(self, camera_name: str, data: dict) -> None:
        """Handle a fresh image from one camera.

        For each active session whose person is currently in a HIGH_VALUE
        zone visible to ``camera_name``, store the frame.
        """
        image_b64 = data.get("image", data.get("data", ""))
        if not image_b64:
            return

        scenescape_frame_ts = data.get("timestamp", "")

        try:
            # Offload CPU-intensive base64 decode (~5-15ms for HD frames)
            # to the thread pool so the event loop stays responsive.
            image_bytes = await asyncio.to_thread(base64.b64decode, image_b64)
        except Exception:
            logger.exception("Invalid base64 image", camera=camera_name)
            return

        # Use SceneScape's timestamp for the stored frame so the bucket
        # filename (ms_since_epoch) matches the `last_frame_ts` we publish
        # on ba/requests. Drop the frame if SceneScape did not give us a
        # parseable timestamp -- BA needs the two to be aligned.
        if not scenescape_frame_ts:
            logger.warning("Missing scenescape timestamp; dropping frame", camera=camera_name)
            return
        try:
            frame_ts = datetime.fromisoformat(scenescape_frame_ts.replace("Z", "+00:00"))
        except ValueError:
            logger.warning(
                "Unparseable scenescape timestamp; dropping frame",
                camera=camera_name, scenescape_frame_ts=scenescape_frame_ts,
            )
            return

        for session in self._sessions.get_all_sessions().values():
            if camera_name not in session.current_cameras:
                continue

            # Find the HIGH_VALUE zone the person is in (if any).
            zone_id: Optional[str] = None
            for zid in session.current_zones:
                if self._config.get_zone_type(zid) == "HIGH_VALUE":
                    zone_id = zid
                    break
            if zone_id is None:
                continue

            entry_ts_iso = session.current_zones.get(zone_id, "")

            # Enforce the orchestrator's per-cycle quota: store at most
            # `frame_capture_count` frames per (scene, person, region)
            # cycle, regardless of how many images SceneScape pushes us.
            if self._tracker is not None and not self._tracker.try_consume(
                session.scene_id, session.object_id, zone_id,
            ):
                continue

            try:
                # Offload synchronous S3 PUT to thread pool to avoid
                # blocking the event loop (~5-50ms per write).
                key = await asyncio.to_thread(
                    self._frame_mgr.store_person_frame,
                    session.object_id, image_bytes, frame_ts,
                    region_id=zone_id,
                    entry_timestamp=entry_ts_iso,
                    scene_id=session.scene_id,
                )
            except Exception:
                logger.exception(
                    "Failed to store person frame",
                    person_id=session.object_id, region_id=zone_id,
                )
                continue
            session.add_frame_key(key)

            if self._tracker is not None:
                self._tracker.record(
                    session.scene_id, session.object_id, zone_id, scenescape_frame_ts,
                )
