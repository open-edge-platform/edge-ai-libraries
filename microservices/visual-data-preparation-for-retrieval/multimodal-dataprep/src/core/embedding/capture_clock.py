# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Derive a frame's *capture* time rather than its arrival time.

``time.time()`` at the moment a frame finishes decoding answers "when did we
process this?", not "when did the camera see this?". The two differ by the
network, jitter-buffer and decode latency — typically 100 ms to a couple of
seconds, and variable. That is far too coarse to pick a specific frame out of
media recorded by a *different* service from its own connection to the same
camera.

The fix is to stop measuring our own arrival time and instead read the camera's
clock, which both consumers can derive identically:

* RTP packets carry a 90 kHz media timestamp with a random per-session origin,
  so on its own it is relative and meaningless in absolute terms.
* RTCP Sender Reports periodically publish the mapping from that media clock to
  the sender's NTP wall clock. FFmpeg folds this into
  ``AVFormatContext.start_time_realtime``.

One report anchors the whole timeline; every frame is then interpolated from its
own PTS. Advancing by PTS also removes per-frame scheduling jitter, because the
spacing comes from the media clock instead of from when our thread happened to
run.

Cheap cameras frequently omit Sender Reports or send an unsynchronised clock, so
the anchor is validated and the source degrades through three tiers. The tier is
recorded alongside the timestamp so consumers know what tolerance to apply.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any, Callable, Optional, Tuple

logger = logging.getLogger(__name__)

#: Reject an RTCP anchor outside this window. Unsynchronised cameras commonly
#: report 1970 (zero clock) or a wrapped NTP era, and a wrong anchor is worse
#: than an honest estimate because it looks authoritative.
_MIN_PLAUSIBLE_EPOCH = 1577836800.0  # 2020-01-01T00:00:00Z
_MAX_ANCHOR_SKEW_SECONDS = 86400.0  # tolerate a day ahead of our own clock


class CaptureTimeSource(str, Enum):
    """How a capture timestamp was obtained, in descending order of trust."""

    #: Anchored to the camera's NTP clock via an RTCP Sender Report. Two
    #: independent receivers derive the same instant for the same frame.
    RTCP_SENDER_REPORT = "rtcp_sender_report"

    #: No usable Sender Report. Anchored to our wall clock at session start and
    #: advanced by PTS: free of per-frame jitter, but offset by however long the
    #: first frame took to reach us.
    STREAM_ANCHORED = "stream_anchored"

    #: No usable PTS either. The ingest instant, carrying full pipeline latency.
    INGEST_ESTIMATED = "ingest_estimated"


class CaptureClock:
    """Maps frames to capture times for one video stream.

    The anchor is resolved once, on the first frame, and reused. Instances are
    single-stream and not thread-safe; the decoder creates one per stream and
    only the decode loop touches it.
    """

    def __init__(
        self,
        container: Any = None,
        stream: Any = None,
        now: Callable[[], float] = time.time,
        stream_id: Optional[int] = None,
    ) -> None:
        self._container = container
        self._stream = stream
        self._now = now
        self._stream_id = stream_id

        self._anchor_epoch: Optional[float] = None
        self._anchor_pts: Optional[int] = None
        self._time_base: Optional[float] = None
        self._source = CaptureTimeSource.INGEST_ESTIMATED
        self._resolved = False

    @property
    def source(self) -> CaptureTimeSource:
        """The tier in use. Only meaningful after the first frame."""
        return self._source

    def _realtime_anchor(self) -> Optional[float]:
        """Epoch seconds from the RTCP-derived anchor, when trustworthy."""
        raw = getattr(self._container, "start_time_realtime", None)
        if raw is None:
            return None

        try:
            epoch = float(raw) / 1_000_000.0  # FFmpeg reports microseconds
        except (TypeError, ValueError):
            return None

        # A camera with an unset or wrapped clock reports a wildly wrong time.
        # Such an anchor would silently offset every frame, so refuse it and let
        # the caller fall back to a tier that is honest about its accuracy.
        if epoch < _MIN_PLAUSIBLE_EPOCH:
            logger.warning(
                "[CAPTURE CLOCK] Stream %s reported an implausible RTCP anchor (%.3f); "
                "the camera clock is likely unsynchronised. Falling back to stream anchoring.",
                self._stream_id,
                epoch,
            )
            return None

        if epoch > self._now() + _MAX_ANCHOR_SKEW_SECONDS:
            logger.warning(
                "[CAPTURE CLOCK] Stream %s reported an RTCP anchor %.0fs in the future; "
                "refusing it and falling back to stream anchoring.",
                self._stream_id,
                epoch - self._now(),
            )
            return None

        return epoch

    def _resolve_time_base(self) -> Optional[float]:
        raw = getattr(self._stream, "time_base", None)
        if raw is None:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    def _stream_start_pts(self, frame_pts: int) -> int:
        """PTS the container considers the origin of the stream."""
        start = getattr(self._stream, "start_time", None)
        if start is None:
            return frame_pts
        try:
            return int(start)
        except (TypeError, ValueError):
            return frame_pts

    def _resolve(self, frame: Any) -> None:
        """Pick the best available anchor. Called once, on the first frame."""
        self._resolved = True

        pts = getattr(frame, "pts", None)
        self._time_base = self._resolve_time_base()

        if pts is None or self._time_base is None:
            # Without a usable media clock there is nothing to interpolate from.
            self._source = CaptureTimeSource.INGEST_ESTIMATED
            return

        realtime = self._realtime_anchor()
        if realtime is not None:
            # start_time_realtime corresponds to the stream's PTS origin, which
            # is not necessarily the first frame we happened to receive.
            self._anchor_pts = self._stream_start_pts(int(pts))
            self._anchor_epoch = realtime
            self._source = CaptureTimeSource.RTCP_SENDER_REPORT
            logger.info(
                "[CAPTURE CLOCK] Stream %s anchored to the camera clock via RTCP "
                "(anchor=%.3f); capture times are comparable across services.",
                self._stream_id,
                realtime,
            )
            return

        self._anchor_pts = int(pts)
        self._anchor_epoch = self._now()
        self._source = CaptureTimeSource.STREAM_ANCHORED
        logger.info(
            "[CAPTURE CLOCK] Stream %s has no usable RTCP Sender Report; anchoring to the "
            "local clock and advancing by PTS. Capture times carry a constant connection "
            "offset and must be matched with a tolerance window.",
            self._stream_id,
        )

    def capture_epoch(self, frame: Any) -> Tuple[float, str]:
        """Return ``(epoch_seconds, source)`` for ``frame``."""
        if not self._resolved:
            try:
                self._resolve(frame)
            except Exception:  # pragma: no cover - defensive
                logger.warning(
                    "[CAPTURE CLOCK] Stream %s failed to resolve a capture anchor; "
                    "falling back to ingest time.",
                    self._stream_id,
                    exc_info=True,
                )
                self._source = CaptureTimeSource.INGEST_ESTIMATED

        if self._source is CaptureTimeSource.INGEST_ESTIMATED:
            return self._now(), self._source.value

        pts = getattr(frame, "pts", None)
        if pts is None or self._anchor_epoch is None or self._time_base is None:
            # An individual frame may lack a PTS even on an anchored stream;
            # degrade just this frame rather than the whole stream.
            return self._now(), CaptureTimeSource.INGEST_ESTIMATED.value

        anchor_pts = self._anchor_pts if self._anchor_pts is not None else int(pts)
        offset = (int(pts) - anchor_pts) * self._time_base
        return self._anchor_epoch + offset, self._source.value
