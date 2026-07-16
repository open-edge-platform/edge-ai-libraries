# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
MQTT-based queue consumer for Behavioral Analysis.

The BA service is fully event-driven and single-shot:

* swlp-service publishes one ``ba/requests`` message after each capture
  cycle (5 frames stored in the ``behavioral-frames`` bucket).
* For every request we fetch the frames for that visit ONCE, run pose +
  VLM, and publish exactly one ``ba/results`` message.
* There is no ``start``/``exit`` lifecycle, no polling worker, and no
  watermark state on the BA side. Visit lifecycle is owned entirely by
  the swlp-service ``BAVisitTracker``.
"""

import asyncio
import json
import logging
from typing import Optional

from vlm_metrics_logger import log_ovms_performance_metric

import paho.mqtt.client as mqtt

from config import Settings
from pose_analyzer import PatternResult
from yolo_pipeline import extract_poses

logger = logging.getLogger(__name__)


class BAQueueConsumer:
    """Consumes ``ba/requests`` messages and runs one analysis per message."""

    def __init__(
        self,
        settings: Settings,
        frame_store=None,
        pose_analyzer=None,
    ) -> None:
        self.settings = settings
        self.request_topic = settings.ba_request_topic
        self.result_topic = settings.ba_result_topic
        self.frame_store = frame_store
        self.pose_analyzer = pose_analyzer
        self.min_frames = settings.min_frames_for_detection

        # Bound concurrent VLM calls so ovms-vlm doesn’t pile up requests.
        self._vlm_sem = asyncio.Semaphore(
            max(1, int(getattr(settings, "vlm_max_concurrency", 1)))
        )

        self.client: Optional[mqtt.Client] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.connected = False
        self._shutdown = asyncio.Event()
        # In-flight analysis tasks; tracked only so shutdown can await them.
        self._inflight: set[asyncio.Task] = set()        # Entity dedup: skip requests for entities already being analyzed.
        self._inflight_entities: set[str] = set()
        # Max concurrent analysis tasks to bound memory usage.
        self._max_inflight = max(1, int(getattr(settings, "max_inflight_analyses", 3)))
    def initialize(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.client = mqtt.Client(client_id="ba-queue-consumer")
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    async def start(self) -> None:
        logger.info(
            "BA queue consumer connecting to MQTT",
            extra={"host": self.settings.mqtt_host, "port": self.settings.mqtt_port},
        )
        self.client.connect_async(
            self.settings.mqtt_host, self.settings.mqtt_port, keepalive=60
        )
        self.client.loop_start()
        await self._shutdown.wait()

    async def stop(self) -> None:
        self._shutdown.set()
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
        # Let any in-flight analyses finish so their results are published.
        if self._inflight:
            logger.info(
                f"Awaiting {len(self._inflight)} in-flight BA analyses"
            )
            await asyncio.gather(*self._inflight, return_exceptions=True)
        logger.info("BA queue consumer stopped")

    def publish_result(self, result: dict) -> None:
        if self.client and self.connected:
            self.client.publish(
                self.result_topic, json.dumps(result), qos=1
            )
            logger.info(
                "Published BA result",
                extra={
                    "person_id": result.get("person_id"),
                    "status": result.get("status"),
                },
            )

    # ---- paho callbacks ------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            self.connected = True
            client.subscribe(self.request_topic, qos=1)
            logger.info(
                f"BA queue consumer connected, subscribed to {self.request_topic}"
            )
        else:
            logger.error(f"BA queue consumer MQTT connect failed, rc={rc}")

    def _on_disconnect(self, client, userdata, rc) -> None:
        self.connected = False
        logger.warning(f"BA queue consumer MQTT disconnected, rc={rc}")

    def _on_message(self, client, userdata, msg: mqtt.MQTTMessage) -> None:
        if msg.topic != self.request_topic:
            return
        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            logger.error("Invalid JSON in BA request message")
            return

        person_id = payload.get("person_id", "")
        region_id = payload.get("region_id", "")
        entry_timestamp = payload.get("entry_timestamp", "")
        scene_id = payload.get("scene_id", "")
        last_frame_ts = payload.get("last_frame_ts", "")
        if not person_id:
            logger.warning("BA message missing person_id, skipping")
            return

        if not self.loop:
            return
        # Schedule the single-shot analysis on the asyncio loop.
        self.loop.call_soon_threadsafe(
            self._spawn_analysis,
            person_id, region_id, entry_timestamp, scene_id, last_frame_ts,
        )

    # ---- analysis dispatch ---------------------------------------------------

    def _spawn_analysis(
        self, person_id: str, region_id: str, entry_timestamp: str,
        scene_id: str, last_frame_ts: str,
    ) -> None:
        # Drop request if this entity is already being analyzed (dedup).
        if person_id in self._inflight_entities:
            logger.debug(
                f"Entity {person_id}: analysis already in-flight, skipping"
            )
            return
        # Drop request if we're at capacity to bound memory usage.
        if len(self._inflight) >= self._max_inflight:
            logger.debug(
                f"Max in-flight analyses ({self._max_inflight}) reached, dropping request for {person_id}"
            )
            return

        self._inflight_entities.add(person_id)

        async def _runner() -> None:
            try:
                await self._analyze_visit(
                    person_id, region_id, entry_timestamp,
                    scene_id, last_frame_ts,
                )
            finally:
                self._inflight_entities.discard(person_id)

        task = asyncio.create_task(_runner())
        self._inflight.add(task)
        task.add_done_callback(self._inflight.discard)

    async def _analyze_visit(
        self, person_id: str, region_id: str, entry_timestamp: str,
        scene_id: str, last_frame_ts: str,
    ) -> None:
        """Fetch frames for this visit ONCE, analyse, publish one result."""
        try:
            frames = await self.frame_store.get_frames(
                entity_id=person_id,
                max_frames=self.settings.max_frames_to_fetch,
                last_frame_ts=last_frame_ts,
                region_id=region_id,
                entry_timestamp=entry_timestamp,
                scene_id=scene_id,
            )
        except Exception:
            logger.exception(f"Frame fetch failed for {person_id}")
            self.publish_result({
                "person_id": person_id, "region_id": region_id,
                "entry_timestamp": entry_timestamp, "scene_id": scene_id,
                "last_frame_ts": last_frame_ts,
                "status": "no_enough_data", "confidence": 0.0,
                "vlm_response": None, "frames_analyzed": 0,
            })
            return

        frames_available = len(frames)
        if frames_available < self.min_frames:
            self.publish_result({
                "person_id": person_id, "region_id": region_id,
                "entry_timestamp": entry_timestamp, "scene_id": scene_id,
                "last_frame_ts": last_frame_ts,
                "status": "no_enough_data", "confidence": 0.0,
                "vlm_response": None, "frames_analyzed": frames_available,
            })
            return

        await self._analyze_batch(
            person_id, region_id, entry_timestamp, scene_id,
            frames, last_frame_ts=last_frame_ts,
        )

    # ---- single-batch analysis -----------------------------------------------

    async def _analyze_batch(
        self, person_id: str, region_id: str, entry_timestamp: str,
        scene_id: str, frames: list, last_frame_ts: str = "",
    ) -> None:
        """Run pose + VLM on a batch of frames and publish exactly one result."""
        frames_available = len(frames)
        try:
            pose_frames = frames[-self.settings.pose_frames_count:]
            poses = await extract_poses(pose_frames, person_id, self.settings)

            if not poses:
                self.publish_result({
                    "person_id": person_id, "region_id": region_id,
                    "entry_timestamp": entry_timestamp, "scene_id": scene_id,
                    "last_frame_ts": last_frame_ts,
                    "status": "no_match", "confidence": 0.0,
                    "vlm_response": None, "frames_analyzed": frames_available,
                })
                return

            results = self.pose_analyzer.detect_all_patterns(poses)
            matched = [r for r in results if r.matched]
            result = (
                max(matched, key=lambda r: r.confidence)
                if matched
                else results[0] if results
                else PatternResult(
                    matched=False, confidence=0.0,
                    pattern_id="shelf_to_waist",
                    description="No patterns evaluated",
                )
            )

            if result.matched:
                logger.warning(
                    f"Entity {person_id}: pose pattern matched "
                    f"(confidence={result.confidence:.3f}), calling VLM"
                )
                if self.settings.vlm_enabled and self.pose_analyzer.vlm_client:
                    # Timeout on semaphore wait so one hung VLM call
                    # doesn't block all other entities from progressing.
                    sem_timeout = self.settings.vlm_timeout
                    try:
                        acquired = await asyncio.wait_for(
                            self._vlm_sem.acquire(), timeout=sem_timeout,
                        )
                    except asyncio.TimeoutError:
                        acquired = False
                        logger.warning(
                            f"Entity {person_id}: VLM semaphore acquire "
                            f"timed out after {sem_timeout}s, skipping VLM"
                        )
                    if acquired:
                        try:
                            result = await self.pose_analyzer.analyze_with_vlm(
                                frames=pose_frames,
                                pose_result=result,
                            )
                        finally:
                            self._vlm_sem.release()
                    if result.vlm_metrics:
                        log_ovms_performance_metric(
                            "USECASE_1", result.vlm_metrics
                        )
                vlm_response = None
                if result.vlm_result:
                    vlm_response = result.vlm_result.get("reasoning")

                if result.vlm_confirmed is True:
                    self.publish_result({
                        "person_id": person_id, "region_id": region_id,
                        "entry_timestamp": entry_timestamp, "scene_id": scene_id,
                        "last_frame_ts": last_frame_ts,
                        "status": "suspicious",
                        "confidence": result.confidence,
                        "vlm_response": vlm_response,
                        "frames_analyzed": frames_available,
                    })
                    return
                logger.info(
                    f"Entity {person_id}: VLM did not confirm "
                    f"(vlm_confirmed={result.vlm_confirmed})"
                )
                self.publish_result({
                    "person_id": person_id, "region_id": region_id,
                    "entry_timestamp": entry_timestamp, "scene_id": scene_id,
                    "last_frame_ts": last_frame_ts,
                    "status": "no_match",
                    "confidence": result.confidence,
                    "vlm_response": vlm_response,
                    "frames_analyzed": frames_available,
                })
                return

            self.publish_result({
                "person_id": person_id, "region_id": region_id,
                "entry_timestamp": entry_timestamp, "scene_id": scene_id,
                "last_frame_ts": last_frame_ts,
                "status": "no_match",
                "confidence": result.confidence,
                "vlm_response": None,
                "frames_analyzed": frames_available,
            })
        except Exception:
            logger.exception(f"Error analysing batch for {person_id}")
