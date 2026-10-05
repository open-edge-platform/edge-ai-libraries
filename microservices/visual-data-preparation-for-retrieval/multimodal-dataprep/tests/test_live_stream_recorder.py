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

    def __init__(self, *, keyframe: bool = True, frames: int = 1) -> None:
        self.dts = 0
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
