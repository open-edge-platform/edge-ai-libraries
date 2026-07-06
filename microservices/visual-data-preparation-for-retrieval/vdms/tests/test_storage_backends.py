# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the pluggable storage abstraction (local + factory).

These tests intentionally avoid importing the FastAPI app so they exercise the
storage layer in isolation.
"""

import io

import pytest

from src.core.storage import BaseStorage, StorageObject, get_storage, reset_storage
from src.core.storage.local_storage import LocalStorage


@pytest.fixture
def local_storage(tmp_path):
    return LocalStorage(root_path=str(tmp_path / "store"))


def test_local_storage_is_base_storage(local_storage):
    assert isinstance(local_storage, BaseStorage)


def test_bucket_lifecycle(local_storage):
    assert local_storage.bucket_exists("b1") is False
    local_storage.ensure_bucket_exists("b1")
    assert local_storage.bucket_exists("b1") is True


def test_upload_download_roundtrip(local_storage):
    name = local_storage.compose_object_name("vid1", "clip.mp4")
    assert name == "vid1/clip.mp4"
    local_storage.upload_video("b1", name, io.BytesIO(b"hello"), 5)
    assert local_storage.object_exists_by_path("b1", name) is True
    assert local_storage.object_exists("b1", "vid1", "clip.mp4") is True
    assert local_storage.get_object_size("b1", name) == 5
    data = local_storage.download_video_stream("b1", name)
    assert data.read() == b"hello"


def test_listing_helpers(local_storage):
    name = local_storage.compose_object_name("vid1", "clip.mp4")
    local_storage.upload_video("b1", name, io.BytesIO(b"x"), 1)
    objs = local_storage.list_objects_in_directory("b1", "vid1")
    assert all(isinstance(o, StorageObject) for o in objs)
    assert any(o.object_name == "vid1/clip.mp4" for o in objs)

    assert local_storage.get_video_in_directory("b1", "vid1") == "vid1/clip.mp4"
    assert local_storage.get_video_in_directory("b1", "vid1", return_prefix=False) == "clip.mp4"

    videos = local_storage.list_all_videos("b1")
    assert len(videos) == 1
    assert videos[0]["video_id"] == "vid1"
    assert videos[0]["video_name"] == "clip.mp4"


def test_metadata_file_and_delete(local_storage):
    key = local_storage.save_metadata_file("b1", b"{}", "vid1")
    assert key == "vid1/metadata.json"
    assert local_storage.object_exists_by_path("b1", key) is True
    local_storage.delete_object("b1", key)
    assert local_storage.object_exists_by_path("b1", key) is False


def test_path_traversal_is_blocked(local_storage):
    with pytest.raises(ValueError):
        local_storage.compose_object_name("../etc", "passwd")
    with pytest.raises(ValueError):
        local_storage._resolve_object_path("b1", "../../escape.mp4")


def test_validate_object_name(local_storage):
    assert local_storage.validate_object_name("vid1", "clip.mp4") is True
    assert local_storage.validate_object_name("vid1", "clip.txt") is False
    assert local_storage.validate_object_name("", "clip.mp4") is False


def test_factory_selects_local(monkeypatch, tmp_path):
    from src.common import settings

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path / "fac"))
    reset_storage()
    try:
        store = get_storage()
        assert isinstance(store, LocalStorage)
        # cached singleton
        assert get_storage() is store
    finally:
        reset_storage()


def test_factory_rejects_unknown_backend(monkeypatch):
    from src.common import settings

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "bogus")
    reset_storage()
    try:
        with pytest.raises(ValueError):
            get_storage()
    finally:
        reset_storage()
