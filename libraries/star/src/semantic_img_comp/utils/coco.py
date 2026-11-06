# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: utils/coco.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: helper function to load annotations and store detections in coco compliant format.
"""

from pycocotools.coco import COCO

# ------------------------------
# LOAD COCO
# ------------------------------
def load_coco_annotations(annotation_path):
    """
    Load annotations from the specified path.
    The file must follow the COCO annotation schema.

    Returns:
        COCO: An instance of the COCO class with the loaded annotations.
    """
    return COCO(annotation_path)

# ------------------------------
# CONVERT DETS → COCO JSON ENTRY
# ------------------------------
def dets_to_coco(crops, image_id):
    """
    Converts a list of object detection results into COCO-compatible JSON format.

    Writes the raw model class index directly as ``category_id``. Any remapping
    from model class indices to annotation category IDs should be done at
    evaluation time via ``update_cat_ids``, not here.

    Args:
        crops: List of ``ObjData`` with ``bbox``, ``category_id``, and ``det_conf``.
        image_id (int): The ID of the image associated with these detections.

    Returns:
        list: A list of dicts in COCO results format:
              - "image_id": image identifier.
              - "category_id": raw model class index.
              - "bbox": [x, y, width, height].
              - "score": detection confidence.
    """
    out = []
    for crop_data in crops:
        x1, y1, x2, y2 = crop_data.bbox
        w = max(0.0, x2 - x1)
        h = max(0.0, y2 - y1)
        out.append({
            "image_id": int(image_id),
            "category_id": int(crop_data.category_id),
            "bbox": [float(x1), float(y1), float(w), float(h)],
            "score": float(crop_data.det_conf),
        })
    return out