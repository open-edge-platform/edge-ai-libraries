# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
BehavioralAnalysis Service

Analyzes pose sequences to detect suspicious activity patterns.
Uses YOLO-Pose for keypoint extraction and pattern matching for detection.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

from pose_analyzer import PoseAnalyzer, PatternResult
from seaweedfs_client import SeaweedFSClient
from vlm_client import VLMClient
from ba_queue import BAQueueConsumer
from config import Settings, load_pattern_config, apply_vlm_settings
from yolo_pipeline import extract_poses

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources."""
    # Startup
    logger.info("Starting BehavioralAnalysis Service")

    # Load pattern config
    pattern_config = load_pattern_config(settings.pattern_config_path)

    # Apply VLM settings from config YAML (overrides env/defaults)
    apply_vlm_settings(settings, settings.pattern_config_path)

    # Initialize VLM client (if enabled)
    vlm_client = None
    if settings.vlm_enabled:
        vlm_client = VLMClient(
            endpoint=settings.vlm_endpoint,
            model_name=settings.vlm_model_name,
            timeout=settings.vlm_timeout,
            max_tokens=settings.vlm_max_tokens,
            temperature=settings.vlm_temperature,
            max_image_size=settings.vlm_max_image_size,
        )
        logger.info(f"VLM enabled: {settings.vlm_endpoint} ({settings.vlm_model_name})")
    else:
        logger.info("VLM disabled — pose-only detection")

    app.state.pose_analyzer = PoseAnalyzer(
        min_frames=settings.min_frames_for_detection,
        confidence_threshold=settings.pose_confidence_threshold,
        vlm_client=vlm_client,
        pattern_config=pattern_config,
    )
    app.state.frame_store = SeaweedFSClient(
        endpoint=settings.seaweedfs_endpoint,
        bucket=settings.seaweedfs_bucket,
        access_key=settings.seaweedfs_access_key,
        secret_key=settings.seaweedfs_secret_key,
    )
    await app.state.frame_store.ensure_bucket()
    logger.info("Service initialized successfully")

    # Start MQTT queue consumer (ba/requests → ba/results)
    loop = asyncio.get_running_loop()
    queue_consumer = BAQueueConsumer(
        settings,
        frame_store=app.state.frame_store,
        pose_analyzer=app.state.pose_analyzer,
    )
    queue_consumer.initialize(loop)
    app.state.queue_consumer = queue_consumer
    queue_task = asyncio.create_task(queue_consumer.start())
    logger.info("BA queue consumer started")

    yield

    # Shutdown
    await queue_consumer.stop()
    queue_task.cancel()
    if vlm_client:
        await vlm_client.close()
    logger.info("Shutting down BehavioralAnalysis Service")


app = FastAPI(
    title="BehavioralAnalysis Service",
    description="Pose-based suspicious activity detection",
    version="1.0.0",
    lifespan=lifespan,
)


# ─────────────────────────────────────────────────────────────────────────────
# Request/Response Models
# ─────────────────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    """Request to analyze frames for an entity."""
    entity_id: str
    region_id: Optional[str] = None
    entry_timestamp: Optional[str] = None
    scene_id: Optional[str] = None
    pattern_id: str = "shelf_to_waist"  # Pattern to detect


class AnalyzeResponse(BaseModel):
    """Response from pose analysis."""
    entity_id: str
    scene_id: Optional[str] = None
    status: str  # "no_data" | "accumulating" | "no_match" | "suspicious"
    frames_available: int
    frames_required: int
    confidence: Optional[float] = None
    pattern_id: Optional[str] = None
    message: Optional[str] = None
    vlm_confirmed: Optional[bool] = None
    vlm_reasoning: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    model_loaded: bool
    seaweedfs_connected: bool


# ─────────────────────────────────────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check service health."""
    frame_store: SeaweedFSClient = app.state.frame_store
    pose_analyzer: PoseAnalyzer = app.state.pose_analyzer

    return HealthResponse(
        status="healthy",
        model_loaded=pose_analyzer.is_loaded(),
        seaweedfs_connected=await frame_store.check_connection(),
    )


@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze_activity(request: AnalyzeRequest):
    """
    Analyze frames for suspicious activity.

    Flow:
    1. Fetch frames for entity_id from SeaweedFS
    2. If not enough frames, return "no_data" or "accumulating"
    3. Extract pose keypoints from each frame
    4. Run pattern detection on pose sequence
    5. Return result
    """
    frame_store: SeaweedFSClient = app.state.frame_store
    pose_analyzer: PoseAnalyzer = app.state.pose_analyzer

    entity_id = request.entity_id
    region_id = request.region_id
    entry_timestamp = request.entry_timestamp
    scene_id = request.scene_id
    pattern_id = request.pattern_id
    min_frames = settings.min_frames_for_detection

    try:
        # Step 1: Fetch frames from SeaweedFS
        frames = await frame_store.get_frames(
            entity_id=entity_id,
            max_frames=settings.max_frames_to_fetch,
            max_age_seconds=0,
            region_id=region_id,
            entry_timestamp=entry_timestamp,
            scene_id=scene_id,
        )

        frames_available = len(frames)
        logger.info(f"Entity {entity_id}: {frames_available} frames available")

        # Step 2: Check if we have enough frames
        if frames_available == 0:
            return AnalyzeResponse(
                entity_id=entity_id,
                scene_id=scene_id,
                status="no_data",
                frames_available=0,
                frames_required=min_frames,
                message="No frames available for this entity",
            )

        if frames_available < min_frames:
            return AnalyzeResponse(
                entity_id=entity_id,
                scene_id=scene_id,
                status="accumulating",
                frames_available=frames_available,
                frames_required=min_frames,
                message=f"Need {min_frames - frames_available} more frames",
            )

        # Step 3: Extract poses from last N frames via YOLO-Pose pipeline
        pose_frames = frames[-settings.pose_frames_count:]
        poses = await extract_poses(pose_frames, entity_id, settings)

        if not poses:
            logger.info(f"Entity {entity_id}: YOLO pipeline could not extract poses")
            return AnalyzeResponse(
                entity_id=entity_id,
                scene_id=scene_id,
                status="accumulating",
                frames_available=frames_available,
                frames_required=min_frames,
                message="Could not extract poses from enough frames",
            )

        # Step 4: Run pattern detection
        results = pose_analyzer.detect_all_patterns(poses)
        matched = [r for r in results if r.matched]
        result = (
            max(matched, key=lambda r: r.confidence)
            if matched
            else results[0] if results
            else PatternResult(
                matched=False, confidence=0.0,
                pattern_id=pattern_id,
                description="No patterns evaluated",
            )
        )

        # Step 5: If pose pattern matched, send to VLM for confirmation
        if result.matched and settings.vlm_enabled:
            result = await pose_analyzer.analyze_with_vlm(
                frames=pose_frames,
                pose_result=result,
            )

        # Step 6: Return result
        if result.matched:
            vlm_reasoning = None
            if result.vlm_result:
                vlm_reasoning = result.vlm_result.get("reasoning")

            logger.warning(
                f"Entity {entity_id}: SUSPICIOUS — pattern={pattern_id} "
                f"confidence={result.confidence:.3f} "
                f"vlm_confirmed={result.vlm_confirmed} "
                f"{result.description}"
            )
            return AnalyzeResponse(
                entity_id=entity_id,
                scene_id=scene_id,
                status="suspicious",
                frames_available=frames_available,
                frames_required=min_frames,
                confidence=result.confidence,
                pattern_id=pattern_id,
                message=result.description,
                vlm_confirmed=result.vlm_confirmed,
                vlm_reasoning=vlm_reasoning,
            )
        else:
            logger.info(
                f"Entity {entity_id}: no_match — pattern={pattern_id} "
                f"confidence={result.confidence:.3f}"
            )
            return AnalyzeResponse(
                entity_id=entity_id,
                scene_id=scene_id,
                status="no_match",
                frames_available=frames_available,
                frames_required=min_frames,
                confidence=result.confidence,
                pattern_id=pattern_id,
                message="No suspicious pattern detected",
            )

    except Exception as e:
        logger.error(f"Error analyzing entity {entity_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/entities/{entity_id}/frames")
async def clear_entity_frames(entity_id: str, region_id: Optional[str] = None, scene_id: Optional[str] = None):
    """Clear all frames for an entity (optionally scoped to a region/scene)."""
    frame_store: SeaweedFSClient = app.state.frame_store

    try:
        deleted_count = await frame_store.delete_frames(entity_id, region_id=region_id, scene_id=scene_id)
        return {"entity_id": entity_id, "region_id": region_id, "scene_id": scene_id, "deleted_frames": deleted_count}
    except Exception as e:
        logger.error(f"Error clearing frames for {entity_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=settings.debug,
    )
