# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the live-stream manager, worker lifecycle, and retention."""

import threading
import time
from typing import Any, Dict, List, Optional

import pytest

from src.common import settings
from src.common.schema import LiveStreamStateEnum
from src.core.live.manager import (
    LiveStreamLimitError,
    LiveStreamManager,
    LiveStreamNotFoundError,
    LiveStreamPurgeError,
    LivePurgeBackendError,
    _object_is_older_than,
)
from src.core.live.models import LiveStream
from src.core.live.segments import segment_object_name, segment_start
from src.core.live.store import InMemoryLiveStreamStore
from src.core.live.urls import InvalidStreamUrlError
from src.core.live.worker import LiveStreamWorker

CREDENTIALED_URL = "rtsp://admin:s3cr3t@camera-1.local:554/stream1"


class FakeWorker:
    """A worker stand-in that records lifecycle calls without touching RTSP."""

    instances: List["FakeWorker"] = []

    def __init__(self, stream: LiveStream, *, on_update=None, **_kwargs) -> None:
        self.stream = stream
        self._on_update = on_update
        self.calls: List[str] = []
        self.alive = False
        FakeWorker.instances.append(self)

    @property
    def stream_id(self) -> str:
        return self.stream.stream_id

    def is_alive(self) -> bool:
        return self.alive

    def start(self, paused: bool = False) -> None:
        self.alive = True
        self.calls.append("start(paused)" if paused else "start")
        self.stream.state = LiveStreamStateEnum.paused if paused else LiveStreamStateEnum.running
        if self._on_update:
            self._on_update(self.stream)

    def pause(self) -> None:
        self.calls.append("pause")
        self.stream.state = LiveStreamStateEnum.paused
        self.stream.desired_state = LiveStreamStateEnum.paused

    def resume(self) -> None:
        self.calls.append("resume")
        self.stream.state = LiveStreamStateEnum.running
        self.stream.desired_state = LiveStreamStateEnum.running

    def stop(self, join: bool = True, timeout: float = 0.0) -> None:
        self.calls.append("stop")
        self.alive = False
        self.stream.state = LiveStreamStateEnum.stopped


@pytest.fixture
def manager():
    FakeWorker.instances = []
    yield LiveStreamManager(InMemoryLiveStreamStore(), worker_factory=FakeWorker)


# --------------------------------------------------------------------------
# Create / read
# --------------------------------------------------------------------------
def test_create_registers_persists_and_starts(manager):
    stream = manager.create(stream_url=CREDENTIALED_URL, stream_name="cam")

    assert manager.store.get(stream.stream_id) is not None
    assert FakeWorker.instances[0].calls == ["start"]
    assert stream.desired_state == LiveStreamStateEnum.running
    # Identity that makes live data addressable by the media endpoints.
    assert stream.bucket_name == settings.LIVE_STREAM_BUCKET


def test_create_with_start_false_registers_without_ingesting(manager):
    stream = manager.create(stream_url=CREDENTIALED_URL, start=False)

    assert FakeWorker.instances[0].calls == ["start(paused)"]
    assert stream.desired_state == LiveStreamStateEnum.paused


def test_create_applies_defaults_from_settings(manager):
    stream = manager.create(stream_url=CREDENTIALED_URL)
    assert stream.frame_interval == settings.FRAME_INTERVAL
    assert stream.detection_confidence == settings.DETECTION_CONFIDENCE


def test_create_rejects_a_non_rtsp_url(manager):
    with pytest.raises(InvalidStreamUrlError):
        manager.create(stream_url="http://camera-1.local/stream")
    assert manager.list() == []


def test_create_enforces_the_concurrency_limit(manager, monkeypatch):
    monkeypatch.setattr(settings, "LIVE_STREAM_MAX_CONCURRENT", 1)
    manager.create(stream_url="rtsp://cam-a/stream")

    with pytest.raises(LiveStreamLimitError):
        manager.create(stream_url="rtsp://cam-b/stream")
    # The rejected stream must not linger in the registry.
    assert len(manager.list()) == 1


def test_paused_streams_do_not_consume_the_concurrency_budget(manager, monkeypatch):
    monkeypatch.setattr(settings, "LIVE_STREAM_MAX_CONCURRENT", 1)
    manager.create(stream_url="rtsp://cam-a/stream", start=False)
    # A paused stream is registered but not ingesting, so there is still room.
    assert manager.create(stream_url="rtsp://cam-b/stream")


def test_get_unknown_stream_raises(manager):
    with pytest.raises(LiveStreamNotFoundError):
        manager.get("nope")


def test_list_filters_by_state_and_tags(manager):
    running = manager.create(stream_url="rtsp://cam-a/stream", tags=["lobby", "hd"])
    manager.create(stream_url="rtsp://cam-b/stream", tags=["garage"], start=False)

    assert [s.stream_id for s in manager.list(state=LiveStreamStateEnum.running)] == [
        running.stream_id
    ]
    assert [s.stream_id for s in manager.list(tags=["lobby"])] == [running.stream_id]
    # Tag filtering is a conjunction.
    assert manager.list(tags=["lobby", "garage"]) == []


def test_counts_reports_a_state_histogram(manager):
    manager.create(stream_url="rtsp://cam-a/stream")
    manager.create(stream_url="rtsp://cam-b/stream", start=False)

    counts = manager.counts()
    assert counts["total"] == 2
    assert counts[LiveStreamStateEnum.running.value] == 1
    assert counts[LiveStreamStateEnum.paused.value] == 1


# --------------------------------------------------------------------------
# Update
# --------------------------------------------------------------------------
def test_update_changes_descriptive_fields(manager):
    stream = manager.create(stream_url=CREDENTIALED_URL, start=False)
    updated = manager.update(stream.stream_id, stream_name="lobby-cam", description="d", tags=["a"])

    assert updated.stream_name == "lobby-cam"
    assert updated.description == "d"
    assert updated.tags == ["a"]
    assert manager.store.get(stream.stream_id).stream_name == "lobby-cam"


def test_update_pauses_and_resumes(manager):
    stream = manager.create(stream_url=CREDENTIALED_URL)
    worker = FakeWorker.instances[0]

    manager.update(stream.stream_id, state=LiveStreamStateEnum.paused)
    assert "pause" in worker.calls
    assert manager.get(stream.stream_id).desired_state == LiveStreamStateEnum.paused

    manager.update(stream.stream_id, state=LiveStreamStateEnum.running)
    assert "resume" in worker.calls
    assert manager.get(stream.stream_id).desired_state == LiveStreamStateEnum.running


def test_update_bounces_the_session_when_processing_params_change(manager):
    stream = manager.create(stream_url=CREDENTIALED_URL)
    worker = FakeWorker.instances[0]
    worker.calls.clear()

    manager.update(stream.stream_id, frame_interval=30)

    assert manager.get(stream.stream_id).frame_interval == 30
    # Restarting the session is what makes the new interval take effect now.
    assert worker.calls == ["pause", "resume"]


def test_update_does_not_bounce_a_paused_stream(manager):
    stream = manager.create(stream_url=CREDENTIALED_URL, start=False)
    worker = FakeWorker.instances[0]
    worker.calls.clear()

    manager.update(stream.stream_id, frame_interval=30)
    assert worker.calls == []


def test_update_unknown_stream_raises(manager):
    with pytest.raises(LiveStreamNotFoundError):
        manager.update("nope", description="x")


# --------------------------------------------------------------------------
# Delete / purge
# --------------------------------------------------------------------------
def test_delete_stops_the_worker_and_deregisters(manager):
    stream = manager.create(stream_url=CREDENTIALED_URL)
    worker = FakeWorker.instances[0]

    _, embeddings, media = manager.delete(stream.stream_id)

    assert "stop" in worker.calls
    assert manager.store.get(stream.stream_id) is None
    # Data is retained unless a purge is explicitly requested.
    assert embeddings is None and media is None


def test_delete_can_purge_embeddings(manager, monkeypatch):
    stream = manager.create(stream_url=CREDENTIALED_URL)
    calls: Dict[str, Any] = {}

    class FakeStore:
        def delete_embeddings(self, bucket, video_id):
            calls["args"] = (bucket, video_id)
            return 12

    monkeypatch.setattr(
        "src.core.vectorstores.get_vector_store", lambda: FakeStore(), raising=False
    )
    _, embeddings, _ = manager.delete(stream.stream_id, purge_embeddings=True)

    assert embeddings == 12
    assert calls["args"] == (settings.LIVE_STREAM_BUCKET, stream.stream_id)


def test_purge_embeddings_raises_backend_error_on_failure(manager, monkeypatch):
    stream = manager.create(stream_url=CREDENTIALED_URL, start=False)

    class ExplodingStore:
        def delete_embeddings(self, bucket, video_id):
            raise RuntimeError("vector db down")

    monkeypatch.setattr(
        "src.core.vectorstores.get_vector_store",
        lambda: ExplodingStore(),
        raising=False,
    )
    # A real backend failure is signalled by an exception, distinct from the
    # -1 "success, no exact count" that VDMS/Milvus return on a clean delete.
    with pytest.raises(LivePurgeBackendError):
        manager.purge_embeddings(stream)


def test_purge_embeddings_returns_minus_one_on_countless_success(manager, monkeypatch):
    stream = manager.create(stream_url=CREDENTIALED_URL, start=False)

    class CountlessStore:
        def delete_embeddings(self, bucket, video_id):
            return -1  # VDMS/Milvus success sentinel

    monkeypatch.setattr(
        "src.core.vectorstores.get_vector_store", lambda: CountlessStore(), raising=False
    )
    # -1 is a success, not a failure: it must not raise.
    assert manager.purge_embeddings(stream) == -1



def test_delete_unknown_stream_raises(manager):
    with pytest.raises(LiveStreamNotFoundError):
        manager.delete("nope")


def test_delete_aborts_and_keeps_the_stream_when_a_purge_fails(manager, monkeypatch):
    stream = manager.create(stream_url=CREDENTIALED_URL, start=False)

    class ExplodingStore:
        def delete_embeddings(self, bucket, video_id):
            raise RuntimeError("vector db down")

    monkeypatch.setattr(
        "src.core.vectorstores.get_vector_store", lambda: ExplodingStore(), raising=False
    )

    with pytest.raises(LiveStreamPurgeError):
        manager.delete(stream.stream_id, purge_embeddings=True)

    # The registration survives so the caller can retry the delete.
    kept = manager.store.get(stream.stream_id)
    assert kept is not None
    assert kept.state == LiveStreamStateEnum.error
    assert kept.last_error


def test_delete_succeeds_when_vector_store_cannot_report_a_count(manager, monkeypatch):
    """Regression: VDMS/Milvus return -1 on success; that is not a purge failure."""
    stream = manager.create(stream_url=CREDENTIALED_URL)

    class CountlessStore:
        def delete_embeddings(self, bucket, video_id):
            return -1

    monkeypatch.setattr(
        "src.core.vectorstores.get_vector_store", lambda: CountlessStore(), raising=False
    )
    monkeypatch.setattr(LiveStreamManager, "purge_media", lambda self, s, before_epoch=None: 0)

    # Must not raise and must deregister the stream.
    _, embeddings, media = manager.delete(
        stream.stream_id, purge_embeddings=True, purge_media=True
    )
    assert embeddings == -1 and media == 0
    assert manager.store.get(stream.stream_id) is None


def test_delete_without_purge_tombstones_when_retention_is_on(manager, monkeypatch):
    monkeypatch.setattr(settings, "LIVE_RETENTION_HOURS", 24.0)
    stream = manager.create(stream_url=CREDENTIALED_URL)

    manager.delete(stream.stream_id)

    # Hidden from the API but kept for the sweeper.
    record = manager.store.get(stream.stream_id)
    assert record is not None and record.is_tombstone
    assert stream.stream_id not in {s.stream_id for s in manager.list()}
    assert stream.stream_id in {s.stream_id for s in manager.list_tombstones()}
    with pytest.raises(LiveStreamNotFoundError):
        manager.get(stream.stream_id)


def test_delete_purging_everything_removes_the_record_even_with_retention(manager, monkeypatch):
    monkeypatch.setattr(settings, "LIVE_RETENTION_HOURS", 24.0)
    stream = manager.create(stream_url=CREDENTIALED_URL)
    monkeypatch.setattr(LiveStreamManager, "purge_embeddings", lambda self, s, before_epoch=None: 0)
    monkeypatch.setattr(LiveStreamManager, "purge_media", lambda self, s, before_epoch=None: 0)

    manager.delete(stream.stream_id, purge_embeddings=True, purge_media=True)

    assert manager.store.get(stream.stream_id) is None
    assert manager.list_tombstones() == []


def test_object_age_filter_uses_the_segment_epoch():
    start = segment_start(1_000_000.0, 10)
    name = segment_object_name("abc", start)
    assert _object_is_older_than(name, cutoff_epoch=start + 1) is True
    assert _object_is_older_than(name, cutoff_epoch=start - 1) is False
    # An unparseable name must never be deleted by accident.
    assert _object_is_older_than("abc/segments/not-an-epoch.mp4", 1e12) is False


# --------------------------------------------------------------------------
# Restore on startup
# --------------------------------------------------------------------------
def test_restore_restarts_streams_that_were_running(manager):
    store = manager.store
    running = LiveStream.new(stream_url="rtsp://cam-a/stream", start=True)
    paused = LiveStream.new(stream_url="rtsp://cam-b/stream", start=False)
    store.upsert(running)
    store.upsert(paused)

    restored = LiveStreamManager(store, worker_factory=FakeWorker)
    FakeWorker.instances = []
    result = restored.restore()

    assert len(result) == 2
    calls = {w.stream_id: w.calls for w in FakeWorker.instances}
    assert calls[running.stream_id] == ["start"]
    assert calls[paused.stream_id] == ["start(paused)"]


def test_restore_respects_the_concurrency_limit(manager, monkeypatch):
    monkeypatch.setattr(settings, "LIVE_STREAM_MAX_CONCURRENT", 1)
    store = manager.store
    for index in range(2):
        store.upsert(LiveStream.new(stream_url=f"rtsp://cam-{index}/s", start=True))

    restored = LiveStreamManager(store, worker_factory=FakeWorker)
    FakeWorker.instances = []
    restored.restore()

    started = [w for w in FakeWorker.instances if w.calls == ["start"]]
    deferred = [w for w in FakeWorker.instances if w.calls == ["start(paused)"]]
    assert len(started) == 1
    assert len(deferred) == 1
    assert "concurrency limit" in deferred[0].stream.last_error


def test_restore_is_a_no_op_when_live_ingestion_is_disabled(manager, monkeypatch):
    manager.store.upsert(LiveStream.new(stream_url="rtsp://cam/s", start=True))
    monkeypatch.setattr(settings, "LIVE_STREAM_ENABLED", False)
    FakeWorker.instances = []

    assert manager.restore() == []
    assert FakeWorker.instances == []


def test_stop_all_stops_every_worker(manager):
    manager.create(stream_url="rtsp://cam-a/stream")
    manager.create(stream_url="rtsp://cam-b/stream")

    manager.stop_all()

    assert all("stop" in w.calls for w in FakeWorker.instances)
    assert manager.counts()["total"] == 2  # registrations survive a shutdown


# --------------------------------------------------------------------------
# Worker behaviour (real worker, fake pipeline + recorder)
# --------------------------------------------------------------------------
class FakeRecorder:
    """Stands in for the media recorder; never opens a connection."""

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.stats = type("S", (), {"segments_stored": 2})()

    def start(self) -> None:
        pass

    def close(self) -> None:
        pass

    def join(self, timeout: Optional[float] = None) -> None:
        pass


def _worker(pipeline, stream: Optional[LiveStream] = None) -> LiveStreamWorker:
    stream = stream or LiveStream.new(stream_url=CREDENTIALED_URL)
    return LiveStreamWorker(
        stream,
        on_update=lambda _s: None,
        pipeline=pipeline,
        recorder_factory=lambda **kwargs: FakeRecorder(**kwargs),
    )


def test_worker_metadata_gives_live_embeddings_a_real_identity():
    stream = LiveStream.new(stream_url=CREDENTIALED_URL, tags=["lobby"])
    metadata = _worker(lambda **_: {})._metadata_dict()

    assert metadata["bucket_name"] == settings.LIVE_STREAM_BUCKET
    assert metadata["tags"] == []
    live = metadata["live"]
    # Credentials must never reach the vector database.
    assert "s3cr3t" not in live["stream_url"]
    assert live["stream_url"].startswith("rtsp://***@camera-1.local")
    assert callable(live["segment_url_builder"])
    assert live["segment_url_builder"](None) == ""


def test_worker_wires_the_recorders_segment_resolver_into_the_pipeline():
    """When a recorder is supplied, the pipeline must resolve frames against the
    recorder's real segment boundaries (PTS-anchored), not a guessed time
    bucket."""
    worker = _worker(lambda **_: {})

    class FakeRecorderWithResolver:
        def resolve_segment(self, media_pts):
            return (42.0, 7.5)

    live = worker._metadata_dict(FakeRecorderWithResolver())["live"]
    assert callable(live["segment_resolver"])
    assert live["segment_resolver"](123.0) == (42.0, 7.5)

    # Without a recorder the resolver is absent and the pipeline falls back.
    assert "segment_resolver" not in worker._metadata_dict()["live"]


def test_worker_segment_url_builder_points_at_the_recorded_segment():
    worker = _worker(lambda **_: {})
    live = worker._metadata_dict()["live"]
    start = segment_start(1_000_000.0, settings.LIVE_SEGMENT_DURATION_SECONDS)

    url = live["segment_url_builder"](start)
    # Root-relative so consumers can resolve it against their object-store
    # gateway; see LiveStreamWorker._metadata_dict.
    assert url == (
        f"/{settings.LIVE_STREAM_BUCKET}/" f"{segment_object_name(worker.stream_id, start)}"
    )
    assert url.startswith("/")


def test_worker_runs_the_pipeline_and_accumulates_stats(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_RECONNECT_MAX_ATTEMPTS", 0)
    started = threading.Event()

    def pipeline(**kwargs):
        started.set()
        # A live pipeline never returns totals while it runs, so progress is
        # reported per stored batch through the callback instead.
        report = kwargs["progress_callback"]
        report(20, 2)
        report(10, 1)
        return {"stored_ids": ["a", "b", "c"], "total_frames_processed": 30}

    worker = _worker(pipeline)
    monkeypatch.setattr(worker, "_record_telemetry", lambda *a, **k: None)
    worker._resume.set()  # the supervisor normally does this before a session

    error = worker._run_session()

    assert started.is_set()
    # Counted once, from the callback -- the returned totals must not be added on
    # top or every live stream would report double.
    assert worker.stream.stats.embeddings_created == 3
    assert worker.stream.stats.frames_processed == 30
    assert worker.stream.stats.segments_stored == 2
    # The pipeline returning on its own means the source went away.
    assert error is not None


def test_worker_reports_progress_before_the_pipeline_returns(monkeypatch):
    """Stats must be observable mid-session; a live source never returns."""
    monkeypatch.setattr(settings, "LIVE_RECONNECT_MAX_ATTEMPTS", 0)
    seen = {}

    def pipeline(**kwargs):
        report = kwargs["progress_callback"]
        report(15, 4)
        # Snapshot what an in-flight GET /media/streams/{id} would observe.
        seen["frames"] = worker.stream.stats.frames_processed
        seen["embeddings"] = worker.stream.stats.embeddings_created
        return {}

    worker = _worker(pipeline)
    monkeypatch.setattr(worker, "_record_telemetry", lambda *a, **k: None)
    worker._resume.set()

    worker._run_session()

    assert seen == {"frames": 15, "embeddings": 4}


def test_worker_surfaces_a_pipeline_failure_as_an_error(monkeypatch):
    def pipeline(**kwargs):
        raise RuntimeError("connection refused")

    worker = _worker(pipeline)
    monkeypatch.setattr(worker, "_record_telemetry", lambda *a, **k: None)
    worker._resume.set()

    error = worker._run_session()
    assert "connection refused" in error


def test_worker_marks_a_stream_in_error_after_exhausting_reconnects(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_RECONNECT_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "LIVE_RECONNECT_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(settings, "LIVE_RECONNECT_WINDOW_SECONDS", 3600)
    attempts: List[int] = []

    def pipeline(**kwargs):
        attempts.append(1)
        raise RuntimeError("unreachable")

    worker = _worker(pipeline)
    monkeypatch.setattr(worker, "_record_telemetry", lambda *a, **k: None)
    worker.start()

    deadline = time.time() + 10
    while worker.is_alive() and time.time() < deadline:
        time.sleep(0.05)

    assert worker.stream.state == LiveStreamStateEnum.error
    assert worker.stream.last_error
    # The initial attempt plus the budgeted retries.
    assert len(attempts) == 3
    assert worker.stream.stats.reconnect_count >= 1


def test_worker_stays_starting_until_the_source_delivers_data(monkeypatch):
    """A source that is still connecting (or unreachable) must not report
    ``running``. Regression: the state was set to ``running`` optimistically at
    the top of each session, so a dead stream looked healthy on the UI until a
    brief reconnect blip."""
    monkeypatch.setattr(settings, "LIVE_RECONNECT_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(settings, "LIVE_RECONNECT_WINDOW_SECONDS", 3600)
    connecting = threading.Event()
    release = threading.Event()

    def pipeline(shutdown_event=None, **kwargs):
        # Simulate a connect attempt in progress that delivers no data.
        connecting.set()
        release.wait(timeout=5)
        raise RuntimeError("Connection timed out")

    class SilentRecorder(FakeRecorder):
        """A recorder that never records a segment (source never connected)."""

        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self.stats = type("S", (), {"segments_stored": 0})()

    worker = LiveStreamWorker(
        LiveStream.new(stream_url=CREDENTIALED_URL),
        on_update=lambda _s: None,
        pipeline=pipeline,
        recorder_factory=lambda **kwargs: SilentRecorder(**kwargs),
    )
    monkeypatch.setattr(worker, "_record_telemetry", lambda *a, **k: None)
    worker.start()
    try:
        assert connecting.wait(timeout=5)
        # No frames and no segments yet, so the stream is not running.
        assert worker.stream.state == LiveStreamStateEnum.starting
    finally:
        release.set()
        worker.stop(timeout=5)


def test_worker_enters_running_only_once_frames_start_flowing(monkeypatch):
    """The stream flips to ``running`` the moment the source delivers data."""
    monkeypatch.setattr("src.core.live.worker._STATS_REFRESH_SECONDS", 0.05)
    monkeypatch.setattr(settings, "LIVE_RECONNECT_MAX_ATTEMPTS", 0)
    reported = threading.Event()
    release = threading.Event()

    def pipeline(shutdown_event=None, progress_callback=None, **kwargs):
        # First real frames for this session: now it is genuinely live.
        progress_callback(5, 1)
        reported.set()
        release.wait(timeout=5)
        return {"stored_ids": ["a"], "total_frames_processed": 5}

    class SilentRecorder(FakeRecorder):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self.stats = type("S", (), {"segments_stored": 0})()

    worker = LiveStreamWorker(
        LiveStream.new(stream_url=CREDENTIALED_URL),
        on_update=lambda _s: None,
        pipeline=pipeline,
        recorder_factory=lambda **kwargs: SilentRecorder(**kwargs),
    )
    monkeypatch.setattr(worker, "_record_telemetry", lambda *a, **k: None)
    worker.start()
    try:
        assert reported.wait(timeout=5)
        deadline = time.time() + 5
        while (
            worker.stream.state != LiveStreamStateEnum.running
            and time.time() < deadline
        ):
            time.sleep(0.02)
        assert worker.stream.state == LiveStreamStateEnum.running
    finally:
        release.set()
        worker.stop(timeout=5)


def test_worker_pause_and_stop_are_not_treated_as_failures(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_RECONNECT_INTERVAL_SECONDS", 0.01)
    running = threading.Event()

    def pipeline(shutdown_event=None, **kwargs):
        running.set()
        while not shutdown_event.is_set():
            time.sleep(0.01)
        return {"stored_ids": [], "total_frames_processed": 1}

    worker = _worker(pipeline)
    monkeypatch.setattr(worker, "_record_telemetry", lambda *a, **k: None)
    worker.start()
    assert running.wait(timeout=5)

    worker.pause()
    assert worker.stream.state == LiveStreamStateEnum.paused

    running.clear()
    worker.resume()
    assert running.wait(timeout=5)

    worker.stop(timeout=5)
    assert worker.stream.state == LiveStreamStateEnum.stopped
    assert not worker.is_alive()
    # A deliberate stop is not a reconnect.
    assert worker.stream.last_error is None


def test_worker_telemetry_reports_this_sessions_counts(monkeypatch):
    """Telemetry must carry the session's own work, not zeros or a running total.

    The live pipeline aggregates per stream and returns no top-level totals, so
    the counts have to come from the per-batch progress callback. Stream stats
    are cumulative across sessions, so the record must use the delta.
    """
    monkeypatch.setattr(settings, "LIVE_RECONNECT_MAX_ATTEMPTS", 0)
    captured = {}

    def pipeline(**kwargs):
        report = kwargs["progress_callback"]
        report(20, 2)
        report(10, 1)
        return {}

    worker = _worker(pipeline)
    # Pretend an earlier session already ran, so a cumulative read would be wrong.
    worker.stream.stats.frames_processed = 100
    worker.stream.stats.embeddings_created = 7
    monkeypatch.setattr(
        worker,
        "_record_telemetry",
        lambda result, ts, **kw: captured.update(kw),
    )
    worker._resume.set()

    worker._run_session()

    assert captured == {"frames": 30, "embeddings": 3}


def test_aggregator_publishes_combined_fleet_rate(monkeypatch):
    """Throughput must be the SUM across running streams, not one stream's rate.

    Regression guard for the "drops to ~7 eps with 4 streams" bug: the gauge is
    a single process-wide value, so a per-stream publisher would show one
    camera's rate. The aggregator sums the rolling embedding totals of every
    running stream and publishes one combined interval rate.
    """
    from src.core.live.metrics import LiveThroughputAggregator

    published: List[float] = []
    monkeypatch.setattr(
        "src.core.live.metrics.publish_embeddings_throughput",
        lambda value, ts: (published.append(value), True)[1],
    )

    class FakeManager:
        counts: dict = {}

        def running_embeddings_by_stream(self):
            return dict(self.counts)

    manager = FakeManager()
    agg = LiveThroughputAggregator(manager=manager)
    # Prime the window at t=100 with four streams already tracked and idle.
    agg._last_ts = 100.0
    manager.counts = {"s1": 0, "s2": 0, "s3": 0, "s4": 0}
    agg._last_counts = dict(manager.counts)

    # Four streams each add 5 embeddings over a 1s interval -> 20 eps combined.
    manager.counts = {"s1": 5, "s2": 5, "s3": 5, "s4": 5}
    rate = agg.sample(now=101.0)

    assert rate == 20.0
    assert published == [20.0]


def test_aggregator_holds_last_value_on_idle_interval(monkeypatch):
    """An interval with no new embeddings publishes nothing (gauge holds)."""
    from src.core.live.metrics import LiveThroughputAggregator

    published: List[float] = []
    monkeypatch.setattr(
        "src.core.live.metrics.publish_embeddings_throughput",
        lambda value, ts: (published.append(value), True)[1],
    )

    class FakeManager:
        counts: dict = {}

        def running_embeddings_by_stream(self):
            return dict(self.counts)

    manager = FakeManager()
    agg = LiveThroughputAggregator(manager=manager)
    agg._last_ts = 100.0
    manager.counts = {"s1": 12}
    agg._last_counts = dict(manager.counts)

    # Burst lands: total climbs to 24 over 1s -> 12 eps.
    manager.counts = {"s1": 24}
    assert agg.sample(now=101.0) == 12.0
    # Idle tick: no new embeddings -> no publish, window still advances.
    assert agg.sample(now=102.0) is None
    assert agg.sample(now=103.0) is None
    # Next burst measured over its OWN interval (total 24 -> 30 across 1s).
    manager.counts = {"s1": 30}
    assert agg.sample(now=104.0) == 6.0

    assert published == [12.0, 6.0]  # no zeros between bursts


def test_aggregator_ignores_shrinking_total(monkeypatch):
    """A stream pausing/stopping leaves the set; never publish a negative rate."""
    from src.core.live.metrics import LiveThroughputAggregator

    published: List[float] = []
    monkeypatch.setattr(
        "src.core.live.metrics.publish_embeddings_throughput",
        lambda value, ts: (published.append(value), True)[1],
    )

    class FakeManager:
        counts: dict = {}

        def running_embeddings_by_stream(self):
            return dict(self.counts)

    manager = FakeManager()
    agg = LiveThroughputAggregator(manager=manager)
    agg._last_ts = 100.0
    manager.counts = {"s1": 25, "s2": 15}
    agg._last_counts = dict(manager.counts)

    # One of the streams stops -> it drops out of the running set.
    manager.counts = {"s1": 25}
    assert agg.sample(now=101.0) is None
    assert published == []


def test_aggregator_does_not_spike_when_paused_stream_resumes(monkeypatch):
    """Resuming a paused stream must not dump its backlog as one interval.

    Regression guard for the "~1646 eps on resume" bug: a paused stream keeps a
    frozen ``embeddings_created`` counter and is excluded from the running set.
    When it resumes it rejoins with its full accumulated count; a scalar total
    would read that as a single interval's burst. Diffing per stream baselines
    the returning stream instead, so the gauge reflects only genuine new work.
    """
    from src.core.live.metrics import LiveThroughputAggregator

    published: List[float] = []
    monkeypatch.setattr(
        "src.core.live.metrics.publish_embeddings_throughput",
        lambda value, ts: (published.append(value), True)[1],
    )

    class FakeManager:
        counts: dict = {}

        def running_embeddings_by_stream(self):
            return dict(self.counts)

    manager = FakeManager()
    agg = LiveThroughputAggregator(manager=manager)
    agg._last_ts = 100.0
    # Only a steadily-running stream is tracked; the other is paused (absent).
    manager.counts = {"running": 30}
    agg._last_counts = dict(manager.counts)

    # The paused stream (8200 embeddings accumulated before the pause) resumes
    # and rejoins the running set, while the running stream adds 5 this interval.
    manager.counts = {"running": 35, "resumed": 8200}
    rate = agg.sample(now=101.0)

    # Only the 5 genuinely-new embeddings count; the 8200 backlog is baselined.
    assert rate == 5.0
    assert published == [5.0]
    # The resumed stream is now tracked, so its real throughput is measured next.
    manager.counts = {"running": 35, "resumed": 8210}
    assert agg.sample(now=102.0) == 10.0


def test_running_embeddings_total_sums_only_running_streams():
    """Manager aggregate excludes paused/stopped/errored workers."""
    from src.common.schema import LiveStreamStateEnum
    from src.core.live.manager import LiveStreamManager

    class FakeStats:
        def __init__(self, embeddings):
            self.embeddings_created = embeddings

    class FakeStream:
        def __init__(self, state, embeddings):
            self.state = state
            self.stats = FakeStats(embeddings)

    class FakeWorker:
        def __init__(self, state, embeddings, alive=True, stream_id="s"):
            self.stream_id = stream_id
            self.stream = FakeStream(state, embeddings)
            self._alive = alive

        def is_alive(self):
            return self._alive

    manager = LiveStreamManager.__new__(LiveStreamManager)
    manager._lock = threading.RLock()
    manager._workers = {
        "a": FakeWorker(LiveStreamStateEnum.running, 10, stream_id="a"),
        "b": FakeWorker(LiveStreamStateEnum.running, 7, stream_id="b"),
        "c": FakeWorker(LiveStreamStateEnum.paused, 100, stream_id="c"),
        "d": FakeWorker(LiveStreamStateEnum.stopped, 100, stream_id="d"),
        "e": FakeWorker(LiveStreamStateEnum.error, 100, stream_id="e"),
        "f": FakeWorker(LiveStreamStateEnum.running, 50, alive=False, stream_id="f"),
    }

    assert manager.running_embeddings_total() == 17


def test_clock_check_never_delays_ingestion_start(monkeypatch):
    """Regression: the camera clock probe must stay off the ingestion path.

    The probe resolves DNS and connects to the device's HTTP port, which may be
    slow, firewalled, or blackholed. Running it inline once delayed the first
    session by seconds; it must not delay it at all.
    """
    monkeypatch.setattr(settings, "LIVE_CLOCK_CHECK_ENABLED", True)
    probe_entered = threading.Event()
    release_probe = threading.Event()

    def slow_probe(*_args, **_kwargs):
        probe_entered.set()
        release_probe.wait(timeout=10)

    monkeypatch.setattr("src.core.live.worker.log_clock_skew", slow_probe)

    running = threading.Event()

    def pipeline(shutdown_event=None, **kwargs):
        running.set()
        while not shutdown_event.is_set():
            time.sleep(0.01)
        return {"stored_ids": [], "total_frames_processed": 1}

    worker = _worker(pipeline)
    monkeypatch.setattr(worker, "_record_telemetry", lambda *a, **k: None)
    worker.start()
    try:
        assert probe_entered.wait(timeout=5), "clock probe never ran"
        # The pipeline must start while the probe is still blocked.
        assert running.wait(timeout=5), "ingestion waited on the clock probe"
    finally:
        release_probe.set()
        worker.stop()


def test_clock_check_is_skipped_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_CLOCK_CHECK_ENABLED", False)
    called = threading.Event()
    monkeypatch.setattr("src.core.live.worker.log_clock_skew", lambda *a, **k: called.set())

    worker = _worker(lambda **_: {})
    worker._check_camera_clock()
    assert not called.wait(timeout=0.5)
