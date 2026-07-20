# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Endpoint-level tests for the batch ingestion API.

Storage and the heavy per-item processor are stubbed so the async 202 + poll
flow, validation, and error responses can be verified without a real backend.
"""

import time
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import src.endpoints.video_processing.batch_ingest as batch_ep
from src.core.jobs.batch_jobs import reset_jobs


@pytest.fixture
def client(monkeypatch):
    # Stub storage so _stash_bytes / selector listing never touch a real backend.
    fake_storage = MagicMock()
    fake_storage.ensure_bucket_exists.return_value = None
    fake_storage.upload_video.return_value = None
    fake_storage.list_all_videos.return_value = [
        {"video_id": "vid_a", "video_name": "a.mp4"},
        {"video_id": "vid_b", "video_name": "b.mp4"},
        {"video_id": "other", "video_name": "c.mp4"},
    ]
    monkeypatch.setattr(batch_ep, "get_minio_client", lambda: fake_storage)
    # Stub the heavy processor with a fast fake that reports 4 embeddings.
    monkeypatch.setattr(batch_ep, "process_stored_video", lambda item: 4)
    reset_jobs()

    from src.main import app

    with TestClient(app) as c:
        yield c
    reset_jobs()


def _poll(client, job_id, timeout=5.0):
    deadline = time.time() + timeout
    terminal = {"completed", "completed_with_errors", "failed", "cancelled"}
    while time.time() < deadline:
        resp = client.get(f"/videos/batch/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        if body["state"] in terminal:
            return body
        time.sleep(0.03)
    raise AssertionError("job did not finish")


def test_batch_existing_explicit_items(client):
    resp = client.post(
        "/videos/batch",
        json={"items": [{"video_id": "vid_a"}, {"video_id": "vid_b"}]},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["accepted"] == 2
    final = _poll(client, body["job_id"])
    assert final["state"] == "completed"
    assert final["completed"] == 2
    assert all(i["embeddings_count"] == 4 for i in final["items"])


def test_batch_existing_bucket_selector_with_prefix(client):
    resp = client.post("/videos/batch", json={"bucket_name": "test-bucket", "prefix": "vid_"})
    assert resp.status_code == 202
    body = resp.json()
    # Selector should match vid_a and vid_b, not "other".
    assert body["accepted"] == 2
    final = _poll(client, body["job_id"])
    assert final["state"] == "completed"


def test_batch_existing_requires_items_or_selector(client):
    resp = client.post("/videos/batch", json={})
    assert resp.status_code == 400


def test_batch_too_large_rejected(client, monkeypatch):
    from src.common import settings

    monkeypatch.setattr(settings, "BATCH_MAX_ITEMS", 1)
    resp = client.post(
        "/videos/batch",
        json={"items": [{"video_id": "vid_a"}, {"video_id": "vid_b"}]},
    )
    assert resp.status_code == 400


def test_upload_batch_flow(client):
    files = [
        ("files", ("one.mp4", b"data-one", "video/mp4")),
        ("files", ("two.mp4", b"data-two", "video/mp4")),
    ]
    resp = client.post("/videos/upload/batch", files=files)
    assert resp.status_code == 202
    body = resp.json()
    assert body["accepted"] == 2
    final = _poll(client, body["job_id"])
    assert final["state"] == "completed"
    assert {i["identifier"] for i in final["items"]} == {"one.mp4", "two.mp4"}


def test_upload_batch_rejects_non_mp4(client):
    files = [("files", ("bad.txt", b"nope", "text/plain"))]
    resp = client.post("/videos/upload/batch", files=files)
    assert resp.status_code == 400


def test_status_unknown_job_404(client):
    resp = client.get("/videos/batch/nonexistent")
    assert resp.status_code == 404


def test_cancel_unknown_job_404(client):
    resp = client.delete("/videos/batch/nonexistent")
    assert resp.status_code == 404
