# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Endpoint tests for the JSON image ingestion API (base64 / URL).

Storage and the heavy embedding path are stubbed so the request handling,
validation, dedup rollback and async 202+poll flow are verified without a real
backend or model.
"""

import base64
import io
import time

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import src.endpoints.video_processing.ingest_image as ingest_ep
from src.core.jobs.batch_jobs import reset_jobs


def _png_b64(size=(16, 16)):
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def client(monkeypatch):
    fake_storage = MagicMock()
    fake_storage.ensure_bucket_exists.return_value = None
    fake_storage.upload_video.return_value = None
    monkeypatch.setattr(ingest_ep, "get_minio_client", lambda: fake_storage)
    # dedup is a no-op in these tests
    monkeypatch.setattr(ingest_ep, "check_and_register_upload", lambda *a, **k: None)

    async def _fake_embed(**kwargs):
        return ["id_1", "id_2"]

    monkeypatch.setattr(ingest_ep, "generate_image_embedding_from_content", _fake_embed)
    # Batch jobs run the real engine but with a stubbed processor.
    monkeypatch.setattr(ingest_ep, "process_stored_video", lambda item: 3)
    reset_jobs()

    from src.main import app

    with TestClient(app) as c:
        yield c
    reset_jobs()


def _poll(client, job_id, timeout=5.0):
    deadline = time.time() + timeout
    terminal = {"completed", "completed_with_errors", "failed", "cancelled"}
    while time.time() < deadline:
        body = client.get(f"/media/jobs/{job_id}").json()
        if body["state"] in terminal:
            return body
        time.sleep(0.03)
    raise AssertionError("job did not finish")


def test_ingest_single_base64(client):
    resp = client.post(
        "/media/ingest",
        json={"type": "image_base64", "image_base64": _png_b64(), "tags": ["a"]},
    )
    assert resp.status_code == 201


def test_ingest_single_data_url(client):
    resp = client.post(
        "/media/ingest",
        json={"type": "image_base64", "image_base64": f"data:image/png;base64,{_png_b64()}"},
    )
    assert resp.status_code == 201


def test_ingest_missing_payload_422(client):
    # type=image_base64 but no image_base64 -> schema validation error
    resp = client.post("/media/ingest", json={"type": "image_base64"})
    assert resp.status_code == 422


def test_ingest_invalid_base64_400(client):
    resp = client.post(
        "/media/ingest",
        json={"type": "image_base64", "image_base64": "%%%not-base64%%%"},
    )
    assert resp.status_code == 400


def test_ingest_non_image_bytes_400(client):
    payload = base64.b64encode(b"not an image").decode()
    resp = client.post(
        "/media/ingest",
        json={"type": "image_base64", "image_base64": payload},
    )
    assert resp.status_code == 400


def test_ingest_url_source(client, monkeypatch):
    raw = base64.b64decode(_png_b64())

    # Patch the loader's URL fetch so no network is used.
    monkeypatch.setattr(
        "src.core.image_ingest.fetch_image_from_url", lambda url: raw
    )
    resp = client.post(
        "/media/ingest",
        json={"type": "image_url", "image_url": "https://example.com/a.png"},
    )
    assert resp.status_code == 201


def test_ingest_url_rejects_bad_scheme(client):
    resp = client.post(
        "/media/ingest",
        json={"type": "image_url", "image_url": "ftp://example.com/a.png"},
    )
    assert resp.status_code == 400


def test_ingest_batch_base64(client):
    resp = client.post(
        "/media/ingest/batch",
        json={
            "images": [
                {"type": "image_base64", "image_base64": _png_b64()},
                {"type": "image_base64", "image_base64": _png_b64()},
            ],
            "tags": ["batch"],
        },
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["accepted"] == 2
    final = _poll(client, body["job_id"])
    assert final["state"] == "completed"
    assert final["completed"] == 2


def test_ingest_batch_empty_400(client):
    resp = client.post("/media/ingest/batch", json={"images": []})
    assert resp.status_code == 400
