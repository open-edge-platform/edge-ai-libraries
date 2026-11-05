# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Which source takes which block, now that a pool holds more than one.

A pool used to have one vector source, so "which blocks does it index" had the
obvious answer: all of them. With a text model and a video model over the same
assets that answer double-embeds every caption and hands a clip to a model that
cannot see it.

`asset_types` could not decide this. It filters on the *file* -- extension and
MIME type, read off the origin so a sync does not have to load every content
stream to answer. A video asset and its model-written caption are the same
file, so no file-level filter can separate them. `block_kinds` is the
block-level counterpart, and the two compose: `asset_types` says which files a
source cares about, `block_kinds` says which parts of them.

One more line is drawn below `block_kinds`: derived blocks -- a clip's
model-written caption, a transcript -- are skipped by text sources no matter
what kinds they take, and embedded by multimodal sources only.
"""

from types import SimpleNamespace

from core.content import (
    IMAGE,
    ROLE_L2_CAPTION,
    ROLE_SHORT_VIDEO,
    TABLE,
    TEXT,
    VIDEO,
    ContentBlock,
    ContentStream,
)
from core.indexer import VectorIndexer, accepts_block

TEXT_SOURCE = {"block_kinds": ["text", "table"]}
VIDEO_SOURCE = {"block_kinds": ["video"]}
IMAGE_SOURCE = {"block_kinds": ["image"]}


class FakeParser:
    def run(self, documents):
        return [
            SimpleNamespace(
                text=document.get_content(),
                metadata=dict(document.metadata),
                id_=document.id_,
                excluded_embed_metadata_keys=[],
                excluded_llm_metadata_keys=[],
            )
            for document in documents
        ]


def _text_indexer(configuration):
    indexer = VectorIndexer.__new__(VectorIndexer)
    indexer.configuration = dict(configuration)
    indexer._node_parser = FakeParser()
    indexer._context_chars = 400
    return indexer


def _clip_with_caption(asset_id="a1"):
    """What a short clip looks like once its caption job has finished."""
    return ContentStream(
        asset_id=asset_id,
        blocks=[
            ContentBlock(
                block_id=f"{asset_id}:0",
                kind=VIDEO,
                media_key="blobs/abc",
                caption="holiday clip",
                reading_order=0,
                metadata={
                    "role": ROLE_SHORT_VIDEO,
                },
            ),
            ContentBlock(
                block_id=f"{asset_id}:caption",
                kind=TEXT,
                text="A family walks along a beach at sunset.",
                reading_order=1,
                metadata={"role": ROLE_L2_CAPTION, "source_block_id": f"{asset_id}:0"},
            ),
        ],
        metadata={"file_name": "holiday.mp4", "asset_id": asset_id},
    )


# --- the split -----------------------------------------------------------------


def test_the_text_source_takes_the_caption_and_not_the_clip():
    stream = _clip_with_caption()

    taken = [
        block.block_id for block in stream.ordered() if accepts_block(block, TEXT_SOURCE)
    ]

    assert taken == ["a1:caption"]


def test_the_video_source_takes_the_clip_and_not_the_caption():
    stream = _clip_with_caption()

    taken = [
        block.block_id
        for block in stream.ordered()
        if accepts_block(block, VIDEO_SOURCE)
    ]

    assert taken == ["a1:0"]


def test_every_block_is_taken_by_exactly_one_of_the_two_sources():
    """Neither dropped nor embedded twice -- the property that matters."""
    stream = _clip_with_caption()

    counts = {
        block.block_id: sum(
            accepts_block(block, configuration)
            for configuration in (TEXT_SOURCE, VIDEO_SOURCE, IMAGE_SOURCE)
        )
        for block in stream.ordered()
    }

    assert counts == {"a1:0": 1, "a1:caption": 1}


def test_a_source_with_no_block_kinds_still_takes_everything():
    """The existing single-source deployment must not change behaviour."""
    stream = _clip_with_caption()

    assert all(accepts_block(block, {}) for block in stream.ordered())


# --- through the text indexer --------------------------------------------------


def test_a_text_source_embeds_no_derived_caption():
    """A clip's model-written caption belongs to a multimodal source (GME)."""
    indexer = _text_indexer(TEXT_SOURCE)
    stream = _clip_with_caption()
    asset = SimpleNamespace(asset_id="a1", content=stream)

    nodes = indexer.nodes_from(asset)

    assert nodes == [], "the only text block here is a derived caption"


def test_an_unfiltered_text_source_still_makes_a_filename_node_for_the_clip():
    """The pre-multimodal behaviour for original media is unchanged.

    Without `block_kinds` the text source reaches the media block and embeds
    its caption -- the file name, for a clip nobody has described yet. Derived
    text is the one thing it no longer embeds.
    """
    indexer = _text_indexer({})
    stream = _clip_with_caption()
    asset = SimpleNamespace(asset_id="a1", content=stream)

    nodes = indexer.nodes_from(asset)

    assert [node.id_ for node in nodes] == ["a1:0"]


# --- the text source does not decide whether a model can embed -------------------


def test_the_block_filter_alone_does_not_claim_a_model_can_embed_the_role():
    """`accepts_block` answers "is this the kind of part I take?", nothing more.

    Whether a model can embed a given role is the multimodal projection's
    question (`MultimodalIndexer.covers`), because only it knows its model.
    """
    block = ContentBlock(
        block_id="b1", kind=IMAGE, metadata={"role": "image"}
    )

    assert accepts_block(block, IMAGE_SOURCE)


def test_a_table_goes_to_the_text_source_like_prose():
    block = ContentBlock(block_id="b2", kind=TABLE, text="| a | b |")

    assert accepts_block(block, TEXT_SOURCE)
    assert not accepts_block(block, VIDEO_SOURCE)
