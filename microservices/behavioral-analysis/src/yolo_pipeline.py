# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
YOLO-Pose pipeline runner for pose extraction.

Pure-Python replacement for the GStreamer DL Streamer pipeline.
Uses YOLO26n-pose via OpenVINO for single-stage person detection + keypoint
estimation.  Returns extracted poses — pattern detection and VLM confirmation
are handled by the caller via a single PoseAnalyzer instance.
"""

import logging

import numpy as np

from config import Settings
from pose_analyzer import Pose
from yolo_pose_ov import YOLOPoseOV

logger = logging.getLogger(__name__)

# Lazy-initialized singleton — compiled once, reused across calls.
_yolo_model: YOLOPoseOV | None = None


def _get_model(settings: Settings) -> YOLOPoseOV:
    global _yolo_model
    if _yolo_model is None:
        _yolo_model = YOLOPoseOV(
            model_path=settings.yolo_pose_model,
            device=settings.gst_inference_device,
        )
    return _yolo_model


async def extract_poses(
    frames: list[tuple[np.ndarray, int]],
    entity_id: str,
    settings: Settings,
) -> list[Pose]:
    """
    Run YOLO-Pose inference and return extracted poses.

    Args:
        frames: List of (frame_image_bgr, timestamp_ms) tuples.
        entity_id: Person identifier (for logging).
        settings: Settings object with model paths and thresholds.

    Returns:
        List of Pose objects extracted from frames.
    """
    model = _get_model(settings)
    conf_threshold = settings.pose_confidence_threshold

    poses: list[Pose] = []
    frame_images = [f[0] for f in frames]
    frame_timestamps = [f[1] for f in frames]

    logger.info(
        "Entity %s: running YOLO-Pose pipeline (%d frames)",
        entity_id, len(frame_images),
    )

    for i, img in enumerate(frame_images):
        results = model(img, verbose=False)
        kp_result = results[0].keypoints if results else None

        if kp_result is None or kp_result.xy.shape[0] == 0:
            logger.debug("Entity %s: frame %d — no person detected", entity_id, i + 1)
            continue

        # Take the highest-confidence detection (largest person, typically)
        # YOLO output is sorted by score after NMS.
        kp_xy = kp_result.xy[0]    # (17, 2)
        kp_conf = kp_result.conf[0]  # (17,)
        mean_conf = float(kp_conf.mean())

        if mean_conf < conf_threshold:
            logger.debug(
                "Entity %s: frame %d — mean kp conf %.3f below %.3f",
                entity_id, i + 1, mean_conf, conf_threshold,
            )
            continue

        pose = Pose(
            keypoints=np.array(kp_xy),
            confidences=np.array(kp_conf),
            timestamp=frame_timestamps[i] if i < len(frame_timestamps) else None,
        )
        poses.append(pose)

    logger.info(
        "Entity %s: YOLO-Pose extracted %d/%d poses",
        entity_id, len(poses), len(frame_images),
    )

    return poses
