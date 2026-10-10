# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Batching behaviour for endless (live) sources.

A live RTSP source never reaches end-of-stream, so the decoder's "drain what is
left at EOF" path never runs. Without a time-based flush the pipeline only sees
frames once ``batch_size`` *sampled* frames have accumulated -- at a low sampling
rate that is minutes of latency, and it pins that many shared-memory blocks in
the meantime. These tests pin the flush timer down.
"""

from __future__ import annotations

import pytest

from src.core.embedding.decoder import (
    VideoFrameConfig,
    VideoInput,
    _redact_source_for_metadata,
    is_live_source,
)


class TestIsLiveSource:
    """Live detection must agree with ``VideoInput.auto_detect``."""

    @pytest.mark.parametrize(
        "url",
        ["rtsp://cam-1:554/live", "rtsps://cam-1:322/live", "rtsp://u:p@cam-1:554/live"],
    )
    def test_rtsp_urls_are_live(self, url):
        assert is_live_source(url) is True

    @pytest.mark.parametrize("source", ["/data/clip.mp4", "clip.mp4", b"\x00\x01raw-bytes"])
    def test_files_and_bytes_are_not_live(self, source):
        assert is_live_source(source) is False

    def test_list_is_live_when_any_member_is_rtsp(self):
        assert is_live_source(["/data/clip.mp4", "rtsp://cam-1:554/live"]) is True

    def test_list_of_files_is_not_live(self):
        assert is_live_source(["/data/a.mp4", "/data/b.mp4"]) is False

    def test_accepts_videoinput_instances(self):
        assert is_live_source([VideoInput.from_rtsp("rtsp://cam-1:554/live")]) is True
        assert is_live_source([VideoInput.from_bytes(b"x")]) is False

    def test_empty_list_is_not_live(self):
        assert is_live_source([]) is False


class TestVideoFrameConfigBatchAge:
    """The flush timer is opt-in and validated."""

    def test_defaults_to_disabled(self):
        # Finite sources must keep EOF-drain semantics, so the timer is off by default.
        assert VideoFrameConfig().max_batch_age_seconds == 0.0

    def test_accepts_a_positive_age(self):
        assert VideoFrameConfig(max_batch_age_seconds=10.0).max_batch_age_seconds == 10.0

    def test_rejects_a_negative_age(self):
        with pytest.raises(ValueError, match="max_batch_age_seconds must be >= 0"):
            VideoFrameConfig(max_batch_age_seconds=-1.0)

    def test_existing_validation_still_applies(self):
        # Guard against the new field displacing the original checks.
        with pytest.raises(ValueError, match="batch_size must be >= 1"):
            VideoFrameConfig(batch_size=0)
        with pytest.raises(ValueError, match="frame_interval must be >= 1"):
            VideoFrameConfig(frame_interval=0)
        with pytest.raises(ValueError, match="`frame_interval` must be 1"):
            VideoFrameConfig(keyframes_only=True, frame_interval=15)


class TestLiveBatchFlush:
    """A partially filled batch from an endless source is emitted on the timer."""

    def _run(self, monkeypatch, *, max_age, frame_count, batch_size=256):
        """Drive ``decode_stream_and_batch_generator`` over a synthetic stream.

        The clock is faked so the test is deterministic and instant: every decoded
        frame advances monotonic time by one second.
        """
        from src.core.embedding import decoder as decoder_mod

        clock = {"t": 0.0}
        monkeypatch.setattr(decoder_mod.time, "monotonic", lambda: clock["t"])

        frames = [type("F", (), {"pts": None})() for _ in range(frame_count)]
        packets = [_FakePacket([f]) for f in frames]
        container = _FakeContainer(packets, clock)

        monkeypatch.setattr(
            decoder_mod, "CaptureClock", lambda **kwargs: _FakeCaptureClock(), raising=True
        )
        monkeypatch.setattr(
            decoder_mod,
            "convert_and_store_frame",
            lambda stream_id, idx, frame, pool, **kw: _FakeFrameMeta(idx),
        )

        config = VideoFrameConfig(
            batch_size=batch_size,
            frame_interval=1,
            max_batch_age_seconds=max_age,
        )
        gen = decoder_mod.decode_stream_and_batch_generator(
            container=container,
            stream_id=0,
            stream_config=config,
            shm_pool=_FakeShmPool(),
            batch_size=batch_size,
        )
        return [item for item in gen if isinstance(item, tuple) and isinstance(item[0], dict)]

    def test_partial_batch_is_flushed_on_the_timer(self, monkeypatch):
        # 10 frames arriving 1s apart, batch_size=256, max age 3s. The batch opens
        # on frame 1 and goes stale on frame 4, so the expected cadence is
        # [4, 4] timed flushes plus a 2-frame end-of-stream drain. Without the
        # timer this would be a single batch of 10 emitted only at the end --
        # and on a real RTSP source, never.
        batches = self._run(monkeypatch, max_age=3.0, frame_count=10)

        sizes = [len(b[0]["frames"]) for b in batches]
        assert sizes == [4, 4, 2], f"unexpected flush cadence: {sizes}"
        assert sum(sizes) == 10, "no frame may be dropped by the timer"

    def test_timer_off_yields_a_single_drain(self, monkeypatch):
        # With the timer disabled the only emission is the end-of-stream drain,
        # which is exactly the behaviour finite files rely on.
        batches = self._run(monkeypatch, max_age=0.0, frame_count=10)

        assert len(batches) == 1
        assert len(batches[0][0]["frames"]) == 10

    def test_full_batch_still_flushes_before_the_timer(self, monkeypatch):
        # batch_size is the tighter bound here, so size wins over age.
        batches = self._run(monkeypatch, max_age=1000.0, frame_count=10, batch_size=5)

        sizes = [len(b[0]["frames"]) for b in batches]
        assert sizes == [5, 5]


class _FakeCaptureClock:
    def capture_epoch(self, frame):
        return (None, None)


class _FakeFrameMeta:
    """Stand-in for ``FrameMetadata``; only ``to_dict`` is exercised here."""

    def __init__(self, frame_index):
        self.frame_index = frame_index

    def to_dict(self):
        return {"frame_index": self.frame_index}


class _FakeShmPool:
    """Pool large enough that ``_clamp_batch_size_to_pool`` leaves batch_size alone."""

    max_blocks = 4096
    block_size = 1920 * 1080 * 3


class _FakePacket:
    def __init__(self, frames):
        self.dts = 0
        self.pts = None
        self._frames = frames

    def decode(self):
        return self._frames


class _FakeStream:
    thread_type = "AUTO"
    skip_frame = None
    time_base = None


class _FakeContainer:
    """Minimal PyAV container stand-in that advances the fake clock per packet."""

    def __init__(self, packets, clock):
        self._packets = packets
        self._clock = clock
        self.streams = type("S", (), {"video": [_FakeStream()]})()

    def demux(self, _stream):
        for packet in self._packets:
            self._clock["t"] += 1.0
            yield packet

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestSourceRedactionInStreamMetadata:
    """Decoder-built stream metadata must never carry credentials.

    ``VideoStreamMetadata.stream_source`` is logged verbatim by the pipeline and
    travels with the extracted metadata, so an RTSP URL with embedded userinfo
    would publish the camera password into the service logs.
    """

    def test_rtsp_source_is_redacted(self):
        secret = "hunter2"
        source = f"rtsp://admin:{secret}@cam-1:554/live"
        rendered = _redact_source_for_metadata(VideoInput.auto_detect(source))
        assert secret not in rendered
        assert "admin" not in rendered
        assert rendered == "rtsp://***@cam-1:554/live"

    def test_credential_free_rtsp_source_is_unchanged(self):
        source = "rtsp://cam-1:554/live"
        assert _redact_source_for_metadata(VideoInput.auto_detect(source)) == source

    def test_file_source_is_preserved(self):
        source = "/data/clip.mp4"
        assert _redact_source_for_metadata(VideoInput.auto_detect(source)) == source

    def test_bytes_source_is_not_disclosed(self):
        rendered = _redact_source_for_metadata(VideoInput.auto_detect(b"\x00\x01raw"))
        assert rendered == "BYTES_SOURCE"


class TestFrameMetadataIngestEpoch:
    """Each sampled frame must carry its own host ingest epoch.

    Live frames are aggregated into batches that can span several recorded
    segments. The segment a frame belongs to is resolved from this per-frame
    host timestamp, not the batch-processing time, so a batch spanning two 10s
    segments is split across them correctly instead of collapsing onto the last.
    """

    def test_ingest_epoch_round_trips_through_to_dict(self):
        from src.core.embedding.decoder import FrameMetadata

        fm = FrameMetadata(
            stream_id=1,
            frame_id=42,
            shm="shm-0",
            shape="(1080, 1920, 3)",
            dtype="uint8",
            ingest_epoch=1791187445.5,
        )
        assert fm.to_dict()["ingest_epoch"] == 1791187445.5

    def test_ingest_epoch_defaults_to_none_for_non_live(self):
        from src.core.embedding.decoder import FrameMetadata

        fm = FrameMetadata(stream_id=1, frame_id=0, shm="shm-0", shape="(2,2,3)", dtype="uint8")
        assert fm.to_dict()["ingest_epoch"] is None
