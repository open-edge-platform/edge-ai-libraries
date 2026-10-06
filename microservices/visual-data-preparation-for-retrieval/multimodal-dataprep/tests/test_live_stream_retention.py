# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for live-stream retention sweeping and credential redaction."""

import logging
from typing import Any, Dict, List

import pytest

from src.common import settings
from src.core.live.manager import LiveStreamManager
from src.core.live.models import LiveStream
from src.core.live.retention import (
    LiveRetentionSweeper,
    get_retention_sweeper,
    reset_retention_sweeper,
)
from src.core.live.segments import segment_object_name, segment_start
from src.core.live.store import InMemoryLiveStreamStore
from src.core.live.urls import redact_stream_url

CREDENTIALED_URL = "rtsp://admin:s3cr3t@camera-1.local:554/stream1"
PASSWORD = "s3cr3t"


class RecordingManager(LiveStreamManager):
    """Manager that records purge calls instead of touching any backend."""

    def __init__(self, streams: List[LiveStream]) -> None:
        super().__init__(InMemoryLiveStreamStore())
        for stream in streams:
            self.store.upsert(stream)
        self.purges: List[Dict[str, Any]] = []

    def purge_embeddings(self, stream, before_epoch=None):  # type: ignore[override]
        self.purges.append({"kind": "embeddings", "before": before_epoch})
        return 1

    def purge_media(self, stream, before_epoch=None):  # type: ignore[override]
        self.purges.append({"kind": "media", "before": before_epoch})
        return 1


@pytest.fixture
def sweeper():
    stream = LiveStream.new(stream_url=CREDENTIALED_URL)
    manager = RecordingManager([stream])
    yield LiveRetentionSweeper(manager), manager
    reset_retention_sweeper()


# --------------------------------------------------------------------------
# Retention
# --------------------------------------------------------------------------
def test_retention_is_disabled_by_default(sweeper, monkeypatch):
    sweep, manager = sweeper
    monkeypatch.setattr(settings, "LIVE_RETENTION_HOURS", 0.0)

    assert sweep.enabled is False
    assert sweep.start() is False
    assert sweep.sweep() == 0
    # Nothing is ever deleted while retention is off.
    assert manager.purges == []


def test_sweep_purges_embeddings_and_media_past_the_cutoff(sweeper, monkeypatch):
    sweep, manager = sweeper
    monkeypatch.setattr(settings, "LIVE_RETENTION_HOURS", 2.0)

    assert sweep.sweep(now=10_000.0) == 1

    kinds = [purge["kind"] for purge in manager.purges]
    assert kinds == ["embeddings", "media"]
    assert all(purge["before"] == 10_000.0 - 7200.0 for purge in manager.purges)


def test_sweep_uses_a_fractional_hour_window(sweeper, monkeypatch):
    sweep, manager = sweeper
    monkeypatch.setattr(settings, "LIVE_RETENTION_HOURS", 0.5)

    sweep.sweep(now=10_000.0)
    assert manager.purges[0]["before"] == 10_000.0 - 1800.0


def test_sweep_is_a_no_op_without_registered_streams(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_RETENTION_HOURS", 1.0)
    sweep = LiveRetentionSweeper(RecordingManager([]))
    assert sweep.sweep() == 0


def test_sweeper_start_and_stop_are_idempotent(sweeper, monkeypatch):
    sweep, _ = sweeper
    monkeypatch.setattr(settings, "LIVE_RETENTION_HOURS", 1.0)
    monkeypatch.setattr(settings, "LIVE_RETENTION_SWEEP_MINUTES", 60.0)

    assert sweep.start() is True
    assert sweep.start() is True  # second call must not spawn a second thread
    sweep.stop(timeout=2)
    sweep.stop(timeout=2)


def test_process_wide_sweeper_is_a_singleton():
    assert get_retention_sweeper() is get_retention_sweeper()
    reset_retention_sweeper()


# --------------------------------------------------------------------------
# Credential redaction at every boundary
# --------------------------------------------------------------------------
def test_credentials_never_reach_the_vector_metadata():
    from src.core.live.worker import LiveStreamWorker

    worker = LiveStreamWorker(
        LiveStream.new(stream_url=CREDENTIALED_URL), on_update=lambda _s: None
    )
    metadata = worker._metadata_dict()
    metadata["live"].pop("segment_url_builder")

    assert PASSWORD not in str(metadata)
    assert "admin" not in str(metadata)


def test_credentials_never_reach_the_api_representation():
    info = LiveStream.new(stream_url=CREDENTIALED_URL).to_info()
    assert PASSWORD not in info.model_dump_json()


def test_credentials_never_reach_the_logs(caplog):
    manager = LiveStreamManager(InMemoryLiveStreamStore(), worker_factory=_NullWorker)
    with caplog.at_level(logging.DEBUG):
        stream = manager.create(stream_url=CREDENTIALED_URL)
        manager.delete(stream.stream_id)

    assert PASSWORD not in caplog.text
    # The host is still logged, so an operator can identify the camera.
    assert "camera-1.local" in caplog.text


def test_media_object_names_never_embed_the_url():
    stream = LiveStream.new(stream_url=CREDENTIALED_URL)
    start = segment_start(1_000_000.0, 10)

    assert PASSWORD not in segment_object_name(stream.stream_id, start)


def test_redaction_is_stable_under_repeated_application():
    once = redact_stream_url(CREDENTIALED_URL)
    assert redact_stream_url(once) == once


class _NullWorker:
    """Worker that does nothing, so manager logging can be tested in isolation."""

    def __init__(self, stream, *, on_update=None, **_kwargs):
        self.stream = stream

    @property
    def stream_id(self):
        return self.stream.stream_id

    def is_alive(self):
        return False

    def start(self, paused: bool = False):
        pass

    def stop(self, join: bool = True, timeout: float = 0.0):
        pass
