# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Duplicate-upload policy tests for the batch job processor.

``POST /media/process/batch`` embeds media the caller already stored itself, so
its per-item processor is the only place the duplicate policy can be applied.
These tests cover :func:`src.core.jobs.processors._enforce_duplicate_policy`
directly (the surrounding processor does heavy embedding work that is out of
scope here) plus the job engine's per-item isolation guarantee.
"""

import io
from http import HTTPStatus

import pytest

import src.core.dedup as dedup
import src.core.jobs.processors as processors
from src.common import DataPrepException
from src.core.jobs.batch_jobs import BatchItem, BatchItemStatusEnum, BatchJob, _run_job


class InMemoryStorage:
    """Minimal storage double implementing only what the dedup helpers touch."""

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
def storage(monkeypatch):
    store = InMemoryStorage()
    monkeypatch.setattr(processors, "get_minio_client", lambda: store)
    return store


@pytest.fixture
def strict(monkeypatch):
    monkeypatch.setattr(processors.settings, "ALLOW_DUPLICATE_UPLOADS", False)
    monkeypatch.setattr(dedup.settings, "ALLOW_DUPLICATE_UPLOADS", False)


def test_registers_marker_for_first_seen_content(storage, strict):
    """/media/process/batch content is registered so later uploads can match it."""
    processors._enforce_duplicate_policy("bucket1", "vid1", b"clip-a")

    content_hash = dedup.compute_content_hash(b"clip-a")
    assert storage.objects[("bucket1", f"{dedup.DEDUP_PREFIX}/{content_hash}")] == b"vid1"


def test_rejects_content_owned_by_another_video(storage, strict):
    processors._enforce_duplicate_policy("bucket1", "vid1", b"clip-a")

    with pytest.raises(DataPrepException) as exc:
        processors._enforce_duplicate_policy("bucket1", "vid2", b"clip-a")

    assert exc.value.status_code == HTTPStatus.CONFLICT
    assert "vid1" in exc.value.message


def test_allows_reprocessing_the_same_video_id(storage, strict):
    """A marker owned by this very item is not a duplicate of anything.

    Guards the ``/media/upload/batch`` and ``/media/ingest-dir`` surfaces, which
    register the marker at submit time before the processor ever runs.
    """
    processors._enforce_duplicate_policy("bucket1", "vid1", b"clip-a")
    processors._enforce_duplicate_policy("bucket1", "vid1", b"clip-a")


def test_allows_distinct_content(storage, strict):
    processors._enforce_duplicate_policy("bucket1", "vid1", b"clip-a")
    processors._enforce_duplicate_policy("bucket1", "vid2", b"clip-b")


def test_scopes_duplicates_per_bucket(storage, strict):
    processors._enforce_duplicate_policy("bucket1", "vid1", b"clip-a")
    processors._enforce_duplicate_policy("bucket2", "vid2", b"clip-a")


def test_permissive_mode_never_rejects_but_still_registers(storage, monkeypatch):
    monkeypatch.setattr(processors.settings, "ALLOW_DUPLICATE_UPLOADS", True)
    monkeypatch.setattr(dedup.settings, "ALLOW_DUPLICATE_UPLOADS", True)

    processors._enforce_duplicate_policy("bucket1", "vid1", b"clip-a")
    processors._enforce_duplicate_policy("bucket1", "vid2", b"clip-a")

    content_hash = dedup.compute_content_hash(b"clip-a")
    assert storage.object_exists_by_path("bucket1", f"{dedup.DEDUP_PREFIX}/{content_hash}")


def test_process_stored_video_rejects_duplicate_before_embedding(storage, strict, monkeypatch):
    """The check is wired into the processor itself and runs before embedding."""
    embedded = []

    monkeypatch.setattr(
        processors,
        "read_config",
        lambda *_, **__: {"metadata_local_temp_dir": "/tmp/dataprep/metadata"},
    )
    monkeypatch.setattr(
        processors,
        "get_video_from_minio",
        lambda *_, **__: (io.BytesIO(b"clip-a"), "clip.mp4"),
    )

    async def fake_embed(**kwargs):
        embedded.append(kwargs["video_id"])
        return ["id1", "id2"]

    monkeypatch.setattr(processors, "generate_video_embedding_from_content", fake_embed)

    # First item is new: it embeds and registers ownership of the content.
    assert processors.process_stored_video(
        BatchItem(identifier="a", bucket_name="bucket1", video_id="vid1")
    ) == 2
    assert embedded == ["vid1"]

    # A different video_id carrying the same bytes is rejected, and the expensive
    # embedding call is never reached.
    with pytest.raises(DataPrepException) as exc:
        processors.process_stored_video(
            BatchItem(identifier="b", bucket_name="bucket1", video_id="vid2")
        )
    assert exc.value.status_code == HTTPStatus.CONFLICT
    assert embedded == ["vid1"]


def test_duplicate_item_does_not_disrupt_the_rest_of_the_batch(storage, strict):
    """One duplicate fails its own item only; the unique items still succeed."""
    contents = {"dup_a": b"clip-a", "unique_b": b"clip-b", "dup_c": b"clip-a"}
    processors._enforce_duplicate_policy("bucket1", "owner_of_a", b"clip-a")

    def processor(item: BatchItem) -> int:
        processors._enforce_duplicate_policy(item.bucket_name, item.video_id, contents[item.video_id])
        return 7

    items = [
        BatchItem(identifier=vid, bucket_name="bucket1", video_id=vid) for vid in contents
    ]
    job = BatchJob(job_id="job1", source="batch_existing", items=items)
    _run_job(job, processor)

    by_id = {item.video_id: item for item in job.items}
    assert by_id["dup_a"].status == BatchItemStatusEnum.error
    assert by_id["dup_c"].status == BatchItemStatusEnum.error
    assert by_id["unique_b"].status == BatchItemStatusEnum.success
    assert by_id["unique_b"].embeddings_count == 7
    assert "identical content" in (by_id["dup_a"].message or "")
