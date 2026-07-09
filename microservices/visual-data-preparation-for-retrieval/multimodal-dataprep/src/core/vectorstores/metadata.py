# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Backend-neutral canonical metadata model and per-backend adapters.

The DataPrep service builds a single, backend-neutral metadata dict for every
embedding (frame or text/summary). Each vector-store backend then adapts that
canonical dict to its own accepted representation:

* **VDMS** accepts only scalar values (str/int/float/bool); lists and nested
  structures must be flattened to strings.
* **Milvus** (with dynamic fields enabled) preserves lists and nested values
  as-is, so the adapter is effectively a pass-through that only drops ``None``.

The canonical field names below are the contract the dataprep *writes*. They are
NOT tied to any one backend; a retriever consuming the data maps these to its
own query schema. The VDMS retriever field names are one such mapping, not the
contract itself.
"""

from __future__ import annotations

import json
from typing import List

# ---------------------------------------------------------------------------
# Canonical metadata field names (superset; fields are nullable/optional and
# only populated when applicable to a given embedding).
# ---------------------------------------------------------------------------
CANONICAL_FIELDS: List[str] = [
    # identity / source
    "video_id",
    "bucket_name",
    "video_name",
    "filename",
    # frame positioning
    "frame_id",
    "timestamp",            # frame time within the video, seconds
    "frame_interval",
    "fps",
    "total_frames",
    "video_duration_seconds",
    # descriptive
    "tags",                 # list[str]
    "date_time",
    "upload_timestamp",
    "video_url",
    "video_rel_url",
    # object-detection crop fields (present only when detection runs)
    "label",
    "bbox",                 # list[number]
    "crop_id",
]


def adapt_for_vdms(metadata: dict) -> dict:
    """Adapt canonical metadata for VDMS storage.

    VDMS accepts only scalar values. Lists are joined into comma-separated
    strings and dicts are JSON-encoded; ``None`` values are dropped.
    """
    cleaned: dict = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            cleaned[key] = value
        elif isinstance(value, list):
            cleaned[key] = ",".join(str(item) for item in value)
        elif isinstance(value, dict):
            cleaned[key] = json.dumps(value)
        else:
            cleaned[key] = str(value)
    return cleaned


def adapt_for_milvus(metadata: dict) -> dict:
    """Adapt canonical metadata for Milvus storage.

    With dynamic fields enabled, Milvus preserves lists and nested values, so
    this only drops ``None`` values (which Milvus dynamic fields reject).
    """
    return {key: value for key, value in metadata.items() if value is not None}
