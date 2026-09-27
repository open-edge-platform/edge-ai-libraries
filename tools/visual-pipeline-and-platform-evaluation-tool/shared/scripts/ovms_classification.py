# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Classify detection ROIs through OVMS and attach GVA classification metadata."""

from __future__ import annotations

import logging
import os
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock

from gstgva import Tensor, VideoFrame
from gstgva.util import libgst

from ovms_client import (
    CLASSIFICATION_MODEL_NAME,
    CLASSIFICATION_OUTPUT_NAME,
    OvmsInferenceError,
    Classification,
    classify_batch,
)


logger = logging.getLogger("ovms_classification")
MAX_ROIS_PER_FRAME = 5
CACHE_TTL_FRAMES = int(os.environ.get("OVMS_CLASSIFICATION_CACHE_TTL_FRAMES", "30"))
CACHE_MAX_ENTRIES = int(os.environ.get("OVMS_CLASSIFICATION_CACHE_MAX_ENTRIES", "256"))

if CACHE_TTL_FRAMES < 0:
    raise ValueError("OVMS_CLASSIFICATION_CACHE_TTL_FRAMES cannot be negative")
if CACHE_MAX_ENTRIES < 1:
    raise ValueError("OVMS_CLASSIFICATION_CACHE_MAX_ENTRIES must be at least one")


@dataclass(frozen=True)
class _CachedClassification:
    result: Classification
    expires_at_frame: int


_classification_cache: OrderedDict[int, _CachedClassification] = OrderedDict()
_cache_lock = Lock()
_frame_number = 0


def _classification_tensor(label: str, confidence: float, class_id: int) -> Tensor:
    structure = libgst.gst_structure_new_empty(
        f"classification_layer_name:{CLASSIFICATION_OUTPUT_NAME}".encode("utf-8")
    )
    tensor = Tensor(structure)
    tensor.set_label(label)
    tensor["type"] = "classification_result"
    tensor["confidence"] = confidence
    tensor["label_id"] = class_id
    tensor["model_name"] = CLASSIFICATION_MODEL_NAME
    tensor["layer_name"] = CLASSIFICATION_OUTPUT_NAME
    return tensor


def _next_frame_number() -> int:
    global _frame_number
    with _cache_lock:
        _frame_number += 1
        return _frame_number


def _cached_result(track_id: int | None, frame_number: int) -> Classification | None:
    if track_id is None or CACHE_TTL_FRAMES == 0:
        return None
    with _cache_lock:
        cached = _classification_cache.get(track_id)
        if cached is None:
            return None
        if cached.expires_at_frame < frame_number:
            del _classification_cache[track_id]
            return None
        _classification_cache.move_to_end(track_id)
        return cached.result


def _cache_result(
    track_id: int | None, result: Classification, frame_number: int
) -> None:
    if track_id is None or CACHE_TTL_FRAMES == 0:
        return
    with _cache_lock:
        _classification_cache[track_id] = _CachedClassification(
            result=result,
            expires_at_frame=frame_number + CACHE_TTL_FRAMES,
        )
        _classification_cache.move_to_end(track_id)
        while len(_classification_cache) > CACHE_MAX_ENTRIES:
            _classification_cache.popitem(last=False)


def process_frame(frame: VideoFrame) -> bool:
    """Classify uncached tracked regions and attach top-1 results to each ROI."""
    regions = list(frame.regions())[:MAX_ROIS_PER_FRAME]
    if not regions:
        return True

    frame_number = _next_frame_number()
    uncached_regions = []
    uncached_track_ids = []
    uncached_crops = []
    results = []

    with frame.data() as image_bgr:
        if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
            raise ValueError(
                "ovms_classification requires video/x-raw,format=BGR before gvapython"
            )

        for roi in regions:
            track_id = roi.object_id()
            cached = _cached_result(track_id, frame_number)
            if cached is not None:
                results.append((roi, cached))
                continue

            rect = roi.rect()
            if rect.w <= 0 or rect.h <= 0:
                continue
            crop = image_bgr[rect.y : rect.y + rect.h, rect.x : rect.x + rect.w].copy()
            if crop.size == 0:
                continue

            uncached_regions.append(roi)
            uncached_track_ids.append(track_id)
            uncached_crops.append(crop)

    try:
        batch_results = classify_batch(uncached_crops, top_k=1)
    except OvmsInferenceError:
        logger.exception("OVMS classification request failed for uncached ROIs")
        raise

    for roi, track_id, classifications in zip(
        uncached_regions, uncached_track_ids, batch_results, strict=True
    ):
        top_result = classifications[0]
        _cache_result(track_id, top_result, frame_number)
        results.append((roi, top_result))

    for roi, top_result in results:
        roi.add_tensor(
            _classification_tensor(
                top_result.label,
                top_result.confidence,
                top_result.class_id,
            )
        )

    return True
