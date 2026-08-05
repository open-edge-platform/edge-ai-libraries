# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Adapted from YOLOX: https://github.com/Megvii-BaseDetection/YOLOX

import cv2
import numpy as np


def compute_iou(box, boxes):
    """Compute IoU between a single box and an array of boxes.

    Args:
        box: Array-like of shape (4,) in [x1, y1, x2, y2].
        boxes: Array-like of shape (N, 4) in [x1, y1, x2, y2].

    Returns:
        IoU values as a numpy array of shape (N,).
    """
    boxes = np.asarray(boxes)
    box = np.asarray(box)
    if boxes.size == 0:
        return np.asarray([])

    # Intersection top-left and bottom-right coordinates.
    xx1 = np.maximum(box[0], boxes[:, 0])
    yy1 = np.maximum(box[1], boxes[:, 1])
    xx2 = np.minimum(box[2], boxes[:, 2])
    yy2 = np.minimum(box[3], boxes[:, 3])

    # Clamp to zero to avoid negative widths/heights for non-overlapping boxes.
    inter_w = np.maximum(0.0, xx2 - xx1)
    inter_h = np.maximum(0.0, yy2 - yy1)
    inter = inter_w * inter_h

    # Compute union area and return IoU for each box.
    area_box = (box[2] - box[0] + 1) * (box[3] - box[1] + 1)
    area_boxes = (boxes[:, 2] - boxes[:, 0] + 1) * (boxes[:, 3] - boxes[:, 1] + 1)
    union = area_box + area_boxes - inter
    return np.where(union > 0, inter / union, 0.0)

def preproc(img, input_size, swap=(2, 0, 1)):
    """
    Preprocess image for YOLOX inference.
    
    Args:
        img: Input image (numpy array)
        input_size: Target input size (height, width)
        swap: Channel swap configuration
        
    Returns:
        Tuple of (preprocessed_image, scale_ratio)
    """
    if len(img.shape) == 3:
        padded_img = np.ones((input_size[0], input_size[1], 3), dtype=np.uint8) * 114
    else:
        padded_img = np.ones(input_size, dtype=np.uint8) * 114

    r = min(input_size[0] / img.shape[0], input_size[1] / img.shape[1])
    resized_img = cv2.resize(
        img,
        (int(img.shape[1] * r), int(img.shape[0] * r)),
        interpolation=cv2.INTER_LINEAR,
    ).astype(np.uint8)
    padded_img[: int(img.shape[0] * r), : int(img.shape[1] * r)] = resized_img

    padded_img = padded_img.transpose(swap)
    padded_img = np.ascontiguousarray(padded_img, dtype=np.float32)
    padded_img = np.expand_dims(padded_img, axis=0)

    return padded_img, r

def nms(boxes, scores, nms_thr):
    """Single class NMS implemented in Numpy."""
    # Sort by score descending so we keep the highest-confidence boxes first.
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        # Pick the next highest-score box and suppress overlaps above threshold.
        i = order[0]
        keep.append(i)
        if order.size == 1:
            break
        ious = compute_iou(boxes[i], boxes[order[1:]])
        inds = np.where(ious <= nms_thr)[0]
        # Shift indices by 1 because we skipped the current top box.
        order = order[inds + 1]
    return keep


def multiclass_nms(boxes, scores, nms_thr, score_thr, class_agnostic=True):
    """Multiclass NMS implemented in Numpy"""
    if class_agnostic:
        nms_method = multiclass_nms_class_agnostic
    else:
        nms_method = multiclass_nms_class_aware
    return nms_method(boxes, scores, nms_thr, score_thr)


def multiclass_nms_class_aware(boxes, scores, nms_thr, score_thr):
    """Multiclass NMS implemented in Numpy. Class-aware version."""
    final_dets = []
    num_classes = scores.shape[1]
    for cls_ind in range(num_classes):
        cls_scores = scores[:, cls_ind]
        valid_score_mask = cls_scores > score_thr
        if valid_score_mask.sum() == 0:
            continue
        else:
            valid_scores = cls_scores[valid_score_mask]
            valid_boxes = boxes[valid_score_mask]
            keep = nms(valid_boxes, valid_scores, nms_thr)
            if len(keep) > 0:
                cls_inds = np.ones((len(keep), 1)) * cls_ind
                dets = np.concatenate(
                    [valid_boxes[keep], valid_scores[keep, None], cls_inds], 1
                )
                final_dets.append(dets)
    if len(final_dets) == 0:
        return None
    return np.concatenate(final_dets, 0)


def multiclass_nms_class_agnostic(boxes, scores, nms_thr, score_thr):
    """Multiclass NMS implemented in Numpy. Class-agnostic version."""
    cls_inds = scores.argmax(1)
    cls_scores = scores[np.arange(len(cls_inds)), cls_inds]

    valid_score_mask = cls_scores > score_thr
    if valid_score_mask.sum() == 0:
        return None
    valid_scores = cls_scores[valid_score_mask]
    valid_boxes = boxes[valid_score_mask]
    valid_cls_inds = cls_inds[valid_score_mask]
    keep = nms(valid_boxes, valid_scores, nms_thr)
    if keep:
        dets = np.concatenate(
            [valid_boxes[keep], valid_scores[keep, None], valid_cls_inds[keep, None]], 1
        )
    return dets


def demo_postprocess(outputs, img_size, p6=False):
    """
    YOLOX postprocessing to decode outputs.
    
    Args:
        outputs: Raw model outputs
        img_size: Input image size
        p6: Whether using P6 model variant
        
    Returns:
        Decoded detections
    """
    grids = []
    expanded_strides = []
    strides = [8, 16, 32] if not p6 else [8, 16, 32, 64]

    hsizes = [img_size[0] // stride for stride in strides]
    wsizes = [img_size[1] // stride for stride in strides]

    for hsize, wsize, stride in zip(hsizes, wsizes, strides):
        xv, yv = np.meshgrid(np.arange(wsize), np.arange(hsize))
        grid = np.stack((xv, yv), 2).reshape(1, -1, 2)
        grids.append(grid)
        shape = grid.shape[:2]
        expanded_strides.append(np.full((*shape, 1), stride))

    grids = np.concatenate(grids, 1)
    expanded_strides = np.concatenate(expanded_strides, 1)
    outputs[..., :2] = (outputs[..., :2] + grids) * expanded_strides
    outputs[..., 2:4] = np.exp(outputs[..., 2:4]) * expanded_strides

    return outputs
