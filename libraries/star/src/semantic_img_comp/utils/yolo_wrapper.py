# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: utils/yolo_wrapper.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: wrapper function to run yolo on images. Tiling is optional and supported.
"""

from typing import Any, List, Tuple
import logging
import torch
import numpy as np
from PIL import Image

try:
    from transformers import RTDetrForObjectDetection
except ImportError as exc:  # pragma: no cover - depends on optional extra
    RTDetrForObjectDetection = Any  # type: ignore[assignment]
    _RTDETR_IMPORT_ERROR: ImportError | None = exc
else:
    _RTDETR_IMPORT_ERROR = None
# ------------------------------
# YOLO WRAPPER
# ------------------------------

Det = Tuple[float, float, float, float, float, int]
LOGGER = logging.getLogger(__name__)


def _ensure_hwc3(img_np: Any) -> np.ndarray:
    arr = np.asarray(img_np)
    if arr.ndim == 2:
        return np.repeat(arr[:, :, None], 3, axis=2)
    if arr.ndim == 3 and arr.shape[2] == 1:
        return np.repeat(arr, 3, axis=2)
    if arr.ndim == 3 and arr.shape[2] >= 3:
        return arr[:, :, :3]
    raise ValueError(f"Expected image with shape (H, W) or (H, W, C), got shape={arr.shape}")


def _iou_xyxy(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    inter_x1 = np.maximum(box[0], boxes[:, 0])
    inter_y1 = np.maximum(box[1], boxes[:, 1])
    inter_x2 = np.minimum(box[2], boxes[:, 2])
    inter_y2 = np.minimum(box[3], boxes[:, 3])

    inter_w = np.maximum(0.0, inter_x2 - inter_x1)
    inter_h = np.maximum(0.0, inter_y2 - inter_y1)
    inter = inter_w * inter_h

    box_area = max(0.0, (box[2] - box[0]) * (box[3] - box[1]))
    boxes_area = np.maximum(0.0, (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1]))
    union = np.maximum(1e-12, box_area + boxes_area - inter)
    return inter / union

def _iom_over_smaller_xyxy(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    inter_x1 = np.maximum(box[0], boxes[:, 0])
    inter_y1 = np.maximum(box[1], boxes[:, 1])
    inter_x2 = np.minimum(box[2], boxes[:, 2])
    inter_y2 = np.minimum(box[3], boxes[:, 3])

    inter_w = np.maximum(0.0, inter_x2 - inter_x1)
    inter_h = np.maximum(0.0, inter_y2 - inter_y1)
    inter = inter_w * inter_h

    box_area = max(0.0, (box[2] - box[0]) * (box[3] - box[1]))
    boxes_area = np.maximum(0.0, (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1]))
    smaller_area = np.maximum(1e-12, np.minimum(box_area, boxes_area))
    return inter / smaller_area

def _nms_classwise(dets: List[Det], iou_threshold: float, iom_threshold: float = 0.8) -> List[Det]:
    if not dets:
        return []

    # Merge overlapping tile-edge duplicates class-agnostically.
    boxes = np.asarray([d[:4] for d in dets], dtype=np.float32)
    scores = np.asarray([d[4] for d in dets], dtype=np.float32)
    order = np.argsort(-scores)
    kept: List[Det] = []

    while order.size > 0:
        idx = int(order[0])
        kept.append(dets[idx])
        if order.size == 1:
            break

        rem = order[1:]
        ious = _iou_xyxy(boxes[idx], boxes[rem])
        ioms = _iom_over_smaller_xyxy(boxes[idx], boxes[rem])
        suppress = (ious > iou_threshold) | (ioms > iom_threshold)
        order = rem[~suppress]

    return kept


def _extract_dets_from_result(res: Any, allowed_classes) -> List[Det]:
    dets: List[Det] = []
    if getattr(res, "boxes", None) is None:
        return dets

    try:
        boxes = res.boxes.xyxy.cpu().numpy()
        confs = res.boxes.conf.cpu().numpy()
        clses = res.boxes.cls.cpu().numpy().astype(int)
    except (AttributeError, TypeError, RuntimeError, ValueError) as exc:
        raise RuntimeError("Failed to parse YOLO prediction boxes") from exc

    for b, c, cl in zip(boxes, confs, clses):
        cl = int(cl)
        if allowed_classes is not None and cl not in allowed_classes:
            continue
        x1, y1, x2, y2 = b.tolist()
        dets.append((float(x1), float(y1), float(x2), float(y2), float(c), cl))

    return dets


def run_yolo(img_np, yolo, cfg, tile_size=None, imgsz=640) -> List[Det]:
    """
    img_np: input image as numpy array
    Returns list of object metadata tuples (x1,y1,x2,y2,conf,class_index)
    """
    DEVICE = cfg.app.device
    YOLO_CONF = cfg.model.pre_comp_conf
    YOLO_IOU = cfg.model.iou_threshold
    YOLO_MAX_DET = cfg.model.max_detections
    # Optional class filtering: when absent, keep all detected classes.
    ALLOWED_CLASSES = cfg.model.valid_obj_categories
    overlap = cfg.model.tile_overlap
    tile_nms_iou = float(getattr(cfg.model, "tile_nms_iou", YOLO_IOU))
    merge_tile_detections = bool(getattr(cfg.model, "merge_tile_detections", True))
    original_shape = np.asarray(img_np).shape
    arr = _ensure_hwc3(img_np)
    if arr.shape != original_shape:
        LOGGER.debug("Auto-expanded YOLO input shape from %s to %s", original_shape, arr.shape)

    dets: List[Det] = []

    if tile_size is not None:
        tile_size = int(tile_size)
        if tile_size <= 0:
            raise ValueError(f"tile_size must be > 0, got {tile_size}")
        if not (0.0 <= tile_nms_iou <= 1.0):
            raise ValueError(f"tile_nms_iou must be in [0, 1], got {tile_nms_iou}")
        overlap = 0 if overlap is None else int(overlap)
        if overlap < 0:
            raise ValueError(f"tile_overlap must be >= 0, got {overlap}")
        if overlap >= tile_size:
            raise ValueError(
                f"tile_overlap must be smaller than tile_size; got overlap={overlap}, tile_size={tile_size}"
            )

    if tile_size is None:
        results = yolo.predict(
            arr,
            device=DEVICE,
            imgsz=imgsz,
            conf=YOLO_CONF,
            iou=YOLO_IOU,
            max_det=YOLO_MAX_DET,
            verbose=False,
        )
        if not results:
            return dets
        return _extract_dets_from_result(results[0], ALLOWED_CLASSES)

    # ---- TILE MODE ----

    H, W, _ = arr.shape
    step = tile_size - overlap
    tile_batch_size = int(
        getattr(
            cfg.model,
            "tile_batch_size",
            8 if str(DEVICE).lower().startswith("cpu") else 1,
        )
    )
    if tile_batch_size <= 0:
        raise ValueError(f"tile_batch_size must be > 0, got {tile_batch_size}")

    tiles: List[np.ndarray] = []
    origins: List[tuple[int, int]] = []
    for y0 in range(0, H, step):
        for x0 in range(0, W, step):
            tiles.append(arr[y0:min(y0 + tile_size, H), x0:min(x0 + tile_size, W)])
            origins.append((x0, y0))

    for start in range(0, len(tiles), tile_batch_size):
        batch_tiles = tiles[start:start + tile_batch_size]
        batch_origins = origins[start:start + tile_batch_size]

        # batch_size==1: pass a single array (not a list) — identical to old per-tile path.
        if tile_batch_size == 1:
            predict_input = batch_tiles[0]
        else:
            predict_input = batch_tiles

        results = yolo.predict(
            predict_input,
            device=DEVICE,
            imgsz=imgsz,
            conf=YOLO_CONF,
            iou=YOLO_IOU,
            max_det=YOLO_MAX_DET,
            verbose=False,
        )

        if not isinstance(results, (list, tuple)):
            results = [results]

        if tile_batch_size == 1:
            # Single-array path always returns exactly one result.
            if results:
                x0, y0 = batch_origins[0]
                for x1, y1, x2, y2, conf, cl in _extract_dets_from_result(results[0], ALLOWED_CLASSES):
                    dets.append((x1 + x0, y1 + y0, x2 + x0, y2 + y0, conf, cl))
            continue

        # Batched path: gracefully fall back to per-tile if wrapper returns unexpected count.
        if len(results) != len(batch_tiles):
            for tile, (x0, y0) in zip(batch_tiles, batch_origins):
                single_results = yolo.predict(
                    tile,
                    device=DEVICE,
                    imgsz=imgsz,
                    conf=YOLO_CONF,
                    iou=YOLO_IOU,
                    max_det=YOLO_MAX_DET,
                    verbose=False,
                )
                if not single_results:
                    continue
                for x1, y1, x2, y2, conf, cl in _extract_dets_from_result(single_results[0], ALLOWED_CLASSES):
                    dets.append((x1 + x0, y1 + y0, x2 + x0, y2 + y0, conf, cl))
            continue

        for res, (x0, y0) in zip(results, batch_origins):
            for x1, y1, x2, y2, conf, cl in _extract_dets_from_result(res, ALLOWED_CLASSES):
                dets.append((x1 + x0, y1 + y0, x2 + x0, y2 + y0, conf, cl))

    if merge_tile_detections and overlap > 0 and dets:
        dets = _nms_classwise(dets, iou_threshold=tile_nms_iou)

    return dets


# Same "orig_dets" shape your pipeline expects:
# [x1, y1, x2, y2, conf, category_id]

def run_rtdetr(
    pil_img: Image.Image,
    processor: Any,
    model: RTDetrForObjectDetection,
    score_thresh: float = 0.3,
    allowed_classes=None,
    device: str | None = None,
) -> List[Det]:
    if _RTDETR_IMPORT_ERROR is not None:
        raise ImportError(
            "RT-DETR support requires the optional 'transformers' dependency to be installed."
        ) from _RTDETR_IMPORT_ERROR
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    current_device = model.device
    if current_device is None or str(current_device) != device:
        model = model.to(device)

    inputs = processor(images=pil_img, return_tensors="pt")
    inputs = inputs.to(device)

    with torch.no_grad():
        outputs = model(**inputs)

    # Convert RT-DETR outputs to pixel boxes on the original image
    target_sizes = torch.tensor([pil_img.size[::-1]], device=device)  # (h, w)
    results: dict[str, Any] = processor.post_process_object_detection(
        outputs, target_sizes=target_sizes, threshold=score_thresh
    )[0]

    dets: List[Det] = []
    for box, score, label in zip(results["boxes"], results["scores"], results["labels"]):
        cl = int(label)
        if allowed_classes is not None and cl not in allowed_classes:
            continue
        x1, y1, x2, y2 = box.tolist()
        dets.append((x1, y1, x2, y2, float(score), int(label)))
    return dets
