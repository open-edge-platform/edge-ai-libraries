# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the live-stream playback recorder.

These cover the two behaviours that are easy to break silently: the PyAV
remux-stream API (which differs across versions) and the fact that muxing a
packet rebinds it, so frames must be sampled first.
"""

import threading
from typing import Any, List

import pytest

from src.common import settings
from src.core.live.recorder import LiveMediaRecorder


class FakePacket:
    """Minimal stand-in for an ``av.Packet``."""

    def __init__(self, *, keyframe: bool = True, frames: int = 1, dts: int = 0) -> None:
        self.dts = dts
        self.pts = dts
        self.is_keyframe = keyframe
        self.stream = "input-stream"
        self._frames = frames
        self.decoded_with_stream: List[Any] = []

    def decode(self):
        # A real packet can only be decoded while bound to its input stream.
        self.decoded_with_stream.append(self.stream)
        if self.stream != "input-stream":
            raise RuntimeError("packet was rebound before decoding")
        return [object() for _ in range(self._frames)]


def _recorder(**overrides) -> LiveMediaRecorder:
    params = {
        "stream_id": "abc",
        "stream_url": "rtsp://cam/stream",
        "bucket_name": "live-streams",
        "shutdown_event": threading.Event(),
        "frame_interval": 1,
    }
    params.update(overrides)
    return LiveMediaRecorder(**params)


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

    assert LiveMediaRecorder._add_remux_stream(Modern(), "in-stream") == "out-stream"
    assert calls["template"] == "in-stream"


def test_remux_stream_falls_back_to_the_legacy_pyav_api():
    class Legacy:
        def add_stream(self, template=None):
            return f"out-of-{template}"

    assert LiveMediaRecorder._add_remux_stream(Legacy(), "in") == "out-of-in"


def test_remux_stream_against_the_installed_pyav():
    """Guard against a PyAV upgrade silently disabling segment recording."""
    av = pytest.importorskip("av")
    import io

    buffer = io.BytesIO()
    source = av.open(io.BytesIO(), mode="w", format="mp4")
    in_stream = source.add_stream("h264", rate=30)
    out = av.open(buffer, mode="w", format="mp4")
    try:
        assert LiveMediaRecorder._add_remux_stream(out, in_stream) is not None
    finally:
        for container in (out, source):
            try:
                container.close()
            except Exception:  # noqa: BLE001 - cleanup only
                pass


# --------------------------------------------------------------------------
# Packet ordering
# --------------------------------------------------------------------------
def test_frames_are_sampled_before_the_packet_is_muxed(monkeypatch):
    """Muxing rebinds ``packet.stream``; decoding afterwards yields nothing."""
    stored: List[int] = []
    recorder = _recorder()
    recorder.store_segments = True
    recorder.store_frames = True
    monkeypatch.setattr(recorder, "_store_frame", lambda frame, n: stored.append(n))
    monkeypatch.setattr(recorder, "_put_object", lambda name, payload: True)

    packet = FakePacket()
    muxed: List[Any] = []

    class FakeOutContainer:
        def add_stream_from_template(self, template):
            return "out-stream"

        def mux(self, pkt):
            muxed.append(pkt.stream)

        def close(self):
            pass

    class FakeAv:
        @staticmethod
        def open(*args, **kwargs):
            return FakeOutContainer()

    class FakeContainer:
        def demux(self, _stream):
            yield packet

    recorder._record_loop(FakeAv, FakeContainer(), "in-stream")

    assert stored == [0]
    # The decode happened while the packet was still bound to the input stream.
    assert packet.decoded_with_stream == ["input-stream"]
    assert muxed == ["out-stream"]


def test_segment_recording_is_disabled_when_the_source_cannot_be_remuxed(monkeypatch):
    recorder = _recorder()
    recorder.store_segments = True
    recorder.store_frames = False

    class FakeAv:
        @staticmethod
        def open(*args, **kwargs):
            raise RuntimeError("unsupported codec")

    class FakeContainer:
        def demux(self, _stream):
            yield FakePacket()

    recorder._record_loop(FakeAv, FakeContainer(), "in-stream")

    # Degraded, not failed: ingestion keeps running without playback media.
    assert recorder.store_segments is False
    assert recorder.stats.segments_stored == 0


def test_packets_without_a_timestamp_are_skipped(monkeypatch):
    recorder = _recorder()
    recorder.store_segments = False
    recorder.store_frames = True
    monkeypatch.setattr(recorder, "_store_frame", lambda frame, n: pytest.fail("should not decode"))

    packet = FakePacket()
    packet.dts = None

    class FakeContainer:
        def demux(self, _stream):
            yield packet

    recorder._record_loop(None, FakeContainer(), "in-stream")
    assert packet.decoded_with_stream == []


def test_recorder_defaults_come_from_settings():
    recorder = _recorder()
    assert recorder.segment_duration == settings.LIVE_SEGMENT_DURATION_SECONDS
    assert recorder.store_segments == settings.LIVE_STORE_SEGMENTS
    assert recorder.store_frames == settings.LIVE_STORE_FRAMES
    # Credentials must never appear in recorder logging.
    recorder = _recorder(stream_url="rtsp://admin:s3cr3t@cam/stream")
    assert "s3cr3t" not in recorder._redacted_url


def test_put_object_applies_public_read_policy_once():
    """Recorded media is browser-played straight from the object store, so the
    bucket must get the same anonymous read policy as the uploaded-video bucket
    (otherwise MinIO answers 403). The policy is set once per recorder."""

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
    recorder = _recorder(storage=storage)

    assert recorder._put_object("abc/segments/1.mp4", b"data") is True
    assert recorder._put_object("abc/segments/2.mp4", b"data") is True

    assert storage.public == ["live-streams"]  # set exactly once
    assert storage.ensured == ["live-streams"]
    assert storage.uploaded == ["abc/segments/1.mp4", "abc/segments/2.mp4"]


def test_frame_uploads_run_through_a_bounded_pool():
    """Sampled frames are uploaded via a bounded worker pool so the decode loop
    is not blocked on per-object storage latency. Every submitted frame must be
    uploaded exactly once and counted once the pool is drained."""
    uploaded: List[str] = []
    upload_lock = threading.Lock()

    def fake_put(name, payload):
        with upload_lock:
            uploaded.append(name)
        return True

    recorder = _recorder(frame_upload_workers=4)
    recorder._put_object = fake_put  # type: ignore[assignment]

    names = [f"abc/frames/{i}.jpg" for i in range(50)]
    for name in names:
        recorder._submit_frame_upload(name, b"payload")

    # Draining the pool must wait for every in-flight upload to finish.
    recorder._shutdown_frame_pool()

    assert sorted(uploaded) == sorted(names)
    assert recorder.stats.frames_stored == 50
    # Pool is disposed; a subsequent recording session re-creates it lazily.
    assert recorder._frame_pool is None


def test_frame_upload_pool_respects_worker_setting(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_FRAME_UPLOAD_WORKERS", 7)
    recorder = _recorder(frame_upload_workers=None)
    assert recorder.frame_upload_workers == 7
    recorder = _recorder(frame_upload_workers=3)
    assert recorder.frame_upload_workers == 3


def test_segments_are_rebased_to_start_at_zero(monkeypatch):
    """A segment cut 40s into the stream must still open at DTS/PTS 0, or the
    MP4 duration spans the offset and the browser's end time jumps on play."""
    recorder = _recorder()
    recorder.store_segments = True
    recorder.store_frames = False
    monkeypatch.setattr(recorder, "_put_object", lambda name, payload: True)

    # Packets arrive carrying the source's running timestamps (base 4000).
    packets = [
        FakePacket(keyframe=True, dts=4000),
        FakePacket(keyframe=False, dts=4010),
        FakePacket(keyframe=False, dts=4020),
    ]
    muxed_dts: List[int] = []
    muxed_pts: List[int] = []

    class FakeOutContainer:
        def add_stream_from_template(self, template):
            return "out-stream"

        def mux(self, pkt):
            muxed_dts.append(pkt.dts)
            muxed_pts.append(pkt.pts)

        def close(self):
            pass

    class FakeAv:
        @staticmethod
        def open(*args, **kwargs):
            return FakeOutContainer()

    class FakeContainer:
        def demux(self, _stream):
            yield from packets

    recorder._record_loop(FakeAv, FakeContainer(), "in-stream")

    # First packet anchors the segment at 0; the rest keep their relative spacing.
    assert muxed_dts == [0, 10, 20]
    assert muxed_pts == [0, 10, 20]


def test_resolve_segment_start_maps_frames_to_the_covering_segment():
    """A frame must resolve to the segment that *contains* it, even when the
    GOP is longer than the segment duration so segments span multiple buckets."""
    recorder = _recorder()

    # No segment opened yet -> caller falls back to time-bucketing.
    assert recorder.resolve_segment_start(25.0) is None

    # Keyframes landed at buckets 0 and 40 (GOP ~40s, segment duration 10s).
    recorder._record_segment_start(0.0)
    recorder._record_segment_start(40.0)

    # A frame at t=25 belongs to the segment that opened at 0 (it covers 0..40),
    # not bucket 20 - which was never written.
    assert recorder.resolve_segment_start(25.0) == 0.0
    assert recorder.resolve_segment_start(5.0) == 0.0
    assert recorder.resolve_segment_start(40.0) == 40.0
    assert recorder.resolve_segment_start(100.0) == 40.0
    # A frame just before the first segment anchors to the earliest one.
    assert recorder.resolve_segment_start(-5.0) == 0.0


def test_record_segment_start_ignores_duplicates_and_regressions():
    recorder = _recorder()
    recorder._record_segment_start(10.0)
    recorder._record_segment_start(10.0)  # duplicate
    recorder._record_segment_start(5.0)  # out-of-order/regression
    recorder._record_segment_start(20.0)
    assert recorder._segment_starts == [10.0, 20.0]
