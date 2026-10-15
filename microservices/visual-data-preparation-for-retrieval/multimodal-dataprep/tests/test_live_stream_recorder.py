# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the live-stream segment sink.

The recorder is now a :class:`SegmentMuxSink`: it does not open its own camera
connection, it receives demuxed packets from the embedding pipeline's single
decode connection via :meth:`submit`. These tests cover the behaviours that are
easy to break silently:

* the PyAV remux-stream API (which differs across versions),
* per-segment DTS/PTS rebasing (or the browser's end time jumps on play),
* the PTS-anchored segment lookup that keeps playback seek drift-free.
"""

import queue
import threading
from typing import Any, List

import pytest

from src.common import settings
from src.core.live import recorder as recorder_module
from src.core.live.recorder import SegmentMuxSink


class FakePacket:
    """Minimal stand-in for an ``av.Packet``."""

    def __init__(self, *, keyframe: bool = True, dts: int = 0) -> None:
        self.dts = dts
        self.pts = dts
        self.is_keyframe = keyframe
        self.stream = "input-stream"


def _sink(**overrides) -> SegmentMuxSink:
    params = {
        "stream_id": "abc",
        "stream_url": "rtsp://cam/stream",
        "bucket_name": "live-streams",
        "shutdown_event": threading.Event(),
    }
    params.update(overrides)
    return SegmentMuxSink(**params)


# --------------------------------------------------------------------------
# PyAV compatibility
# --------------------------------------------------------------------------
def test_remux_stream_prefers_the_modern_pyav_api():
    calls = {}

    class Modern:
        def add_stream_from_template(self, template):
            calls["template"] = template
            return "out-stream"

        def add_stream(self, **kwargs):  # pragma: no cover - must not be used
            raise AssertionError("the legacy API must not be preferred")

    assert SegmentMuxSink._add_remux_stream(Modern(), "in-stream") == "out-stream"
    assert calls["template"] == "in-stream"


def test_remux_stream_falls_back_to_the_legacy_pyav_api():
    class Legacy:
        def add_stream(self, template=None):
            return f"out-of-{template}"

    assert SegmentMuxSink._add_remux_stream(Legacy(), "in") == "out-of-in"


def test_remux_stream_against_the_installed_pyav():
    """Guard against a PyAV upgrade silently disabling segment recording."""
    av = pytest.importorskip("av")
    import io

    buffer = io.BytesIO()
    source = av.open(io.BytesIO(), mode="w", format="mp4")
    in_stream = source.add_stream("h264", rate=30)
    out = av.open(buffer, mode="w", format="mp4")
    try:
        assert SegmentMuxSink._add_remux_stream(out, in_stream) is not None
    finally:
        for container in (out, source):
            try:
                container.close()
            except Exception:  # noqa: BLE001 - cleanup only
                pass


# --------------------------------------------------------------------------
# submit / backpressure
# --------------------------------------------------------------------------
def test_submit_is_non_blocking_and_drops_on_a_full_queue():
    """A saturated queue must drop packets (degrading recording) rather than
    stall the decode loop that feeds embedding."""
    sink = _sink()
    sink.store_segments = True
    # Pretend the drain thread is running so submit enqueues instead of no-oping.
    sink._thread = threading.Thread(target=lambda: None)
    sink._queue = queue.Queue(maxsize=2)

    for _ in range(10):
        sink.submit(FakePacket(), 0.0)

    assert sink._queue.qsize() == 2
    assert sink._dropped_packets == 8


def test_submit_is_a_noop_before_start():
    sink = _sink()
    sink.store_segments = True
    # No drain thread yet -> submit must not raise or enqueue.
    sink.submit(FakePacket(), 0.0)
    assert sink._queue.qsize() == 0


# --------------------------------------------------------------------------
# draining / muxing
# --------------------------------------------------------------------------
def _drive_drain(sink: SegmentMuxSink, fake_av, packets_with_pts) -> None:
    """Pre-fill the queue and run one synchronous drain pass."""
    for item in packets_with_pts:
        sink._queue.put_nowait(item)
    sink._queue.put_nowait(recorder_module._CLOSE_SENTINEL)

    import sys

    original = sys.modules.get("av")
    sys.modules["av"] = fake_av
    try:
        sink._drain_loop()
    finally:
        if original is not None:
            sys.modules["av"] = original
        else:  # pragma: no cover - av is normally importable in tests
            sys.modules.pop("av", None)


def test_segments_are_rebased_to_start_at_zero(monkeypatch):
    """A segment cut 40s into the stream must still open at DTS/PTS 0, or the
    MP4 duration spans the offset and the browser's end time jumps on play."""
    sink = _sink()
    sink.store_segments = True
    monkeypatch.setattr(sink, "_put_object", lambda name, payload: True)
    # Pin every packet into one wall-clock bucket so they share a segment.
    monkeypatch.setattr(recorder_module, "segment_start", lambda *a, **k: 100.0)

    muxed_dts: List[int] = []
    muxed_pts: List[int] = []

    class FakeOutContainer:
        def __init__(self, buffer) -> None:
            self._buffer = buffer

        def add_stream_from_template(self, template):
            return "out-stream"

        def mux(self, pkt):
            muxed_dts.append(pkt.dts)
            muxed_pts.append(pkt.pts)

        def close(self):
            # A real mux writes the container bytes; flush() only stores a
            # segment when the payload is non-empty.
            self._buffer.write(b"\x00mp4-bytes")

    class FakeAv:
        @staticmethod
        def open(buffer, *args, **kwargs):
            return FakeOutContainer(buffer)

    # Packets arrive carrying the source's running timestamps (base 4000).
    packets = [
        (FakePacket(keyframe=True, dts=4000), 40.0),
        (FakePacket(keyframe=False, dts=4010), 40.1),
        (FakePacket(keyframe=False, dts=4020), 40.2),
    ]
    _drive_drain(sink, FakeAv, packets)

    assert muxed_dts == [0, 10, 20]
    assert muxed_pts == [0, 10, 20]
    assert sink.stats.segments_stored == 1
    # The segment is anchored at (wall_start, first_packet_pts) for seek math.
    assert sink._segments == [(100.0, 40.0)]


def test_segment_recording_is_disabled_when_the_source_cannot_be_remuxed(monkeypatch):
    sink = _sink()
    sink.store_segments = True
    monkeypatch.setattr(recorder_module, "segment_start", lambda *a, **k: 0.0)

    class FakeAv:
        @staticmethod
        def open(*args, **kwargs):
            raise RuntimeError("unsupported codec")

    _drive_drain(sink, FakeAv, [(FakePacket(dts=0), 0.0)])

    # Degraded, not failed: ingestion keeps running without playback media.
    assert sink.store_segments is False
    assert sink.stats.segments_stored == 0


def test_packets_without_a_timestamp_are_skipped():
    sink = _sink()
    sink.store_segments = True
    opened: List[Any] = []

    class FakeAv:
        @staticmethod
        def open(*args, **kwargs):  # pragma: no cover - must not be called
            opened.append(True)
            raise AssertionError("a packet without DTS must not open a segment")

    packet = FakePacket()
    packet.dts = None
    _drive_drain(sink, FakeAv, [(packet, None)])
    assert opened == []


# --------------------------------------------------------------------------
# PTS-anchored segment lookup (drift-free seek)
# --------------------------------------------------------------------------
def test_resolve_segment_maps_frames_to_the_covering_segment():
    """A frame must resolve to the segment that *contains* it, returning that
    segment's (wall_start, first_packet_pts) so the seek is an exact PTS delta,
    even when the GOP is longer than the segment duration."""
    sink = _sink()

    # No segment opened yet -> caller falls back to wall-clock bucketing.
    assert sink.resolve_segment(25.0) is None

    # Keyframes landed at wall buckets 0 and 40, anchored at pts 100 and 140.
    sink._record_segment(0.0, 100.0)
    sink._record_segment(40.0, 140.0)

    # A frame at media_pts=125 belongs to the segment anchored at pts 100.
    assert sink.resolve_segment(125.0) == (0.0, 100.0)
    assert sink.resolve_segment(105.0) == (0.0, 100.0)
    assert sink.resolve_segment(140.0) == (40.0, 140.0)
    assert sink.resolve_segment(200.0) == (40.0, 140.0)
    # A frame just before the first segment anchors to the earliest one.
    assert sink.resolve_segment(50.0) == (0.0, 100.0)
    # A missing pts cannot be resolved.
    assert sink.resolve_segment(None) is None


def test_record_segment_ignores_regressions_and_missing_pts():
    sink = _sink()
    sink._record_segment(0.0, 100.0)
    sink._record_segment(0.0, 100.0)  # duplicate wall_start
    sink._record_segment(-5.0, 90.0)  # out-of-order wall_start
    sink._record_segment(10.0, None)  # no pts anchor -> not recordable
    sink._record_segment(10.0, 110.0)
    assert sink._segments == [(0.0, 100.0), (10.0, 110.0)]


# --------------------------------------------------------------------------
# config / safety
# --------------------------------------------------------------------------
def test_sink_defaults_come_from_settings():
    sink = _sink()
    assert sink.segment_duration == settings.LIVE_SEGMENT_DURATION_SECONDS
    assert sink.store_segments == settings.LIVE_STORE_SEGMENTS
    # Credentials must never appear in recorder logging.
    sink = _sink(stream_url="rtsp://user:s3cr3t@cam/stream")
    assert "s3cr3t" not in sink._redacted_url


def test_put_object_applies_public_read_policy_once():
    """Recorded media is browser-played straight from the object store, so the
    bucket must get the same anonymous read policy as the uploaded-video bucket
    (otherwise MinIO answers 403). The policy is set once per sink."""

    class RecordingStorage:
        def __init__(self) -> None:
            self.ensured: List[str] = []
            self.public: List[str] = []
            self.uploaded: List[str] = []

        def ensure_bucket_exists(self, bucket_name: str) -> None:
            self.ensured.append(bucket_name)

        def ensure_public_read(self, bucket_name: str) -> None:
            self.public.append(bucket_name)

        def upload_video(self, bucket, name, stream, length):  # noqa: ANN001
            self.uploaded.append(name)

    storage = RecordingStorage()
    sink = _sink(storage=storage)

    assert sink._put_object("abc/segments/1.mp4", b"data") is True
    assert sink._put_object("abc/segments/2.mp4", b"data") is True

    assert storage.public == ["live-streams"]  # set exactly once
    assert storage.ensured == ["live-streams"]
    assert storage.uploaded == ["abc/segments/1.mp4", "abc/segments/2.mp4"]
