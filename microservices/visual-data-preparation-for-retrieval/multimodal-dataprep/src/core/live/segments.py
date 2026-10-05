# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Wall-clock segment bucketing shared by the live recorder and the embedding pipeline.

A live stream is recorded as a series of fixed-length video segments so that a
retrieval hit on a live frame has something playable. The embedding pipeline and
the recorder run independently (separate threads, separate connections), so they
must agree on which segment a given instant belongs to *without* coordinating.

They do that by bucketing absolute epoch time: a segment starts at
``floor(now / duration) * duration``. Both sides derive the same identifier and
object name from a timestamp alone, so embeddings reference the correct segment
with no shared state.

The trade-off is a possible one-segment skew for a frame embedded within a few
milliseconds of a boundary; that is acceptable for playback and avoids
serializing the two paths.
"""

from __future__ import annotations

import time
from typing import Optional

#: Storage prefix (under a stream's directory) holding recorded segments.
SEGMENT_PREFIX = "segments"

#: Storage prefix (under a stream's directory) holding sampled frames.
FRAME_PREFIX = "frames"


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


def frame_object_name(stream_id: str, start_epoch: float, frame_number: int) -> str:
    """Return the storage object name of a sampled frame."""
    return f"{stream_id}/{FRAME_PREFIX}/{int(start_epoch)}_{int(frame_number):09d}.jpg"
