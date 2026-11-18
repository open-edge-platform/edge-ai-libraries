# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Asset content lives in a source, not in the library record.

The point of the content store is that `asset_library.json` stops carrying the
corpus: a saved library holds references, and the text is read back through the
source it was written to. These tests assert both halves.
"""

import tempfile

import pytest

from assetlib.content import asset_key
from core.content import IMAGE, TEXT, ContentBlock, ContentStream
from core.file_asset_library import (
    FileAsset,
    FileAssetLibrary,
    file_origin,
)
from . import dbhub
from llama_index.core.schema import Document


class StubLibrary(FileAssetLibrary):
    def build_projection(self, projection_id, name, source):
        raise AssertionError("these tests do not materialize")


def _library(hub=None):
    return StubLibrary(name="library", databasehub=hub or dbhub.object_hub())


def _stream(asset_id="a1", text="hello world"):
    return ContentStream(
        asset_id=asset_id,
        blocks=[ContentBlock(block_id=f"{asset_id}:0", kind=TEXT, text=text)],
        metadata={"file_name": "a.pdf", "file_path": "/w/a.pdf", "asset_id": asset_id},
    )


# --- the content source is a source like any other ----------------------------


def test_the_content_source_is_created_on_first_use():
    library = _library()

    assert library.sources == {}

    source = library.content_source()

    assert source.source_type == "object"
    assert source.name == "content"
    assert library.sources[source.source_id] is source
    # The pointer is the record of the choice. It used to be a `content_database`
    # field beside the sources, which meant the same fact in two places.
    assert library.default_content_source_id == source.source_id
    assert library.content_database == source.database_id


def test_the_content_source_is_created_only_once():
    library = _library()

    first = library.content_source()
    second = library.content_source()

    assert first is second
    assert len(library.sources) == 1


def test_the_content_source_is_named_for_the_library():
    library = _library()

    source = library.content_source()

    assert source.location.bucket == library.library_id


def test_content_database_is_derived_from_the_source_not_stored():
    """A content source registered any other way still reports correctly.

    This is what the separate field got wrong: `POST /{library}/sources` stored
    content perfectly well while the library reported no content database.
    """
    library = _library()
    hand_registered = library.create_source(
        name="archive", database_id=dbhub.OBJECT_DATABASE, collection_name="shared"
    )

    assert library.content_database == "", "not the default until it is adopted"

    library.adopt_content_source(hand_registered.source_id)

    assert library.content_source() is hand_registered
    assert library.content_database == dbhub.OBJECT_DATABASE
    assert len(library.sources) == 1, "no second source was invented"


# --- one library, several content sources -------------------------------------


def _second_object_database(hub, database_id="cold-storage"):
    hub.register(
        database_id,
        database_type="object",
        backend="filesystem",
        options={"root": tempfile.mkdtemp()},
    )
    return database_id


def test_an_asset_can_be_written_to_a_source_other_than_the_default():
    hub = dbhub.object_hub()
    library = _library(hub)
    default = library.content_source()
    cold = library.create_source(
        name="cold", database_id=_second_object_database(hub), collection_name="cold"
    )

    asset = library.create_asset(
        origin=file_origin("/w/a.pdf"), stream=_stream(), source_id=cold.source_id
    )

    assert asset.content_source_id == cold.source_id
    assert library.content_store.exists(cold, asset.content_key)
    assert not library.content_store.exists(default, asset.content_key)
    assert library.default_content_source_id == default.source_id, "unmoved"


def test_moving_the_default_leaves_stored_assets_readable():
    """The reason repointing is allowed at all: an asset names its own source."""
    hub = dbhub.object_hub()
    library = _library(hub)
    asset = library.create_asset(origin=file_origin("/w/a.pdf"), stream=_stream())
    library.register_assets([asset])
    first_source_id = library.default_content_source_id

    cold = library.create_source(
        name="cold", database_id=_second_object_database(hub), collection_name="cold"
    )
    library.update(default_content_source_id=cold.source_id)

    assert library.content_source() is cold
    assert asset.content_source_id == first_source_id
    assert library.assets["a1"].content.text() == "hello world"


def test_re_ingesting_into_another_source_does_not_leave_the_old_record():
    """Asset ids are stable, so the old record would have nothing pointing at it."""
    hub = dbhub.object_hub()
    library = _library(hub)
    first = library.create_asset(origin=file_origin("/w/a.pdf"), stream=_stream())
    library.register_assets([first])
    old_source = library.sources[first.content_source_id]
    cold = library.create_source(
        name="cold", database_id=_second_object_database(hub), collection_name="cold"
    )

    moved = library.create_asset(
        origin=file_origin("/w/a.pdf"),
        stream=_stream(text="replaced"),
        source_id=cold.source_id,
    )
    library.register_assets([moved])

    assert moved.asset_id == first.asset_id, "the same file is the same asset"
    assert not library.content_store.exists(old_source, first.content_key)
    assert library.content_store.exists(cold, moved.content_key)
    assert library.assets["a1"].content.text() == "replaced"


def test_a_source_holding_content_cannot_be_detached():
    """Its assets read through it, so forgetting it would make them raise."""
    library = _library()
    asset = library.create_asset(origin=file_origin("/w/a.pdf"), stream=_stream())
    library.register_assets([asset])

    with pytest.raises(ValueError) as caught:
        library.detach_source(asset.content_source_id)

    assert "cannot be detached" in str(caught.value)
    assert asset.content_source_id in library.sources


def test_detaching_the_default_once_it_is_empty_clears_the_pointer():
    library = _library()
    source = library.content_source()

    assert library.detach_source(source.source_id) is True
    assert library.default_content_source_id == ""
    # ...and the next ingest adopts one again rather than staying broken.
    assert library.content_source().source_id != source.source_id


def test_content_needs_an_object_source():
    library = _library(dbhub.with_vector(dbhub.object_hub()))
    library.create_source(
        name="vectors", database_id=dbhub.VECTOR_DATABASE, collection_name="chunks"
    )
    vector_source_id = next(
        source_id
        for source_id, source in library.sources.items()
        if source.source_type == "vector"
    )

    with pytest.raises(ValueError) as caught:
        library.content_source(vector_source_id)

    assert "object" in str(caught.value)


# --- assets hold references, not content --------------------------------------


def test_creating_an_asset_writes_its_content_and_keeps_a_reference():
    library = _library()

    asset = library.create_asset(
        origin=file_origin("/w/a.pdf"), stream=_stream()
    )

    assert asset.content_key == asset_key("a1")
    assert asset.content_source_id == library.content_source().source_id
    stored = library.content_store.get_record(
        library.content_source(), asset.content_key
    )
    assert stored["blocks"][0]["text"] == "hello world"


def test_the_saved_record_carries_no_content():
    """This is the whole point: the corpus is not in asset_library.json."""
    library = _library()
    library.register_assets(
        [library.create_asset(origin=file_origin("/w/a.pdf"), stream=_stream())]
    )

    record = library.to_record()
    asset_record = record["assets"][0]

    assert set(asset_record) == {
        "asset_id",
        "origin",
        "asset_kind",
        "content_source_id",
        "content_key",
    }
    assert asset_record["asset_kind"] == "document"
    assert "hello world" not in str(record)


def test_content_is_read_back_through_the_source():
    library = _library()
    asset = library.create_asset(
        origin=file_origin("/w/a.pdf"), stream=_stream()
    )
    library.register_assets([asset])

    restored = StubLibrary.from_record(library.to_record(), databasehub=library._databasehub)

    # The reference resolves, and only when something asks for it.
    reloaded = restored.assets["a1"]
    assert reloaded.cached is None, "not read at restore"
    assert reloaded.content.text() == "hello world"
    assert reloaded.cached is not None, "cached after the first read"


def test_the_content_stream_is_the_only_view_of_an_assets_content():
    """There is no `.document`: joining the blocks lost pages and figures."""
    library = _library()
    asset = library.create_asset(
        origin=file_origin("/w/a.pdf"), stream=_stream()
    )

    assert not hasattr(asset, "document")
    assert asset.content.text() == "hello world"
    # The metadata a chunk is later deleted by has to survive.
    assert asset.content.metadata["file_path"] == "/w/a.pdf"
    assert asset.content.metadata["asset_id"] == "a1"


def test_an_asset_with_no_loader_and_no_content_is_an_error():
    with pytest.raises(ValueError):
        FileAsset(asset_id="a1", origin="file:///w/a.pdf").content


# --- reading order, figures, and layout ---------------------------------------


def test_text_is_joined_in_reading_order():
    stream = ContentStream(
        asset_id="a1",
        blocks=[
            ContentBlock(block_id="b2", text="second", reading_order=2),
            ContentBlock(block_id="b1", text="first", reading_order=1),
        ],
    )

    assert stream.text() == "first\n\nsecond"


def test_a_figure_keeps_its_caption_as_a_field_not_a_block():
    stream = ContentStream(
        asset_id="a1",
        blocks=[
            ContentBlock(block_id="b1", kind=TEXT, text="body", reading_order=0),
            ContentBlock(
                block_id="b2",
                kind=IMAGE,
                media_key="blobs/abc",
                caption="Figure 1: a plot",
                page=3,
                bbox=(10, 20, 30, 40),
                reading_order=1,
            ),
        ],
    )

    figures = stream.blocks_of(IMAGE)
    assert len(figures) == 1
    assert figures[0].caption == "Figure 1: a plot"
    # The caption is not text to be chunked and embedded on its own.
    assert stream.text() == "body"
    assert stream.media_keys() == ["blobs/abc"]


def test_layout_metadata_is_what_a_node_should_cite_by():
    block = ContentBlock(
        block_id="b2",
        kind=IMAGE,
        media_key="blobs/abc",
        page=3,
        bbox=(10, 20, 30, 40),
        reading_order=7,
    )

    layout = block.layout_metadata()

    assert layout["page"] == 3
    assert layout["bbox"] == [10, 20, 30, 40]
    assert layout["reading_order"] == 7
    assert layout["media_key"] == "blobs/abc"
    # Never the caption: that is embedded with the image, not cited as layout.
    assert "caption" not in layout


def test_a_stream_round_trips():
    stream = ContentStream(
        asset_id="a1",
        blocks=[
            ContentBlock(block_id="b1", kind=TEXT, text="body", page=1),
            ContentBlock(
                block_id="b2",
                kind=IMAGE,
                media_key="blobs/abc",
                caption="cap",
                caption_for="b1",
                page=1,
                bbox=(1, 2, 3, 4),
                reading_order=1,
            ),
        ],
        metadata={"file_name": "a.pdf"},
    )

    again = ContentStream.from_record(stream.to_record())

    assert again.to_record() == stream.to_record()
    assert again.blocks_of(IMAGE)[0].caption_for == "b1"


def test_a_stream_can_be_built_from_a_plain_document():
    """The seam a real layout extractor replaces."""
    stream = ContentStream.from_document(
        Document(text="hello", id_="a1", metadata={"file_name": "a.pdf"})
    )

    assert stream.asset_id == "a1"
    assert stream.text() == "hello"
    assert stream.metadata["asset_id"] == "a1"
    assert stream.metadata["file_name"] == "a.pdf"
