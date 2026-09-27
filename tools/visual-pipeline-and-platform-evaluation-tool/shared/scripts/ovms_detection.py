# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Create GVA ROI metadata from YOLO detections served by OVMS."""

from __future__ import annotations

import logging
import os
from itertools import count

from gstgva import VideoFrame

from ovms_client import OvmsInferenceError, detect


logger = logging.getLogger("ovms_detection")
DETECTION_INTERVAL = int(os.environ.get("OVMS_DETECTION_INTERVAL", "3"))
_frame_numbers = count()

if DETECTION_INTERVAL < 1:
    raise ValueError("OVMS_DETECTION_INTERVAL must be at least one")


def process_frame(frame: VideoFrame) -> bool:
    """Run OVMS object detection periodically and attach results to the frame."""
    if next(_frame_numbers) % DETECTION_INTERVAL:
        return True

    with frame.data() as image_bgr:
        if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
            raise ValueError(
                "ovms_detection requires video/x-raw,format=BGR before gvapython"
            )

        try:
            detections = detect(image_bgr)
        except OvmsInferenceError:
            logger.exception("OVMS detection request failed")
            raise

    for detection in detections:
        frame.add_region(
            detection.x,
            detection.y,
            detection.width,
            detection.height,
            detection.label,
            detection.confidence,
        )

    return True
