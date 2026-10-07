# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the live-stream registry, URL handling, and segment naming."""

import time

import pytest

from src.common.schema import LiveStreamStateEnum
from src.core.live.models import LiveStream
from src.core.live.segments import segment_id, segment_object_name, segment_start
from src.core.live.store import (
    InMemoryLiveStreamStore,
    PostgresLiveStreamStore,
    get_live_stream_store,
    reset_live_stream_store,
    set_live_stream_store,
)
from src.core.live.urls import (
    InvalidStreamUrlError,
    default_stream_name,
    redact_stream_url,
    validate_stream_url,
)

CREDENTIALED_URL = "rtsp://admin:s3cr3t@camera-1.local:554/stream1"


def _make_stream(**overrides) -> LiveStream:
    params = {
        "stream_url": CREDENTIALED_URL,
        "stream_name": "front-door",
        "description": "lobby camera",
        "frame_interval": 15,
        "enable_object_detection": True,
        "detection_confidence": 0.85,
        "bucket_name": "live-streams",
        "tags": ["lobby", "hd"],
        "start": True,
    }
    params.update(overrides)
    return LiveStream.new(**params)


# --------------------------------------------------------------------------
# URL handling
# --------------------------------------------------------------------------
def test_redact_stream_url_strips_credentials():
    redacted = redact_stream_url(CREDENTIALED_URL)
    # The marker is kept deliberately so an operator can tell that the source
    # is authenticated without the secret being disclosed.
    assert redacted == "rtsp://***@camera-1.local:554/stream1"
    assert "s3cr3t" not in redacted
    assert "admin" not in redacted


def test_redact_stream_url_keeps_credential_free_url_intact():
    url = "rtsp://camera-1.local:554/stream1"
    assert redact_stream_url(url) == url


def test_redact_stream_url_handles_unparseable_input():
    # Must never raise and never echo something that looks like a credential.
    assert "s3cr3t" not in redact_stream_url("rtsp://admin:s3cr3t@")


@pytest.mark.parametrize(
    "url",
    ["rtsp://cam/stream", "rtsps://cam:322/stream", "RTSP://CAM/stream"],
)
def test_validate_stream_url_accepts_rtsp_schemes(url):
    assert validate_stream_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "http://cam/stream",
        "file:///etc/passwd",
        "rtsp://",
        "not a url",
    ],
)
def test_validate_stream_url_rejects_everything_else(url):
    with pytest.raises(InvalidStreamUrlError):
        validate_stream_url(url)


def test_default_stream_name_never_leaks_credentials():
    name = default_stream_name(CREDENTIALED_URL)
    assert "s3cr3t" not in name
    assert "camera-1.local" in name


# --------------------------------------------------------------------------
# Segment naming contract (shared by recorder and embedding pipeline)
# --------------------------------------------------------------------------
def test_segment_start_buckets_to_wall_clock_boundaries():
    assert segment_start(1000.0, 10) == 1000.0
    assert segment_start(1009.9, 10) == 1000.0
    assert segment_start(1010.0, 10) == 1010.0


def test_segment_object_names_are_stable_and_prefixed_by_stream():
    start = segment_start(1234.5, 10)
    assert segment_object_name("abc", start) == "abc/segments/1230.mp4"
    assert segment_id("abc", start) == "abc_1230"


# --------------------------------------------------------------------------
# Record model
# --------------------------------------------------------------------------
def test_to_info_redacts_the_url_and_exposes_identity():
    stream = _make_stream()
    info = stream.to_info()
    assert info.stream_url == "rtsp://***@camera-1.local:554/stream1"
    assert "s3cr3t" not in info.model_dump_json()
    assert info.video_id == stream.stream_id
    assert info.bucket_name == "live-streams"


def test_row_round_trip_preserves_every_field():
    stream = _make_stream()
    stream.stats.frames_processed = 42
    stream.stats.embeddings_created = 7
    restored = LiveStream.from_row(stream.to_row())

    assert restored.stream_id == stream.stream_id
    # The registry is the one place the credentialed URL must survive, because
    # reconnect-after-restart needs it.
    assert restored.stream_url == CREDENTIALED_URL
    assert restored.tags == stream.tags
    assert restored.frame_interval == stream.frame_interval
    assert restored.enable_object_detection == stream.enable_object_detection
    assert restored.detection_confidence == stream.detection_confidence
    assert restored.desired_state == stream.desired_state
    assert restored.stats.frames_processed == 42
    assert restored.stats.embeddings_created == 7


# --------------------------------------------------------------------------
# Stores
# --------------------------------------------------------------------------
@pytest.fixture(params=["memory", "postgres"])
def store(request):
    if request.param == "memory":
        yield InMemoryLiveStreamStore()
    else:
        store = _postgres_store_or_skip()
        store.clear()
        try:
            yield store
        finally:
            store.clear()


def _postgres_store_or_skip() -> PostgresLiveStreamStore:
    """Return a Postgres-backed store, skipping the test if no DB is reachable."""
    store = PostgresLiveStreamStore()
    try:
        store.clear()  # Forces a connection + schema creation.
    except Exception as exc:  # noqa: BLE001 - any connection failure skips.
        pytest.skip(f"PostgreSQL is not available for live-stream store tests: {exc}")
    return store


def test_store_upsert_get_and_delete(store):
    stream = _make_stream()
    store.upsert(stream)

    fetched = store.get(stream.stream_id)
    assert fetched is not None
    assert fetched.stream_url == CREDENTIALED_URL

    assert store.delete(stream.stream_id) is True
    assert store.get(stream.stream_id) is None
    assert store.delete(stream.stream_id) is False


def test_store_upsert_is_idempotent(store):
    stream = _make_stream()
    store.upsert(stream)
    stream.description = "updated"
    stream.state = LiveStreamStateEnum.paused
    store.upsert(stream)

    assert len(store.list()) == 1
    fetched = store.get(stream.stream_id)
    assert fetched.description == "updated"
    assert fetched.state == LiveStreamStateEnum.paused


def test_store_list_returns_every_record(store):
    ids = set()
    for index in range(3):
        stream = _make_stream(stream_name=f"cam-{index}")
        store.upsert(stream)
        ids.add(stream.stream_id)
    assert {s.stream_id for s in store.list()} == ids


def test_store_get_unknown_id_returns_none(store):
    assert store.get("does-not-exist") is None


def test_postgres_store_survives_a_restart():
    store = _postgres_store_or_skip()
    store.clear()
    stream = _make_stream()
    store.upsert(stream)

    # A brand-new store object stands in for a service restart.
    restored = PostgresLiveStreamStore().get(stream.stream_id)
    assert restored is not None
    assert restored.stream_name == stream.stream_name
    assert restored.stream_url == CREDENTIALED_URL
    store.clear()


def test_store_factory_is_overridable_and_resettable():
    custom = InMemoryLiveStreamStore()
    set_live_stream_store(custom)
    try:
        assert get_live_stream_store() is custom
    finally:
        reset_live_stream_store()


def test_stats_record_tracks_activity():
    stream = _make_stream()
    assert stream.stats.frames_processed == 0
    stream.stats.last_frame_ts = time.time()
    assert stream.to_info().stats.last_frame_ts is not None
