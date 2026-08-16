# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Endpoint tests for ``POST /media/process`` duplicate-upload rollback behavior."""

import io
from http import HTTPStatus
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import src.endpoints.video_processing.process_minio_video as process_ep
@pytest.fixture
def client(monkeypatch):
    fake_storage = MagicMock()
    fake_storage.ensure_bucket_exists.return_value = None
    fake_storage.delete_object.return_value = None

    monkeypatch.setattr(process_ep, "get_minio_client", lambda: fake_storage)
    monkeypatch.setattr(process_ep, "_resolve_stored_video_name", lambda **_: "clip.mp4")
    monkeypatch.setattr(
        process_ep,
        "get_video_from_minio",
        lambda *_, **__: (io.BytesIO(b"duplicate-bytes"), "clip.mp4"),
    )
    monkeypatch.setattr(
        process_ep,
        "read_config",
        lambda *_, **__: {
            "videos_local_temp_dir": "/tmp/dataprep/videos",
            "metadata_local_temp_dir": "/tmp/dataprep/metadata",
        },
    )
    monkeypatch.setattr(
        process_ep,
        "get_config",
        lambda: {"frame_interval": 15, "enable_object_detection": True, "detection_confidence": 0.85},
    )
    monkeypatch.setattr(process_ep, "sanitize_model", lambda model: model)
    monkeypatch.setattr(process_ep.settings, "ALLOW_DUPLICATE_UPLOADS", False)
    monkeypatch.setattr(process_ep, "compute_content_hash", lambda *_: "hash123")

    from src.main import app

    with TestClient(app) as c:
        yield c, fake_storage


def test_media_process_deletes_stored_object_on_duplicate(client):
    test_client, fake_storage = client
    process_ep.find_duplicate_video_id = lambda *_: "existing_vid"

    resp = test_client.post(
        "/media/process",
        json={"bucket_name": "test-bucket", "video_id": "vid_dup"},
    )

    assert resp.status_code == HTTPStatus.CONFLICT
    assert "identical content" in str(resp.json())
    fake_storage.delete_object.assert_called_once_with("test-bucket", "vid_dup/clip.mp4")


def test_media_process_keeps_existing_object_when_same_video_id(client):
    test_client, fake_storage = client
    process_ep.find_duplicate_video_id = lambda *_: "vid_dup"

    resp = test_client.post(
        "/media/process",
        json={"bucket_name": "test-bucket", "video_id": "vid_dup"},
    )

    assert resp.status_code == HTTPStatus.CONFLICT
    assert "vid_dup" in str(resp.json())
    fake_storage.delete_object.assert_not_called()
