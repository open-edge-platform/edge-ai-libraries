# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Internal domain schemas for alert configuration and dispatch.

AlertConfig is a lightweight version of the one in live-video-alert-agent:
no 'prompt' field (VLM inference does not run in this service).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class EscalationConfig(BaseModel):
    """Escalation rule: after N consecutive YES detections, fire extra tools."""
    threshold_consecutive: int = Field(default=3, ge=2)
    additional_tools: List[str] = Field(default_factory=list)


class AlertConfig(BaseModel):
    """
    Internal alert configuration used by AlertActionAgent for dispatch.

    Built from AlertActionRequest in the API layer; not exposed directly.
    """
    name: str = Field(..., min_length=1, max_length=128)
    enabled: bool = True
    tools: List[str] = Field(default_factory=lambda: ["log_alert"])
    tool_arguments: Dict[str, dict] = Field(default_factory=dict)
    escalation: Optional[EscalationConfig] = None

    @field_validator("name")
    @classmethod
    def name_no_special_chars(cls, v: str) -> str:
        if not re.match(r"^[\w\s\-\.]+$", v):
            raise ValueError(
                "Alert name may only contain letters, digits, spaces, hyphens, dots, and underscores"
            )
        return v
