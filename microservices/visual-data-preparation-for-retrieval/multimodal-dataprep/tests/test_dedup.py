# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for content-based duplicate-upload detection (``src.core.dedup``).

Uses an in-memory storage double implementing only the backend methods the dedup
helpers touch, so the tests are independent of MinIO / local filesystem storage.
"""

import io
from http import HTTPStatus

import pytest

import src.core.dedup as dedup
from src.common import DataPrepException


class InMemoryStorage:
    """Minimal storage double backed by a dict of ``object_name -> bytes``."""

    def __init__(self):
        self.objects = {}

    def save_metadata_file(self, bucket_name, metadata_content, video_id, filename="metadata.json"):
        object_name = f"{video_id}/{filename}"
        self.objects[(bucket_name, object_name)] = bytes(metadata_content)
        return object_name

    def object_exists_by_path(self, bucket_name, object_name):
        return (bucket_name, object_name) in self.objects

    def download_video_stream(self, bucket_name, object_name):
        if (bucket_name, object_name) not in self.objects:
            return None
        return io.BytesIO(self.objects[(bucket_name, object_name)])

    def delete_object(self, bucket_name, object_name):
        self.objects.pop((bucket_name, object_name), None)


@pytest.fixture
def storage():
    return InMemoryStorage()


def test_compute_content_hash_is_deterministic():
    assert dedup.compute_content_hash(b"abc") == dedup.compute_content_hash(b"abc")
    assert dedup.compute_content_hash(b"abc") != dedup.compute_content_hash(b"abd")
    # Known SHA-256 of b"abc".
    assert dedup.compute_content_hash(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_register_writes_forward_and_reverse_markers(storage):
    content_hash = dedup.compute_content_hash(b"video-bytes")
    dedup.register_upload(storage, "bucket1", "vid1", content_hash)

    forward = f"{dedup.DEDUP_PREFIX}/{content_hash}"
    reverse = f"vid1/{dedup.CONTENT_HASH_SIDECAR}"
    assert storage.objects[("bucket1", forward)] == b"vid1"
    assert storage.objects[("bucket1", reverse)] == content_hash.encode()


def test_find_duplicate_returns_none_when_absent(storage):
    assert dedup.find_duplicate_video_id(storage, "bucket1", "deadbeef") is None


def test_find_duplicate_returns_owner_after_register(storage):
    content_hash = dedup.compute_content_hash(b"payload")
    dedup.register_upload(storage, "bucket1", "vid42", content_hash)
    assert dedup.find_duplicate_video_id(storage, "bucket1", content_hash) == "vid42"


def test_check_allows_duplicate_when_flag_true(storage, monkeypatch):
    monkeypatch.setattr(dedup.settings, "ALLOW_DUPLICATE_UPLOADS", True)
    content = b"same-content"
    dedup.check_and_register_upload(storage, "bucket1", "vid1", content)
    # A second identical upload is permitted and simply re-registers.
    returned = dedup.check_and_register_upload(storage, "bucket1", "vid2", content)
    assert returned == dedup.compute_content_hash(content)


def test_check_rejects_duplicate_when_flag_false(storage, monkeypatch):
    monkeypatch.setattr(dedup.settings, "ALLOW_DUPLICATE_UPLOADS", False)
    content = b"unique-1"
    dedup.check_and_register_upload(storage, "bucket1", "vid1", content)

    with pytest.raises(DataPrepException) as exc:
        dedup.check_and_register_upload(storage, "bucket1", "vid2", content)
    assert exc.value.status_code == HTTPStatus.CONFLICT
    assert "vid1" in exc.value.message


def test_check_rejects_same_video_id_when_flag_false(storage, monkeypatch):
    monkeypatch.setattr(dedup.settings, "ALLOW_DUPLICATE_UPLOADS", False)
    content = b"same-owner-reprocess"
    dedup.check_and_register_upload(storage, "bucket1", "vid1", content)
    with pytest.raises(DataPrepException) as exc:
        dedup.check_and_register_upload(storage, "bucket1", "vid1", content)
    assert exc.value.status_code == HTTPStatus.CONFLICT
    assert "vid1" in exc.value.message


def test_check_allows_distinct_content_when_flag_false(storage, monkeypatch):
    monkeypatch.setattr(dedup.settings, "ALLOW_DUPLICATE_UPLOADS", False)
    dedup.check_and_register_upload(storage, "bucket1", "vid1", b"content-a")
    # Different bytes are not a duplicate.
    dedup.check_and_register_upload(storage, "bucket1", "vid2", b"content-b")


def test_check_scopes_duplicates_per_bucket(storage, monkeypatch):
    monkeypatch.setattr(dedup.settings, "ALLOW_DUPLICATE_UPLOADS", False)
    content = b"cross-bucket"
    dedup.check_and_register_upload(storage, "bucket1", "vid1", content)
    # Same content in a different bucket is independent (marker is per-bucket path).
    dedup.check_and_register_upload(storage, "bucket2", "vid2", content)


def test_remove_marker_allows_reupload(storage, monkeypatch):
    monkeypatch.setattr(dedup.settings, "ALLOW_DUPLICATE_UPLOADS", False)
    content = b"reupload-me"
    dedup.check_and_register_upload(storage, "bucket1", "vid1", content)

    # Simulate deleting vid1: cleanup marker, then remove the video's objects.
    dedup.remove_dedup_marker(storage, "bucket1", "vid1")
    content_hash = dedup.compute_content_hash(content)
    assert ("bucket1", f"{dedup.DEDUP_PREFIX}/{content_hash}") not in storage.objects

    # Re-uploading the same content is now allowed again.
    dedup.check_and_register_upload(storage, "bucket1", "vid3", content)


def test_remove_marker_is_noop_when_sidecar_missing(storage):
    # No sidecar registered; must not raise.
    dedup.remove_dedup_marker(storage, "bucket1", "ghost")
