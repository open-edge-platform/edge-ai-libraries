# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""API-level tests for the live-stream CRUD endpoints."""

from http import HTTPStatus
from typing import List

import pytest
from fastapi.testclient import TestClient

from src.common import settings
from src.common.schema import LiveStreamStateEnum
from src.core.live.manager import (
    LiveStreamManager,
    reset_live_stream_manager,
    set_live_stream_manager,
)
from src.core.live.models import LiveStream
from src.core.live.store import InMemoryLiveStreamStore

BASE = "/media/streams"
CREDENTIALED_URL = "rtsp://admin:s3cr3t@camera-1.local:554/stream1"


class FakeWorker:
    """Worker stand-in: records lifecycle calls, opens no connection."""

    def __init__(self, stream: LiveStream, *, on_update=None, **_kwargs) -> None:
        self.stream = stream
        self._on_update = on_update
        self.calls: List[str] = []
        self.alive = False

    @property
    def stream_id(self) -> str:
        return self.stream.stream_id

    def is_alive(self) -> bool:
        return self.alive

    def start(self, paused: bool = False) -> None:
        self.alive = True
        self.calls.append("start")
        self.stream.state = LiveStreamStateEnum.paused if paused else LiveStreamStateEnum.running
        if self._on_update:
            self._on_update(self.stream)

    def pause(self) -> None:
        self.calls.append("pause")
        self.stream.state = LiveStreamStateEnum.paused

    def resume(self) -> None:
        self.calls.append("resume")
        self.stream.state = LiveStreamStateEnum.running

    def stop(self, join: bool = True, timeout: float = 0.0) -> None:
        self.calls.append("stop")
        self.alive = False


@pytest.fixture
def client():
    """A test client wired to an isolated, in-memory live-stream manager."""
    from src.main import app

    set_live_stream_manager(LiveStreamManager(InMemoryLiveStreamStore(), worker_factory=FakeWorker))
    with TestClient(app) as test_client:
        yield test_client
    reset_live_stream_manager()


def _create(client, **overrides):
    payload = {"stream_url": CREDENTIALED_URL, "stream_name": "cam"}
    payload.update(overrides)
    return client.post(BASE, json=payload)


# --------------------------------------------------------------------------
# Create
# --------------------------------------------------------------------------
def test_create_returns_accepted_with_a_stream_id(client):
    response = _create(client)

    assert response.status_code == HTTPStatus.ACCEPTED
    stream = response.json()["stream"]
    assert stream["stream_id"]
    assert stream["state"] == LiveStreamStateEnum.running.value
    # The addressable identity a consumer needs for playback and deletion.
    assert stream["video_id"] == stream["stream_id"]
    assert stream["bucket_name"] == settings.LIVE_STREAM_BUCKET


def test_create_never_echoes_credentials(client):
    response = _create(client)
    assert "s3cr3t" not in response.text
    assert "admin" not in response.text
    assert response.json()["stream"]["stream_url"].endswith("camera-1.local:554/stream1")


def test_create_accepts_processing_overrides(client):
    response = _create(
        client,
        frame_interval=30,
        enable_object_detection=False,
        detection_confidence=0.5,
        tags=["lobby"],
    )
    stream = response.json()["stream"]
    assert stream["frame_interval"] == 30
    assert stream["enable_object_detection"] is False
    assert stream["detection_confidence"] == 0.5
    assert stream["tags"] == ["lobby"]


def test_create_with_start_false_registers_paused(client):
    response = _create(client, start=False)
    assert response.json()["stream"]["state"] == LiveStreamStateEnum.paused.value


@pytest.mark.parametrize("url", ["http://camera/stream", "file:///etc/passwd", "not-a-url", ""])
def test_create_rejects_non_rtsp_urls(client, url):
    assert _create(client, stream_url=url).status_code in (
        HTTPStatus.BAD_REQUEST,
        HTTPStatus.UNPROCESSABLE_ENTITY,
    )


@pytest.mark.parametrize(
    "field,value",
    [("frame_interval", 0), ("frame_interval", 1000), ("detection_confidence", 5.0)],
)
def test_create_validates_processing_parameters(client, field, value):
    response = _create(client, **{field: value})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_create_returns_503_at_the_concurrency_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "LIVE_STREAM_MAX_CONCURRENT", 1)
    assert _create(client, stream_url="rtsp://cam-a/s").status_code == HTTPStatus.ACCEPTED

    response = _create(client, stream_url="rtsp://cam-b/s")
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    # Errors are normalized to the service-wide DataPrepResponse envelope.
    assert "concurrent" in response.json()["message"].lower()


def test_endpoints_are_unavailable_when_live_ingestion_is_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "LIVE_STREAM_ENABLED", False)
    assert _create(client).status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert client.get(BASE).status_code == HTTPStatus.SERVICE_UNAVAILABLE


# --------------------------------------------------------------------------
# Batch create
# --------------------------------------------------------------------------
def test_batch_create_reports_per_item_outcomes(client):
    response = client.post(
        f"{BASE}/batch",
        json={
            "items": [
                {"stream_url": "rtsp://cam-a/s"},
                {"stream_url": "http://cam-b/s"},
            ]
        },
    )

    assert response.status_code == HTTPStatus.ACCEPTED
    body = response.json()
    assert body["accepted"] == 1
    assert body["rejected"] == 1
    statuses = {item["status"] for item in body["items"]}
    assert statuses == {"success", "error"}
    # A bad item must not block the good one.
    assert client.get(BASE).json()["count"] == 1


def test_batch_create_identifiers_are_redacted(client):
    response = client.post(f"{BASE}/batch", json={"items": [{"stream_url": CREDENTIALED_URL}]})
    assert "s3cr3t" not in response.text


def test_batch_create_rejects_an_empty_batch(client):
    response = client.post(f"{BASE}/batch", json={"items": []})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


# --------------------------------------------------------------------------
# Read
# --------------------------------------------------------------------------
def test_list_is_empty_before_anything_is_registered(client):
    body = client.get(BASE).json()
    assert body["count"] == 0
    assert body["streams"] == []


def test_list_filters_by_state_and_tags(client):
    running = _create(client, stream_url="rtsp://cam-a/s", tags=["lobby"]).json()["stream"]
    _create(client, stream_url="rtsp://cam-b/s", tags=["garage"], start=False)

    by_state = client.get(BASE, params={"state": "running"}).json()
    assert [s["stream_id"] for s in by_state["streams"]] == [running["stream_id"]]

    by_tag = client.get(BASE, params={"tags": ["lobby"]}).json()
    assert [s["stream_id"] for s in by_tag["streams"]] == [running["stream_id"]]


def test_get_returns_the_stream_with_its_statistics(client):
    stream_id = _create(client).json()["stream"]["stream_id"]

    body = client.get(f"{BASE}/{stream_id}").json()
    assert body["stream"]["stream_id"] == stream_id
    assert body["stream"]["stats"]["frames_processed"] == 0
    assert "s3cr3t" not in str(body)


def test_get_unknown_stream_returns_404(client):
    assert client.get(f"{BASE}/nope").status_code == HTTPStatus.NOT_FOUND


# --------------------------------------------------------------------------
# Update
# --------------------------------------------------------------------------
def test_patch_updates_only_the_supplied_fields(client):
    stream = _create(client, start=False, tags=["a"]).json()["stream"]

    body = client.patch(
        f"{BASE}/{stream['stream_id']}", json={"description": "lobby camera"}
    ).json()["stream"]

    assert body["description"] == "lobby camera"
    assert body["stream_name"] == stream["stream_name"]
    assert body["tags"] == ["a"]


def test_patch_pauses_and_resumes_a_stream(client):
    stream_id = _create(client).json()["stream"]["stream_id"]

    paused = client.patch(f"{BASE}/{stream_id}", json={"state": "paused"})
    assert paused.json()["stream"]["state"] == LiveStreamStateEnum.paused.value

    resumed = client.patch(f"{BASE}/{stream_id}", json={"state": "running"})
    assert resumed.json()["stream"]["state"] == LiveStreamStateEnum.running.value


def test_patch_rejects_an_unsupported_state_transition(client):
    stream_id = _create(client).json()["stream"]["stream_id"]
    response = client.patch(f"{BASE}/{stream_id}", json={"state": "error"})
    assert response.status_code in (
        HTTPStatus.BAD_REQUEST,
        HTTPStatus.UNPROCESSABLE_ENTITY,
    )


def test_patch_unknown_stream_returns_404(client):
    assert (
        client.patch(f"{BASE}/nope", json={"description": "x"}).status_code == HTTPStatus.NOT_FOUND
    )


# --------------------------------------------------------------------------
# Delete
# --------------------------------------------------------------------------
def test_delete_deregisters_the_stream(client):
    stream_id = _create(client).json()["stream"]["stream_id"]

    body = client.delete(f"{BASE}/{stream_id}").json()
    assert body["stream_id"] == stream_id
    # Embeddings and media are retained unless purging is requested.
    assert body.get("embeddings_purged") is None
    assert client.get(BASE).json()["count"] == 0


def test_delete_with_purge_flags_removes_data(client, monkeypatch):
    stream_id = _create(client).json()["stream"]["stream_id"]

    class FakeVectorStore:
        def delete_embeddings(self, bucket, video_id):
            return 9

    monkeypatch.setattr(
        "src.core.vectorstores.get_vector_store", lambda: FakeVectorStore(), raising=False
    )
    monkeypatch.setattr(
        "src.core.live.manager.LiveStreamManager.purge_media",
        staticmethod(lambda stream, before_epoch=None: 4),
    )

    body = client.delete(
        f"{BASE}/{stream_id}",
        params={"purge_embeddings": True, "purge_media": True},
    ).json()

    assert body["embeddings_purged"] == 9
    assert body["media_purged"] == 4


def test_delete_unknown_stream_returns_404(client):
    assert client.delete(f"{BASE}/nope").status_code == HTTPStatus.NOT_FOUND


def test_batch_delete_isolates_unknown_ids(client):
    stream_id = _create(client).json()["stream"]["stream_id"]

    body = client.request("DELETE", BASE, json={"stream_ids": [stream_id, "nope"]}).json()

    assert body["accepted"] == 1
    assert body["rejected"] == 1
    assert client.get(BASE).json()["count"] == 0


# --------------------------------------------------------------------------
# Cross-cutting
# --------------------------------------------------------------------------
def test_health_reports_live_stream_counts(client):
    _create(client)
    body = client.get("/health").json()

    assert body["live_streams_enabled"] is True
    assert body["live_streams"]["total"] == 1


def test_legacy_rtsp_endpoint_is_gone(client):
    response = client.post("/media/rtsp", json={"video_uris": ["rtsp://cam/s"]})
    assert response.status_code in (HTTPStatus.NOT_FOUND, HTTPStatus.METHOD_NOT_ALLOWED)
