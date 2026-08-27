# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Backend-neutral canonical metadata contract and reusable coercion helpers.

The DataPrep service builds a single, backend-neutral metadata dict for every
embedding (full frame, detected crop, or text/summary). Before an embedding is
persisted, the active vector-store backend adapts that dict to its own accepted
representation via its :meth:`BaseVectorStore.clean_metadata` implementation.

This module owns only the pieces that are common to **every** backend and knows
nothing about any specific vector DB:

* :data:`CANONICAL_FIELDS` — the *enforced* contract: the exact set of field
  names the pipeline is allowed to persist.
* :func:`project_to_canonical` — drops any key not in the contract (e.g.
  transient pipeline plumbing such as ``shm``, ``shape``, ``dtype``,
  ``frame_id``, ``stream_id``, ``batch_id``) so it never leaks into the DB.
* :func:`flatten_to_scalars` — a reusable value-coercion helper for backends
  (like VDMS) that accept only scalar metadata values.

Every backend's ``clean_metadata`` composes these primitives with its own rule;
the backend-specific adaptation lives in that backend's store module, not here.

The field names below are kept in sync with what the pipeline actually emits
(the ``FrameMetadata`` dataclass in ``core.embedding.embedding_helper``, the
detected-crop update in the same module, and the text/summary metadata in
``endpoints.document_processing.process_text``). A retriever consuming the data
maps these to its own query schema; the VDMS retriever field names are one such
mapping, not the contract itself.
"""

from __future__ import annotations

import json
from typing import List

from src.common import logger

# ---------------------------------------------------------------------------
# Canonical metadata field names (the enforced persisted contract).
#
# This is a superset across the three embedding types; a given embedding only
# populates the fields applicable to it. Any field NOT listed here is stripped
# by the adapters before storage. Keep this in sync with the pipeline emitters:
#   * full frame  -> FrameMetadata (core.embedding.embedding_helper)
#   * crop        -> crop_metadata update (core.embedding.embedding_helper)
#   * text/summary-> text_metadata (endpoints.document_processing.process_text)
# ---------------------------------------------------------------------------
CANONICAL_FIELDS: List[str] = [
    # identity / source
    "video_id",
    "bucket_name",
    "filename",
    "video_name",           # text/summary embeddings
    "video_index",
    "source_path",          # origin path for media ingested from a mounted dir
    # frame positioning
    "extended_frame_id",
    "frame_number",
    "timestamp",            # frame time within the video, seconds
    "frame_type",
    "total_frames",
    "fps",
    "video_duration",
    "video_duration_seconds",
    # descriptive
    "tags",                 # list[str] (flattened to CSV for VDMS)
    "video_url",
    "video_rel_url",
    "created_at",
    "date_time",
    # object-detection crop fields (present only when detection runs)
    "is_detected_crop",
    "crop_index",
    "crop_bbox",            # list[number]
    "detected_label",
    "detected_class_id",
    "detection_confidence",
    "merged_boxes_count",
    "context_expansion_applied",
    # media kind ("video" / "image") and text/summary fields
    "content_type",
    "video_start_time",
    "video_end_time",
]

# O(1) membership set used by the adapters' projection step.
_CANONICAL_SET = frozenset(CANONICAL_FIELDS)

# Reserved carrier key for caller-supplied metadata. Callers (ingest endpoints,
# directory sidecars) place a flat dict of their own keys here; the projection
# step below flattens it alongside the canonical fields so the values are
# directly filterable by a retriever, while everything else stays enforced.
CUSTOM_METADATA_KEY = "custom_metadata"


def project_to_canonical(metadata: dict) -> dict:
    """Drop any key that is not part of the canonical contract.

    This is the enforcement point: transient pipeline keys (``shm``, ``shape``,
    ``dtype``, ``frame_id``, ``stream_id``, ``batch_id`` and similar) never
    reach the vector store. Dropped keys are logged at DEBUG level to surface
    unexpected fields without failing the request.

    Caller-supplied metadata carried in :data:`CUSTOM_METADATA_KEY` is flattened
    into the result as top-level fields. Canonical fields always win on a name
    collision, so user metadata can never shadow or corrupt the contract.
    """
    projected = {key: value for key, value in metadata.items() if key in _CANONICAL_SET}

    custom = metadata.get(CUSTOM_METADATA_KEY)
    if isinstance(custom, dict):
        for key, value in custom.items():
            if key in _CANONICAL_SET or key == CUSTOM_METADATA_KEY:
                logger.debug("Ignoring custom metadata key colliding with contract: %s", key)
                continue
            projected.setdefault(key, value)

    if logger.isEnabledFor(10):  # logging.DEBUG
        dropped = [
            key
            for key in metadata
            if key not in _CANONICAL_SET and key != CUSTOM_METADATA_KEY
        ]
        if dropped:
            logger.debug("Dropped non-canonical metadata keys before storage: %s", dropped)
    return projected


def flatten_to_scalars(metadata: dict) -> dict:
    """Coerce metadata values to the scalars a scalar-only backend accepts.

    Intended for backends such as VDMS that reject lists/nested structures:
    lists are joined into comma-separated strings, dicts are JSON-encoded, other
    non-scalar values are stringified, and ``None`` values are dropped. Callers
    should typically pass the output of :func:`project_to_canonical`.
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
