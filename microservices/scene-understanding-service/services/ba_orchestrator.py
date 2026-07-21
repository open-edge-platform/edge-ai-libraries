# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Behavioral Analysis Orchestrator -- owns the per-visit BA cadence.

For each (person, region) HIGH_VALUE visit we run a single asyncio task
that repeats the following "frame-capture cycle":

    1. emit ``frame_capture_count`` getimage commands evenly spread across
       ``frame_capture_interval_seconds`` seconds. Camera replies are
       stored in the behavioral-frames bucket by FrameCaptureService.
    2. publish one ``ba/requests`` message so the behavioural-analysis
       service can run a single-shot analysis on the accumulated frames.

With ``frame_capture_count=5`` and ``frame_capture_interval_seconds=1.0``
this means 5 frames captured per second and one BA request fired every
second.

BA itself is stateless: each request causes BA to fetch the latest K
frames from the bucket and run pose+VLM once.

Stops cleanly on:
  - explicit stop() call (driven by SceneScape EXITED event), OR
  - explicit stop_all() call (PERSON_LOST).
"""

import asyncio
from typing import Any, Dict, Protocol

import structlog

logger = structlog.get_logger(__name__)


def _compact_ts(entry_iso: str) -> str:
    """Compact ISO timestamp for SeaweedFS bucket-prefix consistency."""
    if not entry_iso:
        return ""
    return (
        entry_iso.replace(":", "")
        .replace("-", "")
        .split("+")[0]
        .split(".")[0]
    )


class _MQTT(Protocol):
    def publish_raw(self, topic: str, payload: str) -> None: ...


class _SessionManager(Protocol):
    def get_session(self, object_id: str, scene_id: str = "") -> Any: ...


class _BAPublisher(Protocol):
    def publish_request(
        self, *, person_id: str, region_id: str,
        entry_timestamp: str, scene_id: str,
        last_frame_ts: str = "",
    ) -> None: ...


class BehavioralAnalysisOrchestrator:
    """Owns BA visit tasks and per-visit frame-capture + request cadence."""

    def __init__(
        self,
        mqtt_service: _MQTT,
        session_manager: _SessionManager,
        ba_publisher: _BAPublisher,
        config,
        frame_capture_count: int = 5,
        frame_capture_interval_seconds: float = 1.0,
        frame_tracker=None,
        visit_tracker=None,
    ) -> None:
        self._mqtt = mqtt_service
        self._sessions = session_manager
        self._ba = ba_publisher
        self._config = config
        self._frame_tracker = frame_tracker
        self._visit_tracker = visit_tracker
        self._frame_capture_count = max(int(frame_capture_count), 1)
        self._frame_capture_interval_seconds = max(
            float(frame_capture_interval_seconds), 0.05
        )
        # Time between successive getimage commands within one cycle.
        self._frame_interval = (
            self._frame_capture_interval_seconds / self._frame_capture_count
        )
        self._cmd_topic_pattern = config.get_cmd_topic_pattern()

        # Active per-visit tasks, keyed by "{scene_id}:{object_id}:{region_id}"
        self._tasks: Dict[str, asyncio.Task] = {}
        # Track whether we're waiting for a BA result before sending another request.
        self._pending_result: Dict[str, bool] = {}

        logger.info(
            "BehavioralAnalysisOrchestrator initialized",
            frame_capture_count=self._frame_capture_count,
            frame_capture_interval_seconds=self._frame_capture_interval_seconds,
            frame_interval=self._frame_interval,
        )

    # ---- public API ----------------------------------------------------------

    def start(self, object_id: str, region_id: str, scene_id: str) -> None:
        """Begin a frame-capture task for one HV-zone visit.

        Idempotent: re-entry events from re-id flicker are ignored if the
        existing task is still alive.
        """
        key = self._key(scene_id, object_id, region_id)
        prev = self._tasks.get(key)
        if prev and not prev.done():
            logger.debug(
                "BA visit task already active, ignoring re-start",
                scene_id=scene_id, object_id=object_id, region_id=region_id,
            )
            return
        self._tasks[key] = asyncio.create_task(
            self._run(object_id, region_id, scene_id)
        )

    def stop(self, object_id: str, region_id: str, scene_id: str = "") -> None:
        """Cancel the visit task for one (scene, person, region) tuple.

        ``scene_id`` is optional for back-compat: when omitted we cancel
        every task matching ``(object_id, region_id)`` across scenes
        (which in practice is at most one).
        """
        if scene_id:
            key = self._key(scene_id, object_id, region_id)
            task = self._tasks.pop(key, None)
            if task and not task.done():
                task.cancel()
            return
        suffix = f":{object_id}:{region_id}"
        for key in [k for k in self._tasks if k.endswith(suffix)]:
            task = self._tasks.pop(key, None)
            if task and not task.done():
                task.cancel()

    def stop_all(self, object_id: str) -> None:
        """Cancel every visit task for a person (used on PERSON_LOST)."""
        marker = f":{object_id}:"
        for key in [k for k in self._tasks if marker in k]:
            task = self._tasks.pop(key, None)
            if task and not task.done():
                task.cancel()

    def active_count(self) -> int:
        return sum(1 for t in self._tasks.values() if not t.done())

    def ack_result(self, object_id: str, region_id: str, scene_id: str = "") -> None:
        """Clear the pending-result flag so the next cycle can publish a new request."""
        if scene_id:
            key = self._key(scene_id, object_id, region_id)
            self._pending_result.pop(key, None)
            return
        # If scene_id is empty, clear any matching suffix.
        suffix = f":{object_id}:{region_id}"
        for k in [k for k in self._pending_result if k.endswith(suffix)]:
            self._pending_result.pop(k, None)

    # ---- internals -----------------------------------------------------------

    @staticmethod
    def _key(scene_id: str, object_id: str, region_id: str) -> str:
        return f"{scene_id}:{object_id}:{region_id}"

    async def _run(self, object_id: str, region_id: str, scene_id: str) -> None:
        logger.info(
            "BA visit task started",
            object_id=object_id,
            region_id=region_id,
            frame_capture_count=self._frame_capture_count,
            frame_capture_interval_seconds=self._frame_capture_interval_seconds,
        )

        try:
            while True:
                session = self._sessions.get_session(object_id, scene_id=scene_id)
                if not session:
                    return

                # 1) Open the per-cycle quota so FrameCaptureService
                #    accepts exactly `frame_capture_count` frames for
                #    this (scene, person, region), then emit N getimage
                #    commands across the interval. Camera replies land in
                #    FrameCaptureService and are stored in the
                #    behavioral-frames bucket.
                if self._frame_tracker is not None:
                    self._frame_tracker.set_remaining(
                        scene_id, object_id, region_id,
                        self._frame_capture_count,
                    )
                for _ in range(self._frame_capture_count):
                    cams = list(session.current_cameras)
                    for cam in cams:
                        try:
                            self._mqtt.publish_raw(
                                self._cmd_topic_pattern.replace("{camera_name}", cam),
                                "getimage"
                            )                           
                        except Exception:
                            logger.exception(
                                "getimage publish failed",
                                object_id=object_id, camera=cam,
                            )
                    await asyncio.sleep(self._frame_interval)

                # 2) After the batch of frames, publish exactly one BA
                #    request so BA processes the latest window once.
                #    Skip if we're still waiting for the previous result
                #    to avoid flooding BA with requests it can't keep up with.
                key = self._key(scene_id, object_id, region_id)
                if self._pending_result.get(key):
                    logger.debug(
                        "BA result still pending, skipping request",
                        object_id=object_id, region_id=region_id,
                    )
                    continue

                entry_ts_iso = session.current_zones.get(region_id, "")
                last_frame_ts = ""
                if self._frame_tracker is not None:
                    last_frame_ts = (
                        self._frame_tracker.get_latest(scene_id, object_id, region_id) or ""
                    )
                    self._frame_tracker.clear(scene_id, object_id, region_id)
                try:
                    if self._visit_tracker is not None:
                        self._visit_tracker.note_request(
                            self._visit_tracker.make_key(
                                scene_id, object_id, region_id,
                                _compact_ts(entry_ts_iso),
                            )
                        )
                    self._ba.publish_request(
                        person_id=object_id,
                        region_id=region_id,
                        entry_timestamp=_compact_ts(entry_ts_iso),
                        scene_id=scene_id,
                        last_frame_ts=last_frame_ts,
                    )
                    self._pending_result[key] = True
                except Exception:
                    logger.exception(
                        "ba/requests publish failed",
                        object_id=object_id, region_id=region_id,
                    )

        except asyncio.CancelledError:
            logger.debug(
                "BA visit task cancelled",
                object_id=object_id, region_id=region_id,
            )
            raise
        except Exception:
            logger.exception(
                "BA visit task crashed",
                object_id=object_id, region_id=region_id,
            )
        finally:
            # Clean up stale frame-tracker entries so they don't leak memory
            # after the visit is over.
            if self._frame_tracker is not None:
                self._frame_tracker.clear(scene_id, object_id, region_id)
            key = self._key(scene_id, object_id, region_id)
            self._tasks.pop(key, None)
            self._pending_result.pop(key, None)
