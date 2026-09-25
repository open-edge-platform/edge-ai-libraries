# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import List, Optional

from src.core.internal_types import (
    InternalCameraProfileInfo,
    InternalV4L2BestCapture,
    InternalV4L2Format,
)

logger = logging.getLogger("scoring")

_MIN_ACCEPTABLE_FPS = 15.0
_TARGET_FPS = 30.0
_TARGET_PIXELS = 1920 * 1080

# Format preference scores (higher = better)
_FORMAT_PREFERENCE = {
    "H264": 1.0,
    "H.264": 1.0,
    "H265": 0.95,
    "H.265": 0.95,
    "HEVC": 0.95,
    "MJPG": 0.7,
    "MJPEG": 0.7,
    "JPEG": 0.7,
    "YUYV": 0.3,
    "YUY2": 0.3,
    "NV12": 0.3,
    "UYVY": 0.3,
    "I420": 0.3,
    "YV12": 0.3,
    "RGB3": 0.3,
    "BGR3": 0.3,
    "GREY": 0.3,
    "GRAY": 0.3,
}
_DEFAULT_FORMAT_PREFERENCE = 0.1

_ENCODING_TO_FOURCC = {
    "H264": "H264",
    "H.264": "H264",
    "H265": "H265",
    "H.265": "H265",
    "HEVC": "H265",
    "JPEG": "MJPG",
    "MJPEG": "MJPG",
}


def score_capture_candidate(fourcc: str, width: int, height: int, fps: float) -> float:
    """Score a capture candidate: 0.3 * fps + 0.3 * resolution + 0.4 * format preference."""
    fps_score = min(fps, _TARGET_FPS) / _TARGET_FPS if _TARGET_FPS > 0 else 0.0
    pixels = width * height
    resolution_score = min(pixels / _TARGET_PIXELS, 1.0) if _TARGET_PIXELS > 0 else 0.0
    format_pref = _FORMAT_PREFERENCE.get(fourcc.upper(), _DEFAULT_FORMAT_PREFERENCE)
    return fps_score * 0.3 + resolution_score * 0.3 + format_pref * 0.4


def select_best_from_v4l2_formats(
    formats: List[InternalV4L2Format],
) -> Optional[InternalV4L2BestCapture]:
    """Pick the highest scoring (fourcc, size, fps) combination, preferring fps >= 15."""
    best_acceptable = None
    best_acceptable_score = -1.0
    best_overall = None
    best_overall_score = -1.0

    for fmt in formats:
        for size in fmt.sizes:
            for fps in size.fps_list:
                score = score_capture_candidate(fmt.fourcc, size.width, size.height, fps)

                if score > best_overall_score:
                    best_overall_score = score
                    best_overall = (fmt.fourcc, size.width, size.height, fps)

                if fps >= _MIN_ACCEPTABLE_FPS and score > best_acceptable_score:
                    best_acceptable_score = score
                    best_acceptable = (fmt.fourcc, size.width, size.height, fps)

    chosen = best_acceptable if best_acceptable is not None else best_overall
    if chosen is None:
        return None

    fourcc, width, height, fps = chosen
    logger.debug(
        f"Selected best capture: {fourcc} {width}x{height} @{fps}fps "
        f"(score={score_capture_candidate(fourcc, width, height, fps):.3f})"
    )
    return InternalV4L2BestCapture(fourcc=fourcc, width=width, height=height, fps=fps)


def select_best_profile(
    profiles: List[InternalCameraProfileInfo],
) -> Optional[InternalCameraProfileInfo]:
    """Pick the best ONVIF profile with the same scoring; profiles without rtsp_url are skipped."""
    best_acceptable = None
    best_acceptable_score = -1.0
    best_overall = None
    best_overall_score = -1.0

    for profile in profiles:
        if not profile.rtsp_url:
            continue

        width, height = 0, 0
        if profile.resolution:
            parts = profile.resolution.lower().split("x")
            if len(parts) == 2:
                try:
                    width = int(parts[0])
                    height = int(parts[1])
                except ValueError:
                    pass

        enc = profile.encoding or ""
        scoring_fourcc = _ENCODING_TO_FOURCC.get(enc, enc.upper())

        fps = float(profile.framerate) if profile.framerate else 0.0

        score = score_capture_candidate(scoring_fourcc, width, height, fps)

        if score > best_overall_score:
            best_overall_score = score
            best_overall = profile

        if fps >= _MIN_ACCEPTABLE_FPS and score > best_acceptable_score:
            best_acceptable_score = score
            best_acceptable = profile

    chosen = best_acceptable if best_acceptable is not None else best_overall
    if chosen is not None:
        logger.debug(
            f"Selected best ONVIF profile: {chosen.name} ({chosen.encoding} {chosen.resolution})"
        )
    return chosen
