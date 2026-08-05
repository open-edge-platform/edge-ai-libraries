# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for the seekable ``/media/download`` endpoint.

These exercise the endpoint end-to-end against the real local filesystem
storage backend so HTTP Range (206), full download (200), and unsatisfiable
range (416) behaviour is verified without mocking the storage layer.
"""

import io
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from src.common import settings
from src.core.storage import get_storage, reset_storage

_BUCKET = "test-bucket"
_VIDEO_ID = "vid-download"
_VIDEO_NAME = "clip.mp4"
_CONTENT = bytes(range(256)) * 16  # 4096 deterministic bytes


@pytest.fixture
def client(monkeypatch, tmp_path):
    """App wired to a local storage backend seeded with one known video."""
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path / "store"))
    monkeypatch.setattr(settings, "DEFAULT_BUCKET_NAME", _BUCKET)
    reset_storage()

    storage = get_storage()
    object_name = storage.compose_object_name(_VIDEO_ID, _VIDEO_NAME)
    storage.upload_video(_BUCKET, object_name, io.BytesIO(_CONTENT), len(_CONTENT))

    from src.main import app

    with TestClient(app) as c:
        yield c
    reset_storage()


def test_full_download_advertises_ranges(client):
    resp = client.get(f"/media/download?video_id={_VIDEO_ID}")
    assert resp.status_code == HTTPStatus.OK
    assert resp.headers["accept-ranges"] == "bytes"
    assert resp.headers["content-length"] == str(len(_CONTENT))
    assert resp.content == _CONTENT


def test_range_returns_partial_content(client):
    resp = client.get(
        f"/media/download?video_id={_VIDEO_ID}",
        headers={"Range": "bytes=100-199"},
    )
    assert resp.status_code == HTTPStatus.PARTIAL_CONTENT
    assert resp.headers["content-range"] == f"bytes 100-199/{len(_CONTENT)}"
    assert resp.headers["content-length"] == "100"
    assert resp.headers["accept-ranges"] == "bytes"
    assert resp.content == _CONTENT[100:200]


def test_open_ended_range(client):
    start = len(_CONTENT) - 10
    resp = client.get(
        f"/media/download?video_id={_VIDEO_ID}",
        headers={"Range": f"bytes={start}-"},
    )
    assert resp.status_code == HTTPStatus.PARTIAL_CONTENT
    assert resp.headers["content-range"] == f"bytes {start}-{len(_CONTENT) - 1}/{len(_CONTENT)}"
    assert resp.content == _CONTENT[start:]


def test_suffix_range(client):
    resp = client.get(
        f"/media/download?video_id={_VIDEO_ID}",
        headers={"Range": "bytes=-50"},
    )
    assert resp.status_code == HTTPStatus.PARTIAL_CONTENT
    assert resp.content == _CONTENT[-50:]


def test_unsatisfiable_range_returns_416(client):
    resp = client.get(
        f"/media/download?video_id={_VIDEO_ID}",
        headers={"Range": f"bytes={len(_CONTENT) + 10}-"},
    )
    assert resp.status_code == HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE
    assert resp.headers["content-range"] == f"bytes */{len(_CONTENT)}"


def test_invalid_range_header_serves_full_body(client):
    resp = client.get(
        f"/media/download?video_id={_VIDEO_ID}",
        headers={"Range": "rows=0-10"},
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.content == _CONTENT


def test_download_flag_sets_attachment(client):
    resp = client.get(f"/media/download?video_id={_VIDEO_ID}&download=true")
    assert resp.status_code == HTTPStatus.OK
    assert resp.headers["content-disposition"].startswith("attachment;")


def test_download_not_found_returns_404(client):
    resp = client.get("/media/download?video_id=does-not-exist")
    assert resp.status_code == HTTPStatus.NOT_FOUND
