# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for directory-ingest source paths, reference ingest and user metadata.

Covers the three generic capabilities added for consumers that share the ingest
mount with the service:

* ``source_path`` — the origin path recorded on every embedding.
* ``store_copy=false`` — reference media in place instead of copying it into the
  storage backend.
* caller-supplied metadata (request body + ``meta/<basename>.json`` sidecar)
  persisted as filterable fields.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import src.endpoints.video_processing.batch_ingest as batch_ep
from src.common import settings
from src.core.jobs.batch_jobs import reset_jobs
from src.core.vectorstores.metadata import project_to_canonical


@pytest.fixture
def ingest_root(tmp_path, monkeypatch):
    root = tmp_path / "ingest_root"
    (root / "meta").mkdir(parents=True)
    (root / "clip.mp4").write_bytes(b"fake-video-bytes")
    (root / "meta" / "clip.json").write_text(
        '{"tags": ["outdoor"], "camera": "cam-7", "capture_date": 20260101}'
    )
    monkeypatch.setattr(settings, "INGEST_DATA_ROOT", str(root))
    monkeypatch.setattr(settings, "INGEST_DATA_ROOT_HOST", "/host/data")
    return root


@pytest.fixture
def client(monkeypatch):
    """Client with storage and the heavy processor stubbed, capturing batch items."""
    fake_storage = MagicMock()
    fake_storage.ensure_bucket_exists.return_value = None
    fake_storage.upload_video.return_value = None
    monkeypatch.setattr(batch_ep, "get_minio_client", lambda: fake_storage)
    monkeypatch.setattr(batch_ep, "check_and_register_upload", lambda *a, **k: None)

    captured = []
    real_submit = batch_ep.submit_job

    def capturing_submit(source, items, processor):
        captured.extend(items)
        return real_submit(source, items, lambda item: 0)

    monkeypatch.setattr(batch_ep, "submit_job", capturing_submit)
    reset_jobs()

    from src.main import app

    with TestClient(app) as test_client:
        test_client.captured_items = captured
        test_client.fake_storage = fake_storage
        yield test_client
    reset_jobs()


def test_ingest_dir_records_host_source_path(client, ingest_root):
    resp = client.post("/media/ingest-dir", json={"dir_path": "."})

    assert resp.status_code == 202
    item = client.captured_items[0]
    assert item.source_path == "/host/data/clip.mp4"
    # Default behaviour still copies the media into the storage backend.
    assert item.local_path is None
    client.fake_storage.upload_video.assert_called_once()


def test_ingest_dir_store_copy_false_references_in_place(client, ingest_root):
    resp = client.post("/media/ingest-dir", json={"dir_path": ".", "store_copy": False})

    assert resp.status_code == 202
    item = client.captured_items[0]
    assert item.local_path == str(ingest_root / "clip.mp4")
    assert item.source_path == "/host/data/clip.mp4"
    client.fake_storage.upload_video.assert_not_called()


def test_ingest_dir_merges_sidecar_and_request_metadata(client, ingest_root):
    resp = client.post(
        "/media/ingest-dir",
        json={"dir_path": ".", "metadata": {"site": "plant-a", "camera": "ignored"}},
    )

    assert resp.status_code == 202
    item = client.captured_items[0]
    assert item.tags == ["outdoor"]
    assert item.custom_metadata["site"] == "plant-a"
    # The per-file sidecar is more specific and wins over request-level metadata.
    assert item.custom_metadata["camera"] == "cam-7"
    assert item.custom_metadata["capture_date"] == 20260101


def test_ingest_dir_rejects_unusable_metadata(client, ingest_root):
    resp = client.post(
        "/media/ingest-dir",
        json={
            "dir_path": ".",
            "metadata": {"bad key": "x", "nested": {"a": 1}, "ok_value": 3},
        },
    )

    assert resp.status_code == 202
    custom = client.captured_items[0].custom_metadata
    assert custom["ok_value"] == 3
    assert "bad key" not in custom
    assert "nested" not in custom


def test_custom_metadata_is_flattened_but_cannot_shadow_contract():
    projected = project_to_canonical(
        {
            "video_id": "vid-1",
            "source_path": "/host/data/clip.mp4",
            "shm": "transient",
            "custom_metadata": {"camera": "cam-7", "video_id": "spoofed"},
        }
    )

    assert projected["camera"] == "cam-7"
    assert projected["video_id"] == "vid-1"
    assert "shm" not in projected
    assert "custom_metadata" not in projected


def test_to_host_path_maps_only_under_the_ingest_root(monkeypatch, tmp_path):
    from src.core.utils.file_utils import to_host_path

    root = tmp_path / "ingest_root"
    root.mkdir()
    monkeypatch.setattr(settings, "INGEST_DATA_ROOT", str(root))
    monkeypatch.setattr(settings, "INGEST_DATA_ROOT_HOST", "/host/data")

    assert to_host_path(root / "a" / "b.mp4") == "/host/data/a/b.mp4"
    assert to_host_path("/elsewhere/b.mp4") == "/elsewhere/b.mp4"

    monkeypatch.setattr(settings, "INGEST_DATA_ROOT_HOST", "")
    assert to_host_path(root / "a" / "b.mp4") == str(root / "a" / "b.mp4")


def test_video_and_image_embeddings_declare_their_media_kind():
    from src.core.embedding.embedding_helper import FrameMetadata
    from src.core.embedding.embedding_orchestrator import _build_image_base_metadata

    assert FrameMetadata().to_dict()["content_type"] == "video"
    image_metadata = _build_image_base_metadata(
        bucket_name="b", video_id="v", filename="a.jpg", tags=[]
    )
    assert image_metadata["content_type"] == "image"


def test_ingest_dir_rejects_reserved_metadata_key(client, ingest_root):
    """A user key that collides with the canonical contract is rejected, not dropped."""
    resp = client.post(
        "/v1/dataprep/media/ingest-dir",
        json={"dir_path": ".", "metadata": {"timestamp": 20260101}},
    )
    assert resp.status_code == 400
    assert "reserved" in str(resp.json()).lower()


def test_ingest_dir_rejects_reserved_sidecar_key(client, ingest_root):
    """The same rule applies to per-file sidecars."""
    (ingest_root / "meta" / "clip.json").write_text('{"video_id": "spoofed"}')
    resp = client.post("/v1/dataprep/media/ingest-dir", json={"dir_path": "."})
    assert resp.status_code == 400


def test_ingest_dir_skips_duplicates_instead_of_failing(client, ingest_root, monkeypatch):
    """A duplicate is a per-file condition: the rest of the directory still ingests."""
    from http import HTTPStatus

    from src.common import DataPrepException

    (ingest_root / "clip2.mp4").write_bytes(b"other-video-bytes")

    seen = []

    def fake_check(storage, bucket, video_id, content):
        seen.append(content)
        if len(seen) == 1:
            raise DataPrepException(msg="duplicate", status_code=HTTPStatus.CONFLICT)
        return "hash"

    monkeypatch.setattr(batch_ep, "check_and_register_upload", fake_check)

    resp = client.post(
        "/v1/dataprep/media/ingest-dir", json={"dir_path": ".", "store_copy": False}
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["accepted"] == 1
    assert "1 duplicate file(s) skipped" in body["message"]
