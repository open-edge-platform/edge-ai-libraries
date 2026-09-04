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
from io import BytesIO

import uvicorn
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List
import cv2
import numpy as np

from pose_analyzer import PoseAnalyzer, PatternResult
from seaweedfs_client import SeaweedFSClient
from vlm_client import VLMClient
from ba_queue import BAQueueConsumer
from config import Settings, load_pattern_config, apply_vlm_settings
from yolo_pipeline import extract_poses

# Load settings first to configure logging
settings = Settings()

# Initialize logging with level from settings
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.DEBUG),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources based on deployment mode."""
    # Startup
    logger.info(f"Starting BehavioralAnalysis Service (mode: {settings.deployment_mode.value})")

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
        min_frames=settings.pose_frames_count,  # Global fallback for phases that don't specify min_frames
        confidence_threshold=settings.pose_confidence_threshold,
        vlm_client=vlm_client,
        pattern_config=pattern_config,
    )
    logger.info(f"Pattern detection initialized: respecting pattern-level min_frames (global fallback={settings.pose_frames_count})")

    # ─────────────────────────────────────────────────────────────────────────────
    # Mode-based initialization: SeaweedFS + MQTT vs Standalone
    # ─────────────────────────────────────────────────────────────────────────────

    # Initialize SeaweedFS only if configured
    frame_store = None
    if settings.use_seaweedfs:
        try:
            frame_store = SeaweedFSClient(
                endpoint=settings.seaweedfs_endpoint,
                bucket=settings.seaweedfs_bucket,
                access_key=settings.seaweedfs_access_key,
                secret_key=settings.seaweedfs_secret_key,
            )
            await frame_store.ensure_bucket()
            logger.info(f"SeaweedFS connected: {settings.seaweedfs_endpoint}/{settings.seaweedfs_bucket}")
        except Exception as e:
            logger.error(f"SeaweedFS initialization failed: {e}")
            raise  # In seaweedfs+mqtt mode, SeaweedFS is required
    else:
        logger.info("SeaweedFS disabled (standalone+api mode) — using direct frame submission only")
    
    app.state.frame_store = frame_store

    # Initialize MQTT queue consumer only if configured
    queue_consumer = None
    queue_task = None
    if settings.use_mqtt:
        if frame_store is None:
            raise RuntimeError("MQTT mode requires SeaweedFS to be enabled and available")
        try:
            loop = asyncio.get_running_loop()
            queue_consumer = BAQueueConsumer(
                settings,
                frame_store=frame_store,
                pose_analyzer=app.state.pose_analyzer,
            )
            queue_consumer.initialize(loop)
            queue_task = asyncio.create_task(queue_consumer.start())
            logger.info("BA queue consumer started (ba/requests → ba/results)")
            app.state.queue_consumer = queue_consumer
        except Exception as e:
            logger.error(f"MQTT queue consumer initialization failed: {e}")
            raise
    else:
        logger.info("MQTT queue consumer disabled (standalone+api mode)")
        app.state.queue_consumer = None

    logger.info("Service initialized successfully")

    yield

    # Shutdown
    if queue_task:
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


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    """Normalize FastAPI request validation errors to the API error contract."""
    return JSONResponse(
        status_code=400,
        content={
            "detail": {
                "error_code": "INVALID_REQUEST",
                "message": "Request validation failed",
                "errors": exc.errors(),
            }
        },
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
# V1 API Models (Direct Frame Submission)
# ─────────────────────────────────────────────────────────────────────────────

class AnalyzeDirectRequest(BaseModel):
    """Direct frame analysis request (metadata for multipart form)."""
    entity_id: str = Field(..., description="Unique entity identifier")
    pattern_id: str = Field(default="shelf_to_waist", description="Pattern to detect")
    vlm_enabled: Optional[bool] = Field(None, description="Override VLM settings")
    request_id: Optional[str] = Field(None, description="Request tracking ID")


class AnalyzeDirectResponse(BaseModel):
    """Simplified direct analysis response."""
    entity_id: str
    status: str  # "pose_not_detected" | "no_match" | "suspicious"
    pose_detected: bool
    frames_submitted: int
    confidence: Optional[float] = None
    message: str
    vlm_confirmed: Optional[bool] = None
    vlm_reasoning: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response."""
    error_code: str
    message: str
    http_status: int
    details: Optional[dict] = None


# ─────────────────────────────────────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check service health."""
    pose_analyzer: PoseAnalyzer = app.state.pose_analyzer
    frame_store: SeaweedFSClient = app.state.frame_store

    if not settings.use_seaweedfs:
        seaweedfs_ok = False
    else:
        seaweedfs_ok = False
        if frame_store:
            try:
                seaweedfs_ok = await frame_store.check_connection()
            except Exception:
                seaweedfs_ok = False

    return HealthResponse(
        status="healthy",
        model_loaded=pose_analyzer.is_loaded(),
        seaweedfs_connected=seaweedfs_ok,
    )


@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze_activity(request: AnalyzeRequest):
    """
    Analyze frames for suspicious activity (SeaweedFS mode only).

    Flow:
    1. Fetch frames for entity_id from SeaweedFS
    2. If not enough frames, return "no_data" or "accumulating"
    3. Extract pose keypoints from each frame
    4. Run pattern detection on pose sequence
    5. Return result

    Note: This endpoint requires SeaweedFS mode. Use /api/v1/analyze/batch for standalone mode.
    """
    # Guard: v1 requires SeaweedFS mode
    if not settings.use_seaweedfs:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "SEAWEEDFS_NOT_ENABLED",
                "message": "V1 endpoint requires SeaweedFS+MQTT mode. Use /api/v1/analyze/batch for standalone mode."
            }
        )

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
    """Clear all frames for an entity (SeaweedFS mode only)."""
    # Guard: v1 requires SeaweedFS mode
    if not settings.use_seaweedfs:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "SEAWEEDFS_NOT_ENABLED",
                "message": "V1 endpoint requires SeaweedFS+MQTT mode. Use /api/v1/analyze/batch for standalone mode."
            }
        )

    frame_store: SeaweedFSClient = app.state.frame_store

    try:
        deleted_count = await frame_store.delete_frames(entity_id, region_id=region_id, scene_id=scene_id)
        return {"entity_id": entity_id, "region_id": region_id, "scene_id": scene_id, "deleted_frames": deleted_count}
    except Exception as e:
        logger.error(f"Error clearing frames for {entity_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# V1 API Endpoints (Batch Frame Submission)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/analyze/batch", response_model=AnalyzeDirectResponse)
async def analyze_frames_batch(
    entity_id: str = Form(..., description="Unique entity identifier"),
    pattern_id: str = Form(default="shelf_to_waist", description="Pattern to detect"),
    vlm_enabled: Optional[bool] = Form(None, description="Override global VLM setting"),
    request_id: Optional[str] = Form(None, description="Request tracking ID"),
    frames: Optional[List[UploadFile]] = File(None, description="Frame files (JPEG/PNG/WebP)"),
):
    """
    Analyze frames for suspicious activity using direct multipart frame submission.

    Flow:
    1. Validate and decode uploaded frame files
    2. Extract pose keypoints from each frame
    3. Run pattern detection on pose sequence
    4. Run VLM confirmation if enabled
    5. Return simplified result

    Args:
        entity_id: Unique entity identifier (required)
        pattern_id: Pattern to detect (default: "shelf_to_waist")
        vlm_enabled: Override global VLM setting (optional)
        request_id: Request tracking ID for logging (optional)
        frames: List of frame files as multipart uploads

    Returns:
        Simplified analysis response with pose detection and pattern match results
    """
    pose_analyzer: PoseAnalyzer = app.state.pose_analyzer

    if not frames or len(frames) == 0:
        req_id = request_id or f"req_{entity_id}_0_frames"
        logger.warning(f"[{req_id}] No frames provided")
        raise HTTPException(
            status_code=400,
            detail={"error_code": "NO_FRAMES_PROVIDED", "message": "At least 1 frame required"}
        )

    # Use provided request_id or generate one
    req_id = request_id or f"req_{entity_id}_{len(frames)}_frames"
    logger.info(f"[{req_id}] Received {len(frames)} frames for entity {entity_id}")

    try:
        # Step 1: Validate frame count
        if len(frames) == 0:
            logger.warning(f"[{req_id}] No frames provided")
            raise HTTPException(
                status_code=400,
                detail={"error_code": "NO_FRAMES_PROVIDED", "message": "At least 1 frame required"}
            )

        # Step 2: Decode and validate frames
        decoded_frames = []
        invalid_frames = []

        for idx, file in enumerate(frames):
            try:
                # Read file content
                content = await file.read()

                # Validate file size (max 5MB per frame)
                if len(content) > 5 * 1024 * 1024:
                    invalid_frames.append((idx, f"Frame {idx} exceeds 5MB limit"))
                    continue

                # Decode using OpenCV
                nparr = np.frombuffer(content, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if frame is None:
                    invalid_frames.append((idx, f"Frame {idx} is not a valid image format"))
                    continue

                decoded_frames.append(frame)
                logger.debug(f"[{req_id}] Decoded frame {idx}: {frame.shape}")

            except Exception as e:
                invalid_frames.append((idx, str(e)))
                logger.warning(f"[{req_id}] Failed to decode frame {idx}: {e}")

        # Step 3: Check if we have minimum frames after validation
        frames_valid = len(decoded_frames)
        logger.info(f"[{req_id}] Valid frames: {frames_valid}/{len(frames)}")

        if frames_valid == 0:
            logger.error(f"[{req_id}] No valid frames could be decoded")
            raise HTTPException(
                status_code=422,
                detail={
                    "error_code": "INVALID_FRAMES",
                    "message": "No valid frames could be decoded",
                    "invalid_frames": invalid_frames
                }
            )

        # Step 4: Extract poses from frames
        # Convert frames to (frame, timestamp) tuples for YOLO pipeline
        # Use frame index * 33ms for timestamps (assuming 30fps)
        frame_tuples = [(frame, i * 33) for i, frame in enumerate(decoded_frames)]
        poses = await extract_poses(frame_tuples, entity_id, settings)
        pose_detected = len(poses) > 0

        logger.info(f"[{req_id}] Pose extraction: {len(poses)} poses detected from {frames_valid} frames")

        if not pose_detected:
            logger.info(f"[{req_id}] Entity {entity_id}: No poses detected")
            return AnalyzeDirectResponse(
                entity_id=entity_id,
                status="pose_not_detected",
                pose_detected=False,
                frames_submitted=frames_valid,
                message="Could not extract poses from submitted frames"
            )

        # Step 5: Run pattern detection
        logger.debug(f"[{req_id}] Pattern Detection Debug Info:")
        logger.debug(f"[{req_id}]   - Total poses extracted: {len(poses)}")
        for idx, pose in enumerate(poses):
            logger.debug(f"[{req_id}]     Pose {idx}: keypoints shape={pose.keypoints.shape}, confidences mean={pose.confidences.mean():.3f}, range=[{pose.confidences.min():.3f}, {pose.confidences.max():.3f}]")
        
        results = pose_analyzer.detect_all_patterns(poses)
        logger.debug(f"[{req_id}] Pattern detection results ({len(results)} patterns evaluated):")
        for res in results:
            logger.debug(f"[{req_id}]   - Pattern '{res.pattern_id}': matched={res.matched}, confidence={res.confidence:.3f}, desc={res.description}")
        
        matched = [r for r in results if r.matched]
        result = (
            max(matched, key=lambda r: r.confidence)
            if matched
            else results[0] if results
            else PatternResult(
                matched=False, confidence=0.0,
                pattern_id=pattern_id,
                description="No patterns evaluated"
            )
        )

        logger.info(f"[{req_id}] Pattern detection: matched={result.matched}, confidence={result.confidence:.3f}, pattern={result.pattern_id}")

        # Step 6: Determine VLM usage (override or use global setting)
        use_vlm = vlm_enabled if vlm_enabled is not None else settings.vlm_enabled
        vlm_confirmed = None
        vlm_reasoning = None

        if result.matched and use_vlm:
            logger.info(f"[{req_id}] Pose pattern matched, calling VLM for confirmation")
            try:
                result = await pose_analyzer.analyze_with_vlm(
                    frames=frame_tuples,
                    pose_result=result,
                )
                vlm_confirmed = result.vlm_confirmed
                if result.vlm_result:
                    vlm_reasoning = result.vlm_result.get("reasoning")
                logger.info(f"[{req_id}] VLM result: confirmed={vlm_confirmed}")
            except asyncio.TimeoutError:
                logger.warning(f"[{req_id}] VLM request timed out")
                vlm_confirmed = None
            except Exception as e:
                logger.warning(f"[{req_id}] VLM processing failed: {e}")
                vlm_confirmed = None

        # Step 7: Format and return result
        if result.matched:
            if vlm_confirmed is False:
                # Pose matched but VLM rejected
                logger.info(f"[{req_id}] Pose matched but VLM did not confirm")
                return AnalyzeDirectResponse(
                    entity_id=entity_id,
                    status="no_match",
                    pose_detected=True,
                    frames_submitted=frames_valid,
                    confidence=result.confidence,
                    message="Pose pattern matched but VLM did not confirm suspicious activity",
                    vlm_confirmed=False,
                    vlm_reasoning=vlm_reasoning
                )
            else:
                # Pose matched (and VLM confirmed if enabled)
                logger.warning(f"[{req_id}] SUSPICIOUS: {result.description}")
                return AnalyzeDirectResponse(
                    entity_id=entity_id,
                    status="suspicious",
                    pose_detected=True,
                    frames_submitted=frames_valid,
                    confidence=result.confidence,
                    message=result.description,
                    vlm_confirmed=vlm_confirmed,
                    vlm_reasoning=vlm_reasoning
                )
        else:
            # No pattern match
            logger.info(f"[{req_id}] No suspicious pattern detected")
            return AnalyzeDirectResponse(
                entity_id=entity_id,
                status="no_match",
                pose_detected=True,
                frames_submitted=frames_valid,
                confidence=result.confidence,
                message="No suspicious pattern detected"
            )

    except HTTPException as http_exc:
        logger.error(f"[{req_id}] HTTP Exception: {http_exc.detail}")
        raise
    except Exception as e:
        logger.error(f"[{req_id}] Unexpected error analyzing entity {entity_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "INTERNAL_ERROR",
                "message": f"Analysis failed: {str(e)[:100]}"
            }
        )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=settings.debug,
    )
