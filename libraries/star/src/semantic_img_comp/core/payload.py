# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass


@dataclass
class PayloadSizeLog:
    """Data model for payload byte accounting by segment.

    Field notes:
    - `header`: number of bytes for frame-level header fields.
    - `background`: number of bytes for encoded background payload and its metadata.
    - `objects`: number of bytes for encoded object crop payloads.
    - `metadata`: number of bytes for non-payload metadata (sizes, bboxes, ids, counts).
    """
    header: int = 0
    background: int = 0
    objects: int = 0
    metadata: int = 0
