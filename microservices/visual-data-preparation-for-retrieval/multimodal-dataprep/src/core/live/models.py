# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""The persisted representation of a live (RTSP) stream registration.

The registry is the control plane for live ingestion. A :class:`LiveStream`
record holds both the caller's intent (source, processing parameters, desired
state) and the worker's observed runtime counters, so the service can restore
streams after a restart and answer ``GET /media/streams`` without touching the
vector database.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from src.common import settings
from src.common.schema import LiveStreamInfo, LiveStreamStateEnum, LiveStreamStats
from src.core.live.urls import default_stream_name, redact_stream_url

# States in which a worker is actively (or attempting to) ingest, so uptime
# should track wall-clock. Any other state freezes the reported uptime.
_ACTIVE_STATES = frozenset(
    {
        LiveStreamStateEnum.starting,
        LiveStreamStateEnum.running,
        LiveStreamStateEnum.reconnecting,
    }
)


@dataclass
class LiveStreamStatsRecord:
    """Runtime counters maintained by a stream's worker."""

    frames_processed: int = 0
    embeddings_created: int = 0
    # Cumulative detect+embed+store compute time (seconds) spent producing the
    # embeddings above. Decode is excluded: for a live source the decode stage
    # blocks on real-time packet arrival, so its wall time is the inter-frame
    # wait, not device work. Dividing embeddings_created by this yields the rate
    # at which the device actually ingests while processing, instead of the
    # delivered rate diluted by the camera's real-time cadence.
    active_seconds: float = 0.0
    segments_stored: int = 0
    reconnect_count: int = 0
    last_frame_ts: Optional[float] = None
    started_ts: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return the counters as a plain dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "LiveStreamStatsRecord":
        """Rebuild counters from a persisted dict, ignoring unknown keys."""
        data = data or {}
        known = {f for f in cls.__dataclass_fields__}  # noqa: SLF001 - dataclass API
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class LiveStream:
    """A registered live stream.

    ``stream_url`` carries the credentialed URL needed to connect and is stored
    only here. Every externally visible representation goes through
    :meth:`to_info`, which redacts it.
    """

    stream_id: str
    stream_url: str
    stream_name: str
    frame_interval: int
    enable_object_detection: bool
    detection_confidence: float
    description: Optional[str] = None
    bucket_name: Optional[str] = None
    #: Stable logical identity of the physical source (camera/sensor), independent
    #: of who is currently ingesting it. ``stream_id`` is *our* registration
    #: handle and is not portable; ``sensor_id`` is the key an external stream
    #: manager files its recordings under, so it is what lets a stored clip be
    #: correlated back to an embedding. Defaults to ``stream_id`` when the caller
    #: does not supply one, which keeps single-service deployments unchanged.
    sensor_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    state: LiveStreamStateEnum = LiveStreamStateEnum.pending
    #: The state the stream should return to after a service restart.
    desired_state: LiveStreamStateEnum = LiveStreamStateEnum.running
    last_error: Optional[str] = None
    stats: LiveStreamStatsRecord = field(default_factory=LiveStreamStatsRecord)
    created_ts: float = field(default_factory=time.time)
    updated_ts: float = field(default_factory=time.time)
    #: Epoch at which the stream was deregistered while keeping its data. A
    #: tombstone is hidden from the API but kept so the retention sweeper can
    #: still age out the data the caller chose not to purge; it is dropped once
    #: that data is guaranteed past the retention window. ``None`` for a live
    #: registration.
    tombstoned_ts: Optional[float] = None

    @property
    def is_tombstone(self) -> bool:
        """True when this record is a deregistered stream kept only for sweeping."""
        return self.tombstoned_ts is not None

    @classmethod
    def new(
        cls,
        *,
        stream_url: str,
        frame_interval: Optional[int] = None,
        enable_object_detection: Optional[bool] = None,
        detection_confidence: Optional[float] = None,
        bucket_name: Optional[str] = None,
        stream_name: Optional[str] = None,
        description: Optional[str] = None,
        sensor_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        start: bool = True,
    ) -> "LiveStream":
        """Create a new registration with a generated ``stream_id``.

        Omitted processing parameters fall back to the service defaults.
        ``sensor_id`` defaults to the generated ``stream_id`` so that the field
        is always populated and downstream correlation never has to special-case
        a missing value.
        """
        stream_id = uuid.uuid4().hex
        return cls(
            stream_id=stream_id,
            stream_url=stream_url,
            stream_name=stream_name or default_stream_name(stream_url),
            description=description,
            sensor_id=sensor_id or stream_id,
            bucket_name=bucket_name or settings.LIVE_STREAM_BUCKET,
            frame_interval=int(
                frame_interval if frame_interval is not None else settings.FRAME_INTERVAL
            ),
            enable_object_detection=bool(
                enable_object_detection
                if enable_object_detection is not None
                else settings.ENABLE_OBJECT_DETECTION
            ),
            detection_confidence=float(
                detection_confidence
                if detection_confidence is not None
                else settings.DETECTION_CONFIDENCE
            ),
            tags=list(tags or []),
            state=LiveStreamStateEnum.pending,
            desired_state=(LiveStreamStateEnum.running if start else LiveStreamStateEnum.paused),
        )

    @property
    def redacted_url(self) -> str:
        """The source URL with credentials stripped."""
        return redact_stream_url(self.stream_url)

    @property
    def effective_sensor_id(self) -> str:
        """The source identity to correlate external media against.

        Falls back to ``stream_id`` so callers never have to handle ``None``.
        """
        return self.sensor_id or self.stream_id

    def uptime_seconds(self) -> Optional[float]:
        """Seconds the current session has been up, frozen while not ingesting.

        While the stream is actively ingesting the value tracks wall-clock. In
        any non-active state (notably ``paused``, but also ``stopped``/``error``)
        it is frozen at the last processed frame so a paused stream's uptime does
        not keep climbing.
        """
        if not self.stats.started_ts:
            return None
        if self.state in _ACTIVE_STATES:
            return max(0.0, time.time() - self.stats.started_ts)
        ceiling = self.stats.last_frame_ts or self.stats.started_ts
        return max(0.0, ceiling - self.stats.started_ts)

    def to_info(self) -> LiveStreamInfo:
        """Project to the API-facing model, redacting the source URL."""
        return LiveStreamInfo(
            stream_id=self.stream_id,
            stream_url=self.redacted_url,
            stream_name=self.stream_name,
            description=self.description,
            state=self.state,
            bucket_name=self.bucket_name,
            video_id=self.stream_id,
            sensor_id=self.effective_sensor_id,
            frame_interval=self.frame_interval,
            enable_object_detection=self.enable_object_detection,
            detection_confidence=self.detection_confidence,
            tags=list(self.tags),
            stats=LiveStreamStats(
                **self.stats.to_dict(),
                uptime_seconds=self.uptime_seconds(),
            ),
            last_error=self.last_error,
            created_ts=self.created_ts,
            updated_ts=self.updated_ts,
        )

    def to_row(self) -> Dict[str, Any]:
        """Return a persistence-friendly dict (state enums flattened to str)."""
        return {
            "stream_id": self.stream_id,
            "stream_url": self.stream_url,
            "stream_name": self.stream_name,
            "description": self.description,
            "bucket_name": self.bucket_name,
            "sensor_id": self.sensor_id,
            "frame_interval": self.frame_interval,
            "enable_object_detection": self.enable_object_detection,
            "detection_confidence": self.detection_confidence,
            "tags": list(self.tags),
            "state": self.state.value,
            "desired_state": self.desired_state.value,
            "last_error": self.last_error,
            "stats": self.stats.to_dict(),
            "created_ts": self.created_ts,
            "updated_ts": self.updated_ts,
            "tombstoned_ts": self.tombstoned_ts,
        }

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "LiveStream":
        """Rebuild a record from its persisted dict form."""
        return cls(
            stream_id=row["stream_id"],
            stream_url=row["stream_url"],
            stream_name=row["stream_name"],
            description=row.get("description"),
            bucket_name=row.get("bucket_name"),
            # Registrations persisted before sensor_id existed fall back to the
            # stream_id, matching what ``new()`` would have assigned.
            sensor_id=row.get("sensor_id") or row["stream_id"],
            frame_interval=int(row["frame_interval"]),
            enable_object_detection=bool(row["enable_object_detection"]),
            detection_confidence=float(row["detection_confidence"]),
            tags=list(row.get("tags") or []),
            state=LiveStreamStateEnum(row.get("state") or LiveStreamStateEnum.pending.value),
            desired_state=LiveStreamStateEnum(
                row.get("desired_state") or LiveStreamStateEnum.running.value
            ),
            last_error=row.get("last_error"),
            stats=LiveStreamStatsRecord.from_dict(row.get("stats")),
            created_ts=float(row.get("created_ts") or time.time()),
            updated_ts=float(row.get("updated_ts") or time.time()),
            tombstoned_ts=row.get("tombstoned_ts"),
        )
