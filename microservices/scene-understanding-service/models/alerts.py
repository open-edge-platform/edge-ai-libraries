# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Alert data models for loss prevention."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
import uuid


@dataclass
class Alert:
    """A suspicious-activity alert produced by the system.

    ``alert_type`` and ``alert_level`` are free-form strings sourced
    verbatim from the YAML rule definitions (rules.yaml) so adding a new
    rule with a brand-new alert type / severity does not require a code
    change.
    """
    alert_type: str
    alert_level: str
    object_id: str
    timestamp: datetime
    scene_id: str = ""  # SceneScape scene UUID
    region_id: Optional[str] = None
    region_name: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    evidence_keys: List[str] = field(default_factory=list)  # MinIO keys
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type,
            "alert_level": self.alert_level,
            "object_id": self.object_id,
            "scene_id": self.scene_id,
            "timestamp": self.timestamp.isoformat(),
            "region_id": self.region_id,
            "region_name": self.region_name,
            "details": self.details,
            "evidence_keys": self.evidence_keys,
        }
