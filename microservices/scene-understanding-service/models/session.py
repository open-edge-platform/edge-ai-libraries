# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Person session data model for loss prevention tracking."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set


@dataclass
class RegionVisit:
    """Record of a person visiting a specific region."""
    region_id: str
    region_name: str
    zone_type: str
    entry_time: datetime
    exit_time: Optional[datetime] = None

    @property
    def duration_seconds(self) -> float:
        end = self.exit_time or datetime.now(timezone.utc)
        return (end - self.entry_time).total_seconds()


@dataclass
class PersonSession:
    """
    Live state of a tracked person in the store.

    Created when SceneScape first reports an object_id.
    Updated on every subsequent scene/region event.
    Expired when the ID is absent for longer than session_timeout.

    Fields aligned with the Store-wide Loss Prevention specification:
      object_id          — SceneScape's persistent person identifier
      first_seen         — Session creation timestamp
      last_seen          — Last activity timestamp for expiry
      visited_checkout   — Whether the person entered any checkout zone
      visited_high_value — Whether the person entered any high-value zone
      zone_visit_counts  — Count of entries per region_id
      current_zones      — Currently occupied zones with entry timestamps
      loiter_alerted     — Tracks if a loiter alert has already been triggered per zone
      concealment_suspected — Set to true if behavioral analysis confirms suspicious behavior
    """
    object_id: str
    first_seen: datetime
    last_seen: datetime
    scene_id: str = ""  # SceneScape scene UUID this person belongs to

    # Current position
    current_cameras: List[str] = field(default_factory=list)
    bbox: Optional[Dict] = None  # {x, y, w, h} on primary camera

    # Current zones: {region_id: entry_timestamp_iso}
    current_zones: Dict[str, str] = field(default_factory=dict)

    # History
    camera_history: List[str] = field(default_factory=list)
    region_visits: List[RegionVisit] = field(default_factory=list)

    # Zone visit counts: {region_id: count}
    zone_visit_counts: Dict[str, int] = field(default_factory=dict)

    # Dynamic session flags — config-driven (see session_flags in rules.yaml).
    # Keys are flag names (e.g. "visited_checkout"), values are booleans.
    flags: Dict[str, bool] = field(default_factory=dict)

    # Backward-compatible accessors for well-known flags.
    @property
    def visited_checkout(self) -> bool:
        return self.flags.get("visited_checkout", False)

    @property
    def visited_exit(self) -> bool:
        return self.flags.get("visited_exit", False)

    @property
    def visited_high_value(self) -> bool:
        return self.flags.get("visited_high_value", False)

    @property
    def concealment_suspected(self) -> bool:
        return self.flags.get("concealment_suspected", False)

    # Re-identification state from SceneScape: "pending_collection" | "matched" | ""
    # Sessions remain hidden from the UI until reid_state == "matched" so that
    # provisional flickering tracks (which are merged via previous_ids_chain)
    # don't appear as ghost rows.
    reid_state: str = ""

    # Generic per-(alert_type, scope_key) dedup map. Driven entirely by the
    # ``fire_once_per`` field on each alert action in rules.yaml — adding a new
    # alert type does not require any code change here.
    #
    #   alert_dedup["LOITERING"][region_id]   -> True   (scope=zone)
    #   alert_dedup["CHECKOUT_BYPASS"]["*"]   -> True   (scope=session)
    alert_dedup: Dict[str, Dict[str, bool]] = field(default_factory=dict)

    # Frame references (SeaweedFS keys for rolling buffer — cropped person frames)
    frame_buffer: List[str] = field(default_factory=list)
    max_frame_buffer: int = 20  # ~10s at 2fps per spec

    def get_open_visits(self) -> List[RegionVisit]:
        """Return region visits that have not been closed."""
        return [v for v in self.region_visits if v.exit_time is None]

    def close_visit(self, region_id: str, exit_time: datetime) -> Optional[RegionVisit]:
        """Close an open visit for a given region."""
        for visit in self.region_visits:
            if visit.region_id == region_id and visit.exit_time is None:
                visit.exit_time = exit_time
                return visit
        return None

    def add_frame_key(self, key: str) -> None:
        """Append a frame key, evicting the oldest if buffer is full."""
        self.frame_buffer.append(key)
        if len(self.frame_buffer) > self.max_frame_buffer:
            self.frame_buffer.pop(0)

    def is_in_zone(self, region_id: str) -> bool:
        """Check if the person is currently in a specific zone."""
        return region_id in self.current_zones

    def enter_zone(self, region_id: str, timestamp: datetime) -> None:
        """Record zone entry."""
        self.current_zones[region_id] = timestamp.isoformat()
        self.zone_visit_counts[region_id] = self.zone_visit_counts.get(region_id, 0) + 1
        # Reset per-visit alert flags so the pipeline can re-analyze and
        # re-alert on re-entry (each visit is independently eligible).
        self.clear_alerts_for_scope(region_id)

    def exit_zone(self, region_id: str) -> Optional[str]:
        """Record zone exit. Returns the entry timestamp if was present."""
        return self.current_zones.pop(region_id, None)

    # ---- generic per-alert-type dedup helpers --------------------------------

    def is_alerted(self, alert_type: str, scope_key: str) -> bool:
        """Return True if an alert of this type has already fired for the scope."""
        return bool(self.alert_dedup.get(alert_type, {}).get(scope_key))

    def mark_alerted(self, alert_type: str, scope_key: str) -> None:
        """Mark an alert of this type as fired for the given scope."""
        self.alert_dedup.setdefault(alert_type, {})[scope_key] = True

    def clear_alerts_for_scope(self, scope_key: str) -> None:
        """Clear all per-type dedup flags for a single scope (e.g. on re-entry)."""
        for type_map in self.alert_dedup.values():
            type_map.pop(scope_key, None)

    # Backward-compatible accessors so legacy call sites that read
    # ``session.loiter_alerted.get(region_id)`` continue to work without
    # caring that the storage moved into ``alert_dedup``.
    @property
    def loiter_alerted(self) -> Dict[str, bool]:
        return self.alert_dedup.setdefault("LOITERING", {})

    @property
    def repeated_visit_alerted(self) -> Dict[str, bool]:
        return self.alert_dedup.setdefault("REPEATED_VISIT", {})

    @property
    def ba_alerted(self) -> Dict[str, bool]:
        return self.alert_dedup.setdefault("CONCEALMENT", {})