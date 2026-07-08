# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Store-wide Loss Prevention — main application entry point.

Wires together the four core responsibilities:
  1. MQTT Subscription and Event Routing
  2. Session State Management
  3. Business Logic (Detection Rules)
  4. Frame Manager (SeaweedFS)

External services (called conditionally):
  - BehavioralAnalysis Service (pose analysis + VLM confirmation)
  - Rule Service (advanced rule evaluation)
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import structlog
import uvicorn
from fastapi import FastAPI
from api.routes import router
from services.config import ConfigService
from services.mqtt_service import MQTTService
from services.session_manager import SessionManager
from rule_engine import RuleEngine
from services.rule_adapter import RuleEngineAdapter
from services.frame_manager import FrameManager
from services.scenescape_client import SceneScapeClient
from services.alert_service_client import AlertServiceClient
from services.ba_queue import BAQueuePublisher, BAQueueConsumer
from services.ba_orchestrator import BehavioralAnalysisOrchestrator
from services.frame_capture import FrameCaptureService, CapturedFrameTracker
from services.ba_visit_tracker import BAVisitTracker

# ---- Structured logging setup -----------------------------------------------
logging.basicConfig(format="%(message)s", stream=__import__("sys").stdout, level=logging.DEBUG)
logging.getLogger().setLevel(logging.DEBUG)

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


# ---- FastAPI lifespan --------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start all services, yield, then tear down."""
    logger.info("Starting Store-wide Loss Prevention")

    # 1. Config
    config = ConfigService()
    app.state.config = config

    # 1b. Discover zones from SceneScape API (match by region name)
    ss_client = SceneScapeClient(config)
    app.state.scenescape_client = ss_client
    ss_user = os.environ.get("SCENESCAPE_API_USER", "")
    ss_pass = os.environ.get("SCENESCAPE_API_PASSWORD", "")
    if ss_user and ss_pass:
        # Authenticate with retry — web container may still be starting
        authenticated = False
        for attempt in range(5):
            authenticated = await ss_client.authenticate(ss_user, ss_pass)
            if authenticated:
                break
            wait = 2 ** attempt  # 1, 2, 4, 8, 16 seconds
            logger.warning("SceneScape auth failed, retrying", attempt=attempt + 1, retry_in=wait)
            await asyncio.sleep(wait)

        if not authenticated:
            logger.error("SceneScape API authentication failed after retries")
        else:
            # Resolve scene_name → scene_id for each configured scene
            for scene_name in config.get_scene_names():
                scene_id = await ss_client.resolve_scene_id(scene_name)
                if scene_id:
                    config.set_scene_id_for_name(scene_name, scene_id)
                    logger.info("Scene resolved from name", scene_name=scene_name, scene_id=scene_id)
                else:
                    logger.error("Could not resolve scene_name to scene_id", scene_name=scene_name)

            # Discover and map zones (already authenticated, skip re-auth)
            regions = await ss_client.fetch_regions()
            if regions:
                discovered = ss_client.map_zones(regions)
                # Tag each zone with its scene_id
                for rid, zinfo in discovered.items():
                    scene_name_of_zone = zinfo.get("scene", "")
                    for sname, sid in config.get_scene_ids().items():
                        if sname == scene_name_of_zone or not scene_name_of_zone:
                            zinfo["scene_id"] = sid
                            break
                if discovered:
                    config.merge_zones(discovered)
                    logger.info("Zone discovery complete", zones=len(config.get_zones()))
                else:
                    logger.warning("Zone discovery found no matching regions")
            else:
                logger.warning("No regions found in SceneScape")
    else:
        logger.warning(
            "SCENESCAPE_API_USER / SCENESCAPE_API_PASSWORD not set, "
            "zone discovery skipped. Use POST /api/v1/lp/zones/discover "
            "or PUT /api/v1/lp/zones/{region_id} to add zones at runtime."
        )

    # 2. Frame Manager (SeaweedFS)
    frame_mgr = FrameManager(config)
    await frame_mgr.ensure_bucket()
    app.state.frame_manager = frame_mgr

    # 3. MQTT
    mqtt_svc = MQTTService(config)
    await mqtt_svc.initialize()
    loop = asyncio.get_running_loop()
    mqtt_svc.set_event_loop(loop)
    app.state.mqtt_service = mqtt_svc

    # 4. External service clients
    alert_svc_client = AlertServiceClient(config)
    app.state.alert_service_client = alert_svc_client

    # 4b. BA MQTT queue (publisher + result consumer)
    ba_publisher = BAQueuePublisher(mqtt_svc)
    app.state.ba_publisher = ba_publisher

    ba_result_consumer = BAQueueConsumer(mqtt_svc)
    app.state.ba_result_consumer = ba_result_consumer

    # 5. Session manager (receives MQTT connection state to pause expiry on disconnect)
    session_mgr = SessionManager(config, mqtt_connected_fn=lambda: mqtt_svc.connected)
    app.state.session_manager = session_mgr

    # 6. Rule engine (local, in-process)
    rules_yaml = config.get_rules_yaml_path()
    rule_engine = RuleEngine(rules_path=rules_yaml)

    # 6b. BA orchestrator (owns per-visit getimage + ba/requests cadence)
    rules_cfg = config.get_rules_config()
    frame_tracker = CapturedFrameTracker()
    app.state.frame_tracker = frame_tracker
    visit_tracker = BAVisitTracker()
    app.state.visit_tracker = visit_tracker
    ba_orchestrator = BehavioralAnalysisOrchestrator(
        mqtt_service=mqtt_svc,
        session_manager=session_mgr,
        ba_publisher=ba_publisher,
        config=config,
        frame_capture_count=int(rules_cfg.get("frame_capture_count", 5)),
        frame_capture_interval_seconds=float(
            rules_cfg.get("frame_capture_interval_seconds", 1.0)
        ),
        frame_tracker=frame_tracker,
        visit_tracker=visit_tracker,
    )
    app.state.ba_orchestrator = ba_orchestrator

    rule_adapter = RuleEngineAdapter(
        rule_engine, config, session_mgr,
        alert_service_client=alert_svc_client,
        frame_manager=frame_mgr,
        visit_tracker=visit_tracker,
    )
    # Register escalation services via the service registry
    rule_adapter.register_service("behavioral_analysis", ba_orchestrator)
    app.state.rule_engine = rule_engine
    app.state.rule_adapter = rule_adapter

    # Wire BA result consumer -> rule adapter (must be after rule_adapter creation)
    ba_result_consumer.register_result_handler(rule_adapter.on_ba_result)
    ba_result_consumer.subscribe()

    # ---- Wire callbacks ----
    # Session manager fires events → rule adapter (business logic)
    session_mgr.register_event_handler(rule_adapter.on_event)

    # MQTT scene data → session manager (liveness: cameras, bbox, last_seen)
    mqtt_svc.register_scene_data_handler(session_mgr.on_scene_data)

    # MQTT region events → session manager (enter/exit with dwell from SceneScape)
    mqtt_svc.register_region_event_handler(session_mgr.on_region_event)

    # MQTT region data → session manager (continuous dwell checking via SceneScape feed)
    mqtt_svc.register_region_data_handler(session_mgr.on_region_data)

    # MQTT camera images → FrameCaptureService (store only). The
    # orchestrator owns the ba/requests cadence.
    frame_capture = FrameCaptureService(
        config=config,
        session_manager=session_mgr,
        frame_manager=frame_mgr,
        frame_tracker=frame_tracker,
    )
    mqtt_svc.register_camera_image_handler(frame_capture.on_camera_image)


    # Frame production is owned by BehavioralAnalysisOrchestrator (per-visit).
    # It publishes "getimage" to active cameras and a BA request only while a
    # person is in a HIGH_VALUE zone. Camera replies land in
    # FrameCaptureService.on_camera_image.

    # Start background tasks
    mqtt_task = asyncio.create_task(mqtt_svc.start())
    expiry_task = asyncio.create_task(session_mgr.run_expiry_loop())

    # Periodic purge of stale visit-tracker entries (alerted visits that
    # would otherwise leak memory indefinitely).
    async def _visit_tracker_purge_loop():
        while True:
            await asyncio.sleep(30)
            visit_tracker.purge_stale()

    purge_task = asyncio.create_task(_visit_tracker_purge_loop())

    # Independent image capture loop: send getimage for ALL configured cameras
    # so the UI always has a live video feed, regardless of session state.
    # Disabled when ENABLE_UI=false to avoid unnecessary MQTT traffic.
    enable_ui = os.environ.get("ENABLE_UI", "true").lower() == "true"
    ui_image_task = None

    if enable_ui:
        cmd_topic = config.get_cmd_topic_pattern()
        _all_camera_names = [c["name"] for c in config.get_cameras()]

        async def _ui_image_loop():
            while True:
                await asyncio.sleep(0.5)  # ~2 FPS for UI feed
                if not mqtt_svc.connected:
                    continue
                for cam in _all_camera_names:
                    try:
                        mqtt_svc.publish_raw(
                            cmd_topic.replace("{camera_name}", cam),
                            "getimage",
                        )
                    except Exception:
                        pass

        ui_image_task = asyncio.create_task(_ui_image_loop())
    else:
        logger.info("UI image loop disabled (ENABLE_UI=false)")

    logger.info(
        "Store-wide Loss Prevention started",
        store_id=config.get_store_id(),
        zones=len(config.get_zones()),
        cameras=len(config.get_cameras()),
    )

    yield

    # ---- Shutdown ----
    logger.info("Shutting down Store-wide Loss Prevention")
    await mqtt_svc.stop()
    expiry_task.cancel()
    purge_task.cancel()
    if ui_image_task is not None:
        ui_image_task.cancel()
    mqtt_task.cancel()


# ---- App ---------------------------------------------------------------------

app = FastAPI(
    title="Store-wide Loss Prevention",
    description="Store-wide Loss Prevention: Suspicious Activity Detection",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api/v1/lp")


@app.get("/health")
async def health():
    return {"status": "healthy"}


# ---- Entry point -------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8082,
        log_level="info",
    )
