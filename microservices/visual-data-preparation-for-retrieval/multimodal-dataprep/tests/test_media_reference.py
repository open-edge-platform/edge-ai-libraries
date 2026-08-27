# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for serving media ingested by reference (``store_copy=false``).

Referenced media has no object in the storage backend, only a path sidecar
pointing at the file on the ingest mount. These tests exercise the real local
storage backend and the real filesystem so that listing, full download, HTTP
Range download and the security boundary are all verified end to end.
"""

import io
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from src.common import settings
from src.core.media_ref import SOURCE_REF_SIDECAR, register_source_ref
from src.core.dedup import register_upload, compute_content_hash
from src.core.storage import get_storage, reset_storage

_BUCKET = "ref-bucket"
_VIDEO_ID = "vid-ref"
_VIDEO_NAME = "referenced.mp4"
_CONTENT = bytes(range(256)) * 8  # 2048 deterministic bytes


@pytest.fixture
def client(monkeypatch, tmp_path):
    """App wired to local storage, with one media file ingested by reference."""
    ingest_root = tmp_path / "ingest"
    (ingest_root / "cam1").mkdir(parents=True)
    media_file = ingest_root / "cam1" / _VIDEO_NAME
    media_file.write_bytes(_CONTENT)

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path / "store"))
    monkeypatch.setattr(settings, "DEFAULT_BUCKET_NAME", _BUCKET)
    monkeypatch.setattr(settings, "INGEST_DATA_ROOT", str(ingest_root))
    monkeypatch.setattr(settings, "INGEST_DATA_ROOT_HOST", "/host/data")
    reset_storage()

    storage = get_storage()
    storage.ensure_bucket_exists(_BUCKET)
    # Exactly what a store_copy=false ingest writes: markers only, no object.
    register_upload(storage, _BUCKET, _VIDEO_ID, compute_content_hash(_CONTENT))
    register_source_ref(storage, _BUCKET, _VIDEO_ID, media_file)

    from src.main import app

    with TestClient(app) as c:
        c.media_file = media_file
        yield c
    reset_storage()


def test_sidecar_stores_ingest_relative_path(client):
    storage = get_storage()
    stream = storage.download_video_stream(_BUCKET, f"{_VIDEO_ID}/{SOURCE_REF_SIDECAR}")
    assert stream.read().decode() == f"cam1/{_VIDEO_NAME}"


def test_no_object_is_stored(client):
    assert get_storage().get_video_in_directory(_BUCKET, _VIDEO_ID) is None


def test_full_download_of_referenced_media(client):
    resp = client.get(f"/media/download?video_id={_VIDEO_ID}")
    assert resp.status_code == HTTPStatus.OK
    assert resp.headers["accept-ranges"] == "bytes"
    assert resp.headers["content-length"] == str(len(_CONTENT))
    assert resp.headers["content-type"].startswith("video/mp4")
    assert f"inline; filename={_VIDEO_NAME}" in resp.headers["content-disposition"]
    assert resp.content == _CONTENT


def test_range_request_on_referenced_media(client):
    resp = client.get(
        f"/media/download?video_id={_VIDEO_ID}",
        headers={"Range": "bytes=64-127"},
    )
    assert resp.status_code == HTTPStatus.PARTIAL_CONTENT
    assert resp.headers["content-range"] == f"bytes 64-127/{len(_CONTENT)}"
    assert resp.content == _CONTENT[64:128]


def test_suffix_range_on_referenced_media(client):
    resp = client.get(
        f"/media/download?video_id={_VIDEO_ID}", headers={"Range": "bytes=-16"}
    )
    assert resp.status_code == HTTPStatus.PARTIAL_CONTENT
    assert resp.content == _CONTENT[-16:]


def test_unsatisfiable_range_on_referenced_media(client):
    resp = client.get(
        f"/media/download?video_id={_VIDEO_ID}",
        headers={"Range": f"bytes={len(_CONTENT) + 10}-"},
    )
    assert resp.status_code == HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE


def test_forced_download_sets_attachment(client):
    resp = client.get(f"/media/download?video_id={_VIDEO_ID}&download=true")
    assert resp.status_code == HTTPStatus.OK
    assert f"attachment; filename={_VIDEO_NAME}" in resp.headers["content-disposition"]


def test_listing_includes_referenced_media(client):
    resp = client.get(f"/media?bucket_name={_BUCKET}")
    assert resp.status_code == HTTPStatus.OK
    videos = resp.json()["videos"]
    assert len(videos) == 1
    entry = videos[0]
    assert entry["video_id"] == _VIDEO_ID
    assert entry["video_name"] == _VIDEO_NAME
    assert entry["stored"] is False
    # Host-visible path, so a consumer sharing the mount can read it directly.
    assert entry["source_path"] == f"/host/data/cam1/{_VIDEO_NAME}"


def test_stored_media_is_flagged_as_stored(client):
    storage = get_storage()
    object_name = storage.compose_object_name("vid-stored", "copy.mp4")
    storage.upload_video(_BUCKET, object_name, io.BytesIO(_CONTENT), len(_CONTENT))

    videos = client.get(f"/media?bucket_name={_BUCKET}").json()["videos"]
    stored = [v for v in videos if v["video_id"] == "vid-stored"]
    assert len(stored) == 1
    assert stored[0]["stored"] is True
    # Null fields are stripped by response_model_exclude_none.
    assert stored[0].get("source_path") is None


def test_dangling_reference_is_not_listed_and_404s(client):
    client.media_file.unlink()

    assert client.get(f"/media?bucket_name={_BUCKET}").json()["videos"] == []
    resp = client.get(f"/media/download?video_id={_VIDEO_ID}")
    assert resp.status_code == HTTPStatus.NOT_FOUND


def test_sidecar_escaping_ingest_root_is_rejected(client, tmp_path):
    """A tampered sidecar cannot be used to read outside the ingest mount."""
    outside = tmp_path / "secret.mp4"
    outside.write_bytes(b"do not serve me")

    storage = get_storage()
    storage.save_metadata_file(
        _BUCKET, b"../secret.mp4", _VIDEO_ID, SOURCE_REF_SIDECAR
    )

    resp = client.get(f"/media/download?video_id={_VIDEO_ID}")
    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert client.get(f"/media?bucket_name={_BUCKET}").json()["videos"] == []
