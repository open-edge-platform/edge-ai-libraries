# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Event types emitted by the Session Manager."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class EventType(str, Enum):
    ENTERED = "ENTERED"
    EXITED = "EXITED"
    LOITER = "LOITER"
    PERSON_LOST = "PERSON_LOST"


@dataclass
class RegionEvent:
    """Event produced when a person enters or exits a region.

    ``zone_type`` is a free-form string sourced from ``zone_config.json`` /
    ``rules.yaml`` so adding a new zone type does not require a code change.
    """
    event_type: EventType
    object_id: str
    region_id: str
    region_name: str
    zone_type: str
    timestamp: datetime
    scene_id: str = ""  # SceneScape scene UUID
    dwell_seconds: Optional[float] = None   # populated on EXIT
    minio_thumbnail_key: Optional[str] = None
    # ISO timestamp of when the person entered this region; populated on
    # EXITED so consumers can scope per-visit work (e.g. frame cleanup
    # only for this visit's bucket prefix, not all of the person's visits).
    entry_timestamp: Optional[str] = None
