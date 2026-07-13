# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Public API request / response schemas.

AlertActionRequest is the generic multimodal entry point — callers pass
text, image, audio, or video payloads together with alert context and the
service dispatches the configured tools via ADK or rule-based mode.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from src.schemas.monitor import EscalationConfig


class DedupConfig(BaseModel):
    """Per-request deduplication configuration."""
    enabled: bool = False
    strategy: str = "field_hash"
    fields: List[str] = Field(default_factory=list)
    window_seconds: int = 30
    on_missing: str = "skip"
    hash_algorithm: str = "sha1"
    hash_truncate: int = 16


class Payload(BaseModel):
    """
    A single media artifact attached to an alert action request.

    Supported modalities
    --------------------
    text    — plain text / transcript / NLP output
    image   — still frame (JPEG, PNG, …)
    audio   — audio clip (WAV, MP3, …)
    video   — video segment (MP4, …)
    binary  — arbitrary binary blob

    Encoding
    --------
    base64  — inline base64-encoded bytes in ``data_base64``
    uri     — remote or local URI in ``uri`` (S3, MinIO, NFS, file://)
    raw     — raw text in ``data_text`` (for kind=text only)

    Metadata examples
    -----------------
    Image:  {"width": 1920, "height": 1080}
    Audio:  {"duration_ms": 3000, "sample_rate": 16000, "channels": 1}
    Video:  {"duration_ms": 5000, "fps": 25.0, "width": 1280, "height": 720, "codec": "h264"}
    Text:   {"language": "en", "confidence": 0.97}
    """

    kind: Literal["text", "image", "audio", "video", "binary"] = "text"
    mime_type: str = "text/plain"
    encoding: Literal["base64", "uri", "raw"] = "raw"
    data_base64: Optional[str] = Field(
        default=None,
        description="Base64-encoded bytes (use when encoding=base64)",
    )
    uri: Optional[str] = Field(
        default=None,
        description="Remote or local URI (use when encoding=uri)",
    )
    data_text: Optional[str] = Field(
        default=None,
        description="Plain text content (use when kind=text and encoding=raw)",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Modality-specific metadata (dimensions, duration, sample rate, etc.)",
    )


class AlertActionRequest(BaseModel):
    """
    Generic alert action dispatch request.

    The caller (e.g. live-video-alert-agent, an audio sensor pipeline, or any
    other detection service) posts this when an alert fires.  The service runs
    the configured tools via ADK (LLM-reasoned) or rule-based dispatch and
    fans out SSE events.

    Example — image alert (base64 JPEG):
    {
      "source_id": "cam-01",
      "alert_name": "Fire Detection",
      "answer": "YES",
      "reason": "Visible flames in upper-right quadrant",
      "tools": ["log_alert", "capture_snapshot", "trigger_webhook"],
      "payloads": [
        {
          "kind": "image",
          "mime_type": "image/jpeg",
          "encoding": "base64",
          "data_base64": "<base64-encoded-jpeg>",
          "metadata": {"width": 1920, "height": 1080}
        }
      ]
    }

    Example — audio alert (URI):
    {
      "source_id": "mic-lobby",
      "alert_name": "Glass Break",
      "answer": "YES",
      "reason": "High-frequency impact detected at 2.3 kHz",
      "tools": ["log_alert", "publish_mqtt"],
      "payloads": [
        {
          "kind": "audio",
          "mime_type": "audio/wav",
          "encoding": "uri",
          "uri": "s3://alerts/mic-lobby/20260602_142301.wav",
          "metadata": {"duration_ms": 2500, "sample_rate": 44100}
        }
      ]
    }

    Example — text alert (no payload):
    {
      "source_id": "sensor-42",
      "alert_name": "Temperature Threshold",
      "answer": "YES",
      "reason": "CPU temperature exceeded 90°C",
      "tools": ["log_alert", "trigger_webhook"]
    }
    """

    event_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        description="Unique event identifier for idempotency tracking",
    )
    source_id: str = Field(
        ...,
        description="Identifier of the originating source (camera ID, sensor ID, device ID, etc.)",
    )
    alert_name: str = Field(
        ...,
        description="Name of the triggered alert (matches alert config)",
    )
    answer: Literal["YES", "NO"] = Field(
        default="YES",
        description="Detection result — tools only execute when answer=YES",
    )
    reason: str = Field(
        default="",
        description="Human-readable explanation of the detection",
    )
    consecutive_count: int = Field(
        default=1,
        ge=1,
        description="Number of consecutive YES detections (used for escalation logic)",
    )
    escalated: bool = Field(
        default=False,
        description="Whether escalation threshold has been reached",
    )
    tools: List[str] = Field(
        default_factory=lambda: ["log_alert"],
        description="Ordered list of tool names to invoke",
    )
    tool_arguments: Dict[str, dict] = Field(
        default_factory=dict,
        description="Per-tool keyword argument overrides; supports {{variable}} placeholders",
    )
    escalation: Optional[EscalationConfig] = Field(
        default=None,
        description="Escalation rule — extra tools added when consecutive threshold is reached",
    )
    payloads: List[Payload] = Field(
        default_factory=list,
        description="Ordered list of media artifacts (text, image, audio, video, binary)",
    )
    alert_type: Optional[str] = Field(
        default=None,
        description="Backward-compat alert type identifier; used for subscription config lookup",
    )
    dedup: Optional[DedupConfig] = Field(
        default=None,
        description="Per-request dedup config; if absent, falls back to subscription config dedup",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata from the incoming alert (preserved for dedup and delivery)",
    )


class AlertActionResponse(BaseModel):
    """Response returned by POST /api/v1/actions/execute."""

    event_id: str
    source_id: str
    alert_name: str
    actions_taken: List[str] = Field(
        description="Names of tools that completed successfully",
    )
    snapshot_path: Optional[str] = Field(
        default=None,
        description="Absolute path to saved snapshot (if capture_snapshot ran)",
    )
    duration_ms: float = Field(description="Total dispatch duration in milliseconds")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc),
    )


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    adk_enabled: bool
    mcp_enabled: bool
    uptime_seconds: float
    timestamp: datetime


class ToolInvokeRequest(BaseModel):
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Keyword arguments passed directly to the selected tool. "
            "Required keys depend on the tool_name path parameter."
        ),
    )


class ToolInvokeResponse(BaseModel):
    tool: str
    status: Literal["success", "error"]
    result: Any
    duration_ms: float
