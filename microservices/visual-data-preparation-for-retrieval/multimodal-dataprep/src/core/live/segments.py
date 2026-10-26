# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Wall-clock segment naming shared by the live recorder and the embedding pipeline.

A live stream is recorded as a series of fixed-length video segments so that a
retrieval hit on a live frame has something playable. Segments are *named* by
wall-clock bucket: a segment starts at ``floor(now / duration) * duration``.
Deriving the object name from a timestamp alone keeps URLs and retention stable
and lets the retention sweeper reason about a segment's age from its name.

The embedding and the recorded segment now ride a *single* RTSP connection: the
decode loop tees every demuxed packet to the recorder (see
``core.embedding.decoder`` and ``core.live.recorder``). Because both the frame
and its segment come from one demux, the in-segment playback **seek** is a pure
presentation-timestamp delta (``frame_media_pts - segment_first_pts``) on a
shared clock and cannot drift. Only the segment *name* uses wall-clock bucketing;
the seek never does. The recorder maps a frame's ``media_pts`` back to its
covering segment via ``resolve_segment``.
"""

from __future__ import annotations

import time
from typing import Optional

#: Storage prefix (under a stream's directory) holding recorded segments.
SEGMENT_PREFIX = "segments"


def segment_start(epoch_seconds: Optional[float] = None, duration_seconds: int = 10) -> float:
    """Return the start of the segment bucket containing ``epoch_seconds``."""
    duration = max(1, int(duration_seconds))
    now = time.time() if epoch_seconds is None else float(epoch_seconds)
    return float(int(now // duration) * duration)


def segment_id(stream_id: str, start_epoch: float) -> str:
    """Return the stable identifier of a stream's segment."""
    return f"{stream_id}_{int(start_epoch)}"


def segment_object_name(stream_id: str, start_epoch: float) -> str:
    """Return the storage object name of a stream's segment."""
    return f"{stream_id}/{SEGMENT_PREFIX}/{int(start_epoch)}.mp4"
