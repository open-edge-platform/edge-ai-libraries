# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Object storage on the filesystem, and the content store over it."""

import os
import tempfile

import pytest

from assetlib.content import ContentStore, asset_key, blob_key
from assetlib.contracts import Source
from databasehub.adapters.filesystem import FilesystemObjectAdapter
from databasehub.adapters.object import ObjectAdapter
from databasehub.models import ObjectCollection, VectorCollection

BUCKET = ObjectCollection("library-1")


def _adapter():
    return FilesystemObjectAdapter({"root": tempfile.mkdtemp()})


# --- the adapter --------------------------------------------------------------


def test_it_implements_the_object_contract():
    assert issubclass(FilesystemObjectAdapter, ObjectAdapter)
    assert isinstance(_adapter(), ObjectAdapter)


def test_a_root_is_required():
    with pytest.raises(ValueError):
        FilesystemObjectAdapter({})


def test_put_then_get_round_trips():
    adapter = _adapter()
    adapter.ensure(BUCKET)

    adapter.put(BUCKET, "assets/a1.json", b'{"hello": 1}')

    assert adapter.get(BUCKET, "assets/a1.json") == b'{"hello": 1}'
    assert adapter.exists(BUCKET, "assets/a1.json")


def test_a_missing_key_raises_key_error():
    adapter = _adapter()
    adapter.ensure(BUCKET)

    assert not adapter.exists(BUCKET, "assets/nope.json")
    with pytest.raises(KeyError):
        adapter.get(BUCKET, "assets/nope.json")


def test_put_creates_intermediate_directories():
    adapter = _adapter()

    adapter.put(BUCKET, "blobs/deep/nested/key", b"x")

    assert adapter.get(BUCKET, "blobs/deep/nested/key") == b"x"


def test_put_replaces_atomically_and_leaves_no_partials():
    adapter = _adapter()
    adapter.put(BUCKET, "k", b"first")
    adapter.put(BUCKET, "k", b"second")

    assert adapter.get(BUCKET, "k") == b"second"
    assert adapter.list(BUCKET) == ["k"], "no .put.*.tmp left behind"


def test_list_returns_keys_relative_to_the_collection():
    adapter = _adapter()
    for key in ("assets/a1.json", "assets/a2.json", "blobs/abc"):
        adapter.put(BUCKET, key, b"x")

    assert adapter.list(BUCKET) == ["assets/a1.json", "assets/a2.json", "blobs/abc"]
    assert adapter.list(BUCKET, "assets") == ["assets/a1.json", "assets/a2.json"]


def test_a_prefixed_collection_scopes_keys():
    adapter = _adapter()
    prefixed = ObjectCollection("library-1", "tenant-a")

    adapter.put(prefixed, "k", b"x")

    assert adapter.get(prefixed, "k") == b"x"
    assert adapter.list(prefixed) == ["k"]
    # The same key in an unprefixed view of the bucket is a different object.
    assert not adapter.exists(ObjectCollection("library-1"), "k")


def test_delete_is_idempotent():
    adapter = _adapter()
    adapter.put(BUCKET, "k", b"x")

    adapter.delete(BUCKET, "k")
    adapter.delete(BUCKET, "k")

    assert not adapter.exists(BUCKET, "k")


def test_clear_empties_the_bucket():
    adapter = _adapter()
    adapter.put(BUCKET, "a", b"x")
    adapter.put(BUCKET, "b", b"y")

    adapter.clear(BUCKET)

    assert adapter.list(BUCKET) == []


@pytest.mark.parametrize(
    "key", ["../escape", "a/../../escape", "/etc/passwd", "a/../../../etc/passwd"]
)
def test_a_key_cannot_escape_its_bucket(key):
    """Keys come out of persisted records, so traversal must be refused."""
    adapter = _adapter()

    with pytest.raises(ValueError):
        adapter.put(BUCKET, key, b"x")


def test_an_empty_key_is_refused():
    with pytest.raises(ValueError):
        _adapter().put(BUCKET, "", b"x")


# --- the content store --------------------------------------------------------


class StubHub:
    """Just enough databasehub to resolve one object adapter."""

    def __init__(self, adapter):
        self.adapter = adapter

    def get_object_adapter(self, database_id):
        return self.adapter


def _store():
    adapter = _adapter()
    source = Source(
        source_id="content-1",
        name="content",
        source_type="object",
        database_id="default-object",
        location=BUCKET,
    )
    return ContentStore(StubHub(adapter)), source, adapter


def test_blobs_are_content_addressed_and_written_once():
    store, source, adapter = _store()

    first = store.put_blob(source, b"figure-bytes")
    second = store.put_blob(source, b"figure-bytes")

    assert first == second == blob_key(b"figure-bytes")
    assert store.get_blob(source, first) == b"figure-bytes"
    assert adapter.list(BUCKET) == [first], "identical bytes share one object"


def test_different_bytes_get_different_keys():
    store, source, _ = _store()

    assert store.put_blob(source, b"a") != store.put_blob(source, b"b")


def test_records_round_trip_as_json():
    store, source, _ = _store()
    record = {"asset_id": "a1", "blocks": [{"block_id": "a1:0", "text": "hi"}]}

    key = store.put_record(source, asset_key("a1"), record)

    assert key == "assets/a1.json"
    assert store.get_record(source, key) == record


def test_a_record_is_overwritten_in_place():
    """Re-extracting an asset replaces its stream rather than accumulating."""
    store, source, adapter = _store()

    store.put_record(source, asset_key("a1"), {"asset_id": "a1", "blocks": []})
    store.put_record(source, asset_key("a1"), {"asset_id": "a1", "blocks": [1]})

    assert adapter.list(BUCKET) == ["assets/a1.json"]
    assert store.get_record(source, asset_key("a1"))["blocks"] == [1]


def test_content_needs_an_object_source():
    """A vector source is a materialization target, not somewhere bytes live."""
    store, _, _ = _store()
    vector_source = Source(
        source_id="v1",
        source_type="vector",
        database_id="default-vector",
        location=VectorCollection("docs", 8),
    )

    with pytest.raises(TypeError):
        store.put_blob(vector_source, b"x")


def test_live_keys_reports_everything_stored():
    store, source, _ = _store()
    store.put_record(source, asset_key("a1"), {"asset_id": "a1"})
    blob = store.put_blob(source, b"bytes")

    assert store.live_keys(source) == {"assets/a1.json", blob}
