# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for camera-clock derived capture timestamps.

The point of the capture clock is that two independent receivers of the same
RTSP feed derive the *same* instant for the *same* frame, which is what makes a
recording stored by another service correlatable with an embedding stored here.
"""

from fractions import Fraction
from unittest import mock

from src.core.embedding.capture_clock import CaptureClock, CaptureTimeSource

#: 2026-09-16T09:12:00Z, comfortably inside the plausible window.
ANCHOR_EPOCH = 1789643520.0
ANCHOR_REALTIME_US = int(ANCHOR_EPOCH * 1_000_000)


class _Frame:
    def __init__(self, pts):
        self.pts = pts


class _Stream:
    def __init__(self, time_base=Fraction(1, 90000), start_time=0):
        self.time_base = time_base
        self.start_time = start_time


class _Container:
    def __init__(self, start_time_realtime=None):
        self.start_time_realtime = start_time_realtime


def _clock(container, stream=None, now=None):
    return CaptureClock(
        container=container,
        stream=stream or _Stream(),
        now=now or (lambda: ANCHOR_EPOCH + 1.0),
        stream_id=0,
    )


class TestRtcpAnchoring:
    """The preferred tier: anchored to the camera's own NTP clock."""

    def test_uses_sender_report_anchor(self):
        clock = _clock(_Container(ANCHOR_REALTIME_US))

        epoch, source = clock.capture_epoch(_Frame(0))

        assert source == CaptureTimeSource.RTCP_SENDER_REPORT.value
        assert epoch == ANCHOR_EPOCH

    def test_advances_by_pts_not_by_wall_clock(self):
        """Frame spacing must come from the media clock, not our scheduler."""
        clock = _clock(_Container(ANCHOR_REALTIME_US))

        clock.capture_epoch(_Frame(0))
        # One second later on a 90 kHz media clock.
        epoch, _ = clock.capture_epoch(_Frame(90000))

        assert epoch == ANCHOR_EPOCH + 1.0

    def test_is_immune_to_ingest_jitter(self):
        """A slow consumer must not shift the reported capture time."""
        wall = [ANCHOR_EPOCH]
        clock = _clock(_Container(ANCHOR_REALTIME_US), now=lambda: wall[0])

        clock.capture_epoch(_Frame(0))
        wall[0] += 37.5  # pipeline stalled
        epoch, _ = clock.capture_epoch(_Frame(90000))

        assert epoch == ANCHOR_EPOCH + 1.0

    def test_two_receivers_agree_on_the_same_frame(self):
        """The property the whole design rests on.

        Each receiver anchors its own RTP timeline to the camera's NTP clock, so
        the per-session random PTS origin cancels out and both land on the same
        absolute instant.
        """
        # Receiver A: PTS origin 0, reads the frame at one wall-clock moment.
        a = CaptureClock(
            container=_Container(ANCHOR_REALTIME_US),
            stream=_Stream(start_time=0),
            now=lambda: ANCHOR_EPOCH + 0.2,
            stream_id=0,
        )
        # Receiver B: different random PTS origin, different arrival latency.
        offset = 4_500_000
        b = CaptureClock(
            container=_Container(ANCHOR_REALTIME_US),
            stream=_Stream(start_time=offset),
            now=lambda: ANCHOR_EPOCH + 1.9,
            stream_id=0,
        )

        a_epoch, _ = a.capture_epoch(_Frame(90000))
        b_epoch, _ = b.capture_epoch(_Frame(offset + 90000))

        assert a_epoch == b_epoch


class TestDegradedTiers:
    """Cheap cameras routinely omit or corrupt the Sender Report."""

    def test_no_sender_report_falls_back_to_stream_anchoring(self):
        clock = _clock(_Container(None))

        epoch, source = clock.capture_epoch(_Frame(0))

        assert source == CaptureTimeSource.STREAM_ANCHORED.value
        assert epoch == ANCHOR_EPOCH + 1.0

    def test_stream_anchored_still_advances_by_pts(self):
        clock = _clock(_Container(None))

        first, _ = clock.capture_epoch(_Frame(0))
        second, _ = clock.capture_epoch(_Frame(45000))

        assert second - first == 0.5

    def test_unset_camera_clock_is_rejected(self):
        """A 1970 anchor is wrong, and wrong-but-authoritative is the worst case."""
        clock = _clock(_Container(0))

        _, source = clock.capture_epoch(_Frame(0))

        assert source == CaptureTimeSource.STREAM_ANCHORED.value

    def test_absurdly_future_anchor_is_rejected(self):
        clock = _clock(_Container(int((ANCHOR_EPOCH + 90 * 86400) * 1_000_000)))

        _, source = clock.capture_epoch(_Frame(0))

        assert source == CaptureTimeSource.STREAM_ANCHORED.value

    def test_missing_pts_falls_back_to_ingest(self):
        clock = _clock(_Container(ANCHOR_REALTIME_US))

        epoch, source = clock.capture_epoch(_Frame(None))

        assert source == CaptureTimeSource.INGEST_ESTIMATED.value
        assert epoch == ANCHOR_EPOCH + 1.0

    def test_missing_time_base_falls_back_to_ingest(self):
        clock = _clock(_Container(ANCHOR_REALTIME_US), stream=_Stream(time_base=None))

        _, source = clock.capture_epoch(_Frame(0))

        assert source == CaptureTimeSource.INGEST_ESTIMATED.value

    def test_one_bad_frame_does_not_demote_the_stream(self):
        clock = _clock(_Container(ANCHOR_REALTIME_US))
        clock.capture_epoch(_Frame(0))

        _, bad = clock.capture_epoch(_Frame(None))
        epoch, good = clock.capture_epoch(_Frame(90000))

        assert bad == CaptureTimeSource.INGEST_ESTIMATED.value
        assert good == CaptureTimeSource.RTCP_SENDER_REPORT.value
        assert epoch == ANCHOR_EPOCH + 1.0

    def test_anchor_is_resolved_once(self):
        container = _Container(ANCHOR_REALTIME_US)
        clock = _clock(container)

        clock.capture_epoch(_Frame(0))
        # A later report must not silently re-anchor mid-stream.
        container.start_time_realtime = int((ANCHOR_EPOCH + 500) * 1_000_000)
        epoch, _ = clock.capture_epoch(_Frame(90000))

        assert epoch == ANCHOR_EPOCH + 1.0

    def test_resolution_failure_degrades_rather_than_raises(self):
        clock = _clock(_Container(ANCHOR_REALTIME_US))

        with mock.patch.object(clock, "_resolve", side_effect=RuntimeError("boom")):
            epoch, source = clock.capture_epoch(_Frame(0))

        assert source == CaptureTimeSource.INGEST_ESTIMATED.value
        assert epoch == ANCHOR_EPOCH + 1.0


class TestDecoderPropagation:
    """The decoder must carry capture data through to stored metadata."""

    def test_frame_metadata_carries_capture_fields(self):
        from src.core.embedding.decoder import FrameMetadata

        meta = FrameMetadata(
            stream_id=0,
            frame_id=15,
            shm="psm_x",
            shape="(1080, 1920, 3)",
            dtype="uint8",
            capture_epoch=ANCHOR_EPOCH,
            capture_time_source=CaptureTimeSource.RTCP_SENDER_REPORT.value,
        ).to_dict()

        assert meta["capture_epoch"] == ANCHOR_EPOCH
        assert meta["capture_time_source"] == CaptureTimeSource.RTCP_SENDER_REPORT.value

    def test_capture_fields_default_to_none_for_file_sources(self):
        from src.core.embedding.decoder import FrameMetadata

        meta = FrameMetadata(stream_id=0, frame_id=0, shm="psm_x", shape="(2, 2, 3)", dtype="uint8")

        assert meta.capture_epoch is None
        assert meta.capture_time_source is None
