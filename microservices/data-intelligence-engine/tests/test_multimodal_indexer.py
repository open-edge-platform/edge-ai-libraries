# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""A media block is embedded by a model that can see it, not by its file name.

`VectorIndexer` embeds a picture by embedding the words near it. For a figure
in a report that is reasonable -- the prose around it is what a reader would
search for. For a standalone recording there is no prose, so what gets embedded
is the file name, and the clip is findable only by what someone called it.

`MultimodalIndexer` attaches the vector itself and lets the index write it. The
load-bearing fact is that llama-index only embeds nodes whose `embedding` is
still unset, so a node that arrives with one passes straight through -- that is
what lets a model the index knows nothing about decide the vector while the
index keeps doing the storing, deleting and searching. The first test pins it.
"""

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from core.content import (
    IMAGE,
    ROLE_IMAGE,
    ROLE_L2_CAPTION,
    ROLE_LONG_VIDEO,
    ROLE_SHORT_VIDEO,
    TEXT,
    VIDEO,
    ContentBlock,
    ContentStream,
)
from core.indexer import MultimodalIndexer

DIMENSION = 8


class FakeEmbedding:
    """Counts what it was asked for, so a test can say what was *not* asked."""

    dimension = DIMENSION
    frames_per_clip = 4

    def __init__(self, supported_roles=(ROLE_SHORT_VIDEO, ROLE_IMAGE)):
        self.supported_roles = frozenset(supported_roles)
        self.videos = 0
        self.images = 0
        self.queries = []
        self.documents = []

    def embed_text(self, texts):
        self.queries.extend(texts)
        return [[0.5] * DIMENSION for _ in texts]

    def embed_documents(self, texts):
        self.documents.extend(texts)
        return [[0.0, 0.0, 1.0] + [0.0] * (DIMENSION - 3) for _ in texts]

    def embed_image(self, images):
        self.images += len(images)
        return [[1.0] + [0.0] * (DIMENSION - 1) for _ in images]

    def embed_video(self, frames):
        self.videos += 1
        return [0.0, 1.0] + [0.0] * (DIMENSION - 2)


class FakeParser:
    """One node per document, unchunked; chunking is the text indexer's own test."""

    def run(self, documents):
        nodes = []
        for document in documents:
            node = SimpleNamespace(
                text=document.get_content(),
                metadata=dict(document.metadata),
                id_=document.id_,
                excluded_embed_metadata_keys=[],
                excluded_llm_metadata_keys=[],
            )
            node.get_content = lambda node=node: node.text
            nodes.append(node)
        return nodes


def _indexer(embedding=None, configuration=None):
    """A `MultimodalIndexer` with only the parts node-building uses.

    Built without `__init__`, which wants a live collection and an adapter --
    neither of which turning blocks into nodes depends on.
    """
    indexer = MultimodalIndexer.__new__(MultimodalIndexer)
    indexer.configuration = dict(configuration or {})
    indexer._embedding = embedding or FakeEmbedding()
    indexer._node_parser = FakeParser()
    indexer._assets_by_stream = {}
    return indexer


def _asset(stream, blob=b"\x00\x01\x02"):
    return SimpleNamespace(
        asset_id=stream.asset_id,
        content=stream,
        read_blob=lambda _key: blob,
        media_path=lambda _key, _suffix=".mp4": nullcontext("/tmp/x.mp4"),
    )


def _media_stream(asset_id, kind, role, caption="holiday clip"):
    block = ContentBlock(
        block_id=f"{asset_id}:0",
        kind=kind,
        media_key="blobs/abc",
        caption=caption,
        metadata={"role": role},
    )
    return ContentStream(
        asset_id=asset_id,
        blocks=[block],
        metadata={"file_name": "holiday.mp4", "asset_id": asset_id},
    )


def _nodes(indexer, asset):
    indexer._assets_by_stream = {id(asset.content): asset}
    return indexer.nodes_from(asset)


def _sample_frames(monkeypatch, count=4):
    monkeypatch.setattr(
        "core.multimodal.frames.sample_frames", lambda _p, _c: ["f"] * count
    )


# --- the vector comes from the model, and the index must not recompute it -----


def test_a_node_arrives_with_its_vector_already_set(monkeypatch):
    embedding = FakeEmbedding()
    indexer = _indexer(embedding)
    _sample_frames(monkeypatch)
    asset = _asset(_media_stream("a1", VIDEO, ROLE_SHORT_VIDEO))

    node = _nodes(indexer, asset)[0]

    assert node.embedding == [0.0, 1.0, 0, 0, 0, 0, 0, 0]
    assert embedding.videos == 1
    assert embedding.queries == [], "the caption is not what produced the vector"


def test_llama_index_leaves_a_preset_embedding_alone():
    """The assumption the whole design rests on, asserted directly.

    If this ever stops holding, `MultimodalIndexer` silently starts embedding
    captions with a text model into a visual collection -- which does not
    error, it just retrieves nothing useful.
    """
    from llama_index.core import VectorStoreIndex
    from llama_index.core.base.embeddings.base import BaseEmbedding
    from llama_index.core.schema import TextNode

    class Exploding(BaseEmbedding):
        def _get_query_embedding(self, query):
            raise AssertionError("query embedded")

        async def _aget_query_embedding(self, query):
            raise AssertionError("query embedded")

        def _get_text_embedding(self, text):
            raise AssertionError("text embedded")

        def _get_text_embeddings(self, texts):
            if texts:
                raise AssertionError(f"{len(texts)} texts embedded")
            return []

    index = VectorStoreIndex(nodes=[], embed_model=Exploding())
    node = TextNode(id_="n1", text="a caption")
    node.embedding = [0.1, 0.2, 0.3]

    index.insert_nodes([node])

    assert index.vector_store.data.embedding_dict["n1"] == [0.1, 0.2, 0.3]
    with pytest.raises(AssertionError, match="1 texts embedded"):
        index.insert_nodes([TextNode(id_="n2", text="unembedded")])


# --- one clip is one record ---------------------------------------------------


def test_a_clip_becomes_exactly_one_node_however_many_frames_it_has(monkeypatch):
    """A record per frame would make the count depend on the video's length."""
    indexer = _indexer()
    _sample_frames(monkeypatch, count=32)
    asset = _asset(_media_stream("a2", VIDEO, ROLE_SHORT_VIDEO))

    nodes = _nodes(indexer, asset)

    assert len(nodes) == 1
    assert len(nodes[0].embedding) == DIMENSION


def test_an_image_is_embedded_as_a_still_not_as_a_one_frame_clip(monkeypatch):
    embedding = FakeEmbedding()
    indexer = _indexer(embedding)
    png = b"\x89PNG\r\n\x1a\n"
    monkeypatch.setattr(
        "PIL.Image.open", lambda _buffer: SimpleNamespace(convert=lambda _m: "image")
    )
    stream = _media_stream("a3", IMAGE, ROLE_IMAGE)
    asset = _asset(stream, png)

    node = _nodes(indexer, asset)[0]

    assert embedding.images == 1
    assert embedding.videos == 0
    assert node.embedding[0] == 1.0


# --- what a source covers is decided by its model, as of now -------------------


def test_a_block_no_configured_model_can_embed_yields_no_node():
    indexer = _indexer(FakeEmbedding(supported_roles=(ROLE_SHORT_VIDEO,)))
    asset = _asset(_media_stream("a4", VIDEO, ROLE_LONG_VIDEO))

    assert _nodes(indexer, asset) == []


def test_the_same_stored_block_is_covered_once_a_capable_model_is_configured():
    """The reason support is derived rather than written on the block.

    Nothing about the stored content differs between the two calls. A flag set
    at ingest would still read "unsupported" after the capability arrived, and
    every asset would have to be re-ingested to clear it.
    """
    block = ContentBlock(
        block_id="b1", kind=VIDEO, metadata={"role": ROLE_LONG_VIDEO}
    )

    assert not _indexer(FakeEmbedding(supported_roles=(ROLE_SHORT_VIDEO,))).covers(block)
    assert _indexer(FakeEmbedding(supported_roles=(ROLE_LONG_VIDEO,))).covers(block)


def test_a_model_that_can_embed_the_role_still_respects_block_kinds():
    block = ContentBlock(block_id="b1", kind=VIDEO, metadata={"role": ROLE_SHORT_VIDEO})
    indexer = _indexer(configuration={"block_kinds": ["image"]})

    assert not indexer.covers(block)


def test_prose_is_never_covered_by_a_multimodal_source():
    block = ContentBlock(block_id="b1", kind=TEXT, text="hello")

    assert not _indexer().covers(block)


# --- prose stays with the text source; derived text goes where its space is -----


def test_prose_in_the_same_stream_is_left_to_a_text_source(monkeypatch):
    """Embedding prose into a visual space duplicates it and degrades it."""
    embedding = FakeEmbedding()
    indexer = _indexer(embedding)
    _sample_frames(monkeypatch)
    stream = _media_stream("a5", VIDEO, ROLE_SHORT_VIDEO)
    stream.blocks.append(
        ContentBlock(
            block_id="a5:prose", kind=TEXT, text="a person wrote this", reading_order=1
        )
    )
    asset = _asset(stream)

    nodes = _nodes(indexer, asset)

    assert [node.id_ for node in nodes] == ["a5:0"]
    assert embedding.documents == []


def test_a_model_with_a_text_tower_embeds_derived_text_on_the_document_side(monkeypatch):
    """GME's text and image towers share one space, so a clip's caption goes in
    next to the clip -- encoded as a document, while queries stay query-side.
    """
    embedding = FakeEmbedding(
        supported_roles=(ROLE_SHORT_VIDEO, ROLE_IMAGE, ROLE_L2_CAPTION)
    )
    indexer = _indexer(embedding)
    _sample_frames(monkeypatch)
    stream = _media_stream("a7", VIDEO, ROLE_SHORT_VIDEO)
    stream.blocks.append(
        ContentBlock(
            block_id="a7:caption",
            kind=TEXT,
            text="a family walks along a beach",
            reading_order=1,
            metadata={"role": ROLE_L2_CAPTION},
        )
    )
    asset = _asset(stream)

    nodes = _nodes(indexer, asset)

    assert sorted(node.id_ for node in nodes) == ["a7:0", "a7:caption"]
    assert embedding.documents == ["a family walks along a beach"]
    assert embedding.queries == [], "derived text is content, not a query"
    caption_node = next(node for node in nodes if node.id_ == "a7:caption")
    assert caption_node.embedding[:3] == [0.0, 0.0, 1.0]


# --- what a retrieved node can say about itself -------------------------------


def test_a_node_keeps_its_caption_for_display_and_its_role_for_filtering(monkeypatch):
    indexer = _indexer()
    _sample_frames(monkeypatch)
    asset = _asset(_media_stream("a6", VIDEO, ROLE_SHORT_VIDEO, caption="beach walk"))

    node = _nodes(indexer, asset)[0]

    assert node.text == "beach walk"
    assert node.metadata["role"] == ROLE_SHORT_VIDEO
    assert node.metadata["asset_id"] == "a6"
    assert node.metadata["media_key"] == "blobs/abc"
