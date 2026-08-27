# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Endpoint tests for ``DELETE /media/{bucket}[/{video_id}]``.

Each ``video_id`` directory holds exactly one video, so deletion is always a
whole-directory operation: it removes the object(s) from the active storage
backend AND the matching embeddings from the vector DB. Storage and vector-store
are faked and injected by monkeypatching the module-level factory functions used
by the endpoint.
"""

from http import HTTPStatus

import pytest

import src.endpoints.video_management.delete_video as delete_module
from src.core.storage.base import StorageObject


class FakeStorage:
    """Minimal storage double recording delete calls."""

    def __init__(self, objects, bucket_ok=True):
        # objects: mapping of video_id -> list of object filenames present
        self._objects = objects
        self._bucket_ok = bucket_ok
        self.deleted = []

    def bucket_exists(self, bucket_name):
        return self._bucket_ok

    def object_exists_by_path(self, bucket_name, object_name):
        return False

    def list_objects_in_directory(self, bucket_name, video_id):
        return [
            StorageObject(object_name=f"{video_id}/{name}")
            for name in self._objects.get(video_id, [])
        ]

    def list_all_videos(self, bucket_name):
        return [
            {"video_id": video_id, "video_name": name}
            for video_id, names in self._objects.items()
            for name in names
        ]

    def download_video_stream(self, bucket_name, object_name):
        return None

    def delete_object(self, bucket_name, object_name):
        self.deleted.append(object_name)


class FakeVectorStore:
    """Vector-store double recording delete_embeddings calls."""

    def __init__(self, fail=False):
        self.calls = []
        self._fail = fail

    def delete_embeddings(self, bucket_name, video_id):
        self.calls.append((bucket_name, video_id))
        if self._fail:
            raise RuntimeError("boom")
        return -1

    def delete_bucket_embeddings(self, bucket_name):
        self.calls.append((bucket_name,))
        if self._fail:
            raise RuntimeError("boom")
        return -1


@pytest.fixture
def wire(monkeypatch):
    """Return a helper that installs fake storage + vector store on the module."""

    def _install(storage, vector_store):
        monkeypatch.setattr(delete_module, "get_minio_client", lambda: storage)
        monkeypatch.setattr(delete_module, "get_vector_store", lambda: vector_store)

    return _install


def test_delete_removes_storage_and_vectors(test_client, wire):
    storage = FakeStorage({"vid1": ["clip.mp4"]})
    vs = FakeVectorStore()
    wire(storage, vs)

    resp = test_client.delete("/media/bucket1/vid1")
    assert resp.status_code == HTTPStatus.OK
    # Vectors deleted first, keyed by (bucket, video_id).
    assert vs.calls == [("bucket1", "vid1")]
    assert storage.deleted == ["vid1/clip.mp4"]


def test_delete_missing_bucket_returns_404_no_vector_delete(test_client, wire):
    storage = FakeStorage({}, bucket_ok=False)
    vs = FakeVectorStore()
    wire(storage, vs)

    resp = test_client.delete("/media/bucket1/vid1")
    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert vs.calls == []


def test_delete_empty_directory_returns_404(test_client, wire):
    storage = FakeStorage({"vid1": []})
    vs = FakeVectorStore()
    wire(storage, vs)

    resp = test_client.delete("/media/bucket1/vid1")
    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert vs.calls == []


def test_delete_aborts_storage_when_vector_delete_fails(test_client, wire):
    storage = FakeStorage({"vid1": ["clip.mp4"]})
    vs = FakeVectorStore(fail=True)
    wire(storage, vs)

    resp = test_client.delete("/media/bucket1/vid1")
    # Vector delete failure -> 502 and storage left untouched (no orphaned vectors).
    assert resp.status_code == HTTPStatus.BAD_GATEWAY
    assert storage.deleted == []


def test_delete_all_clears_bucket_storage_and_vectors(test_client, wire):
    storage = FakeStorage({"vid1": ["clip.mp4"], "vid2": ["image.jpg"]})
    vs = FakeVectorStore()
    wire(storage, vs)

    resp = test_client.delete("/media/bucket1")
    assert resp.status_code == HTTPStatus.OK
    # Vectors are cleared bucket-wide first, then every stored object is removed.
    assert vs.calls == [("bucket1",)]
    assert sorted(storage.deleted) == ["vid1/clip.mp4", "vid2/image.jpg"]


def test_delete_all_without_stored_objects_still_clears_vectors(test_client, wire):
    """Media ingested with store_copy=false has vectors but no stored bucket."""
    storage = FakeStorage({}, bucket_ok=False)
    vs = FakeVectorStore()
    wire(storage, vs)

    resp = test_client.delete("/media/bucket1")
    assert resp.status_code == HTTPStatus.OK
    assert vs.calls == [("bucket1",)]
    assert storage.deleted == []


def test_delete_all_empty_bucket_is_not_an_error(test_client, wire):
    storage = FakeStorage({})
    vs = FakeVectorStore()
    wire(storage, vs)

    resp = test_client.delete("/media/bucket1")
    assert resp.status_code == HTTPStatus.OK
    assert vs.calls == [("bucket1",)]
    assert storage.deleted == []


def test_delete_all_aborts_storage_when_vector_delete_fails(test_client, wire):
    storage = FakeStorage({"vid1": ["clip.mp4"]})
    vs = FakeVectorStore(fail=True)
    wire(storage, vs)

    resp = test_client.delete("/media/bucket1")
    assert resp.status_code == HTTPStatus.BAD_GATEWAY
    assert storage.deleted == []


class MarkerStorage(FakeStorage):
    """Storage holding only dedup markers, as left by a store_copy=false ingest."""

    def __init__(self, markers):
        super().__init__({})
        # markers: mapping of content hash -> owning video_id
        self._markers = markers

    def list_objects_in_directory(self, bucket_name, video_id):
        if video_id == ".dedup":
            return [StorageObject(object_name=f".dedup/{h}") for h in self._markers]
        if video_id in self._markers.values():
            return [StorageObject(object_name=f"{video_id}/.content_sha256")]
        return []

    def download_video_stream(self, bucket_name, object_name):
        import io

        content_hash = object_name.split("/", 1)[1]
        owner = self._markers.get(content_hash)
        return io.BytesIO(owner.encode("utf-8")) if owner else None


def test_delete_all_removes_markers_of_referenced_media(test_client, wire):
    """Referenced media leaves only content markers; the bucket clear removes them."""
    storage = MarkerStorage({"hash1": "vid1"})
    vs = FakeVectorStore()
    wire(storage, vs)

    resp = test_client.delete("/media/bucket1")
    assert resp.status_code == HTTPStatus.OK
    assert vs.calls == [("bucket1",)]
    assert ".dedup/hash1" in storage.deleted
    assert "vid1/.content_sha256" in storage.deleted
