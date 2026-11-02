# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""A vector projection parses the asset's blocks, not a flattened copy of them.

`FileAsset.document` used to join every block's text into one string for the
splitter to chop up again. Everything a block knew about itself was gone by
then: which page it was on, where on the page, and -- for a figure -- that it
was a figure at all. So a retrieved chunk could not be cited, and a picture
could not be retrieved.

Parsing from blocks fixes both, at one cost worth stating: a chunk never spans
two blocks, so a page shorter than the chunk size stays a short chunk.
"""

from types import SimpleNamespace

from core.content import (
    IMAGE,
    LAYOUT_METADATA_KEYS,
    TEXT,
    VIDEO,
    ContentBlock,
    ContentStream,
)
from core.indexer import EMBED_EXCLUDED_METADATA_KEYS, VectorIndexer
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.schema import ImageNode, TextNode
from llama_index.core.vector_stores import SimpleVectorStore
from llama_index.core.vector_stores.types import (
    MetadataFilter,
    MetadataFilters,
    VectorStoreQueryResult,
)


class FakeParser:
    """Stands in for the SentenceSplitter: one node per document, unsplit."""

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


def _indexer(context_chars=400, fused_embed=None, blob_reader=None):
    """A `VectorIndexer` with only the parts `nodes_from` uses.

    Built without `__init__`, which would want an embedding model, a collection
    and a live backend -- none of which parsing blocks into nodes depends on.
    `fused_embed`/`blob_reader` stay `None` by default, so image nodes take the
    text-only path (embedding left for `insert_nodes`) exactly as before.
    """
    indexer = object.__new__(VectorIndexer)
    indexer._node_parser = FakeParser()
    indexer._context_chars = context_chars
    # The embedding model is only reached for its `get_fused_embeddings`; a
    # text-only stand-in simply lacks it, so image nodes take the text path.
    indexer._embedding_model = (
        SimpleNamespace(get_fused_embeddings=fused_embed) if fused_embed else None
    )
    indexer._blob_reader = blob_reader
    indexer.configuration = {}
    return indexer


def _asset(blocks, asset_id="a1", metadata=None):
    return SimpleNamespace(
        asset_id=asset_id,
        origin="file:///w/report.pdf",
        content=ContentStream(
            asset_id=asset_id,
            blocks=blocks,
            metadata={"file_path": "/w/report.pdf", **(metadata or {})},
        ),
    )


def _text(order, text, page):
    return ContentBlock(
        block_id=f"a1:{order}", kind=TEXT, text=text, page=page, reading_order=order
    )


def _figure(order, page, caption="", bbox=(1.0, 2.0, 3.0, 4.0)):
    return ContentBlock(
        block_id=f"a1:{order}",
        kind=IMAGE,
        media_key="blobs/abc",
        caption=caption,
        page=page,
        bbox=bbox,
        reading_order=order,
    )


# --- text ---------------------------------------------------------------------


def test_each_block_is_parsed_on_its_own():
    asset = _asset([_text(0, "page one", 1), _text(1, "page two", 2)])

    nodes = _indexer().nodes_from(asset)

    assert [node.text for node in nodes] == ["page one", "page two"]


def test_a_chunk_keeps_the_page_it_came_from():
    """The whole reason parsing moved here: a chunk you cannot cite is a chunk
    you cannot trust."""
    asset = _asset([_text(0, "page one", 1), _text(1, "page two", 2)])

    nodes = _indexer().nodes_from(asset)

    assert [node.metadata["page"] for node in nodes] == [1, 2]
    assert [node.metadata["reading_order"] for node in nodes] == [0, 1]


def test_document_metadata_still_reaches_every_chunk():
    """Deletion addresses records by file_path and by asset_id."""
    asset = _asset([_text(0, "words", 1)])

    node = _indexer().nodes_from(asset)[0]

    assert node.metadata["file_path"] == "/w/report.pdf"
    assert node.metadata["asset_id"] == "a1"


def test_layout_is_kept_for_citing_and_excluded_from_the_embedding():
    """Coordinates say where a chunk is, not what it says."""
    asset = _asset([_text(0, "words", 1)])

    node = _indexer().nodes_from(asset)[0]

    assert set(node.excluded_embed_metadata_keys) == set(EMBED_EXCLUDED_METADATA_KEYS)
    assert set(LAYOUT_METADATA_KEYS) <= set(node.excluded_embed_metadata_keys)
    assert "page" in node.metadata, "excluded from the vector, not from the record"


def test_an_empty_block_produces_no_node():
    asset = _asset([_text(0, "   ", 1), _text(1, "words", 2)])

    assert len(_indexer().nodes_from(asset)) == 1


# --- figures ------------------------------------------------------------------


def test_a_figure_becomes_one_image_node():
    asset = _asset([_text(0, "before", 1), _figure(1, 1, "Figure 1"), _text(2, "after", 1)])

    nodes = _indexer().nodes_from(asset)

    assert len(nodes) == 3
    assert isinstance(nodes[1], ImageNode)
    assert nodes[1].metadata["media_key"] == "blobs/abc"


def test_a_figure_is_searchable_through_the_text_around_it():
    """An untitled figure uses neighbouring prose as its searchable reference."""
    asset = _asset(
        [_text(0, "before it", 1), _figure(1, 1), _text(2, "after it", 1)]
    )

    figure = _indexer().nodes_from(asset)[1]

    assert figure.text == ""
    context = figure.metadata["surrounding_text"]
    assert "before it" in context and "after it" in context
    assert "surrounding_text" not in figure.excluded_embed_metadata_keys


def test_a_caption_is_the_reference_without_unrelated_neighbouring_prose():
    asset = _asset([_text(0, "before it", 1), _figure(1, 1, "Figure 1"), _text(2, "after it", 1)])

    figure = _indexer().nodes_from(asset)[1]

    assert figure.text == "Figure 1"
    assert "surrounding_text" not in figure.metadata


def test_a_figure_keeps_its_position_for_citation():
    asset = _asset([_text(0, "before", 3), _figure(1, 3, "Figure 1")])

    figure = _indexer().nodes_from(asset)[1]

    assert figure.metadata["page"] == 3
    assert figure.metadata["bbox"] == [1.0, 2.0, 3.0, 4.0]
    assert figure.metadata["kind"] == IMAGE


def test_a_figure_with_nothing_to_say_is_dropped():
    """No caption and no prose around it: nothing a query could ever match."""
    asset = _asset([_figure(0, 1)])

    assert _indexer().nodes_from(asset) == []


def test_the_context_window_is_bounded():
    asset = _asset([_text(0, "x " * 2000, 1), _figure(1, 1)])

    figure = _indexer(context_chars=50).nodes_from(asset)[1]

    assert len(figure.metadata["surrounding_text"]) <= 50


# --- fused image embedding (multimodal model) ---------------------------------


def test_an_image_node_is_embedded_jointly_from_its_pixels_and_text():
    """With a multimodal model the figure's vector is precomputed here: pixels
    read back by media_key, text side the same the text path would embed."""
    seen = {}

    def blob_reader(media_key, source_id=None):
        seen["read"] = (media_key, source_id)
        return b"PNGBYTES"

    def fused_embed(texts, images):
        seen["texts"], seen["images"] = list(texts), list(images)
        return [[0.1, 0.2, 0.3] for _ in texts]

    asset = _asset(
        [_text(0, "before it", 1), _figure(1, 1, "Figure 1"), _text(2, "after it", 1)]
    )
    asset.content_source_id = "obj-src"

    nodes = _indexer(fused_embed=fused_embed, blob_reader=blob_reader).nodes_from(asset)

    figure = nodes[1]
    assert figure.embedding == [0.1, 0.2, 0.3]
    assert seen["read"] == ("blobs/abc", "obj-src")
    assert seen["images"] == [b"PNGBYTES"]
    # Only the image node reaches the fused model; text nodes are left for
    # insert_nodes to embed (their embedding stays None).
    assert len(seen["texts"]) == 1
    # Main pairs a captioned figure with its caption, not unrelated prose.
    assert "Figure 1" in seen["texts"][0]
    assert "before it" not in seen["texts"][0] and "after it" not in seen["texts"][0]


# --- streaming add (producer/consumer) ----------------------------------------


def _streaming_indexer():
    """A `VectorIndexer` wired just enough for `add` to stream into a real store."""
    from core.node_parser import build_node_parser

    indexer = object.__new__(VectorIndexer)
    # A real splitter, so text nodes expose `get_content` for the consumer to embed
    # (the `FakeParser` above is for `nodes_from`, which never embeds text).
    indexer._node_parser = build_node_parser(chunk_size=512, chunk_overlap=50)
    indexer._context_chars = 400
    indexer._embedding_model = MockEmbedding(embed_dim=3)
    indexer._blob_reader = None
    indexer.configuration = {}
    indexer.version = 0
    indexer.dimension = 3
    # `collection` is a read-only property over `source.location`.
    indexer.source = SimpleNamespace(location=SimpleNamespace(name="c", dimension=3))
    vector_store = SimpleVectorStore()
    vector_store.stores_text = True
    indexer._index = VectorStoreIndex(
        nodes=[],
        embed_model=indexer._embedding_model,
        storage_context=StorageContext.from_defaults(vector_store=vector_store),
    )
    indexer._adapter = SimpleNamespace(flush=lambda collection: None)
    return indexer


def test_iter_node_items_filters_to_requested_blocks_with_full_context():
    """Phase 2 of the two-phase ingest builds only the figures, but a figure's
    surrounding_text must still see the whole stream around it."""
    indexer = _indexer()
    asset = _asset(
        [_text(0, "before it", 1), _figure(1, 1), _text(2, "after it", 1)]
    )
    image_id = asset.content.blocks[1].block_id

    items = list(indexer.iter_node_items(asset, only_block_ids={image_id}))

    assert len(items) == 1, "only the requested block produces a node"
    node, modality, _ = items[0]
    assert modality == "fused"
    assert node.metadata["media_key"] == "blobs/abc"
    context = node.metadata["surrounding_text"]
    assert "before it" in context and "after it" in context


def test_add_streams_every_block_into_the_collection():
    """`add` goes through the producer/consumer pipeline, not one batch at the end:
    each block's node is embedded and inserted, and the counts match `nodes_from`."""
    indexer = _streaming_indexer()
    asset = _asset(
        [_text(0, "page one", 1), _figure(1, 1, "Figure 1"), _text(2, "page two", 2)]
    )

    result = indexer.add([asset])

    assert result == {"documents_added": 1, "chunks_added": 3}
    assert indexer.version >= 1, "a write bumps the version so a cache can tell"


def test_a_text_only_model_leaves_image_nodes_for_the_text_path():
    """No fused capability: the image node keeps embedding=None and is embedded
    from its caption and surrounding text like any text node."""
    asset = _asset([_text(0, "before", 1), _figure(1, 1, "Figure 1")])

    figure = _indexer().nodes_from(asset)[1]

    assert figure.embedding is None


def test_unreadable_pixels_fall_back_to_the_text_path():
    def blob_reader(media_key, source_id=None):
        raise FileNotFoundError(media_key)

    def fused_embed(texts, images):  # pragma: no cover - must not be called
        raise AssertionError("no node should reach the fused model")

    asset = _asset([_text(0, "before", 1), _figure(1, 1, "Figure 1")])

    figure = _indexer(fused_embed=fused_embed, blob_reader=blob_reader).nodes_from(
        asset
    )[1]

    assert figure.embedding is None


def test_mixed_retrieval_includes_text_not_only_cached_image_nodes(monkeypatch):
    nodes = [
        TextNode(id_="text-node", text="The battery range is 400 kilometers."),
        ImageNode(id_="image-node", text="figure", embedding=[0.0, 1.0, 0.0]),
    ]
    indexer = _indexer()
    vector_store = SimpleVectorStore()
    vector_store.stores_text = True
    indexer._index = VectorStoreIndex(
        nodes=nodes,
        embed_model=MockEmbedding(embed_dim=3),
        storage_context=StorageContext.from_defaults(vector_store=vector_store),
    )
    assert set(indexer._index.index_struct.nodes_dict.values()) == {"image-node"}
    filters = MetadataFilters(filters=[MetadataFilter(key="asset_id", value="a1")])

    def query_store(self, query, **kwargs):
        assert query.filters == filters
        assert query.similarity_top_k == 2
        selected = [
            node for node in nodes if not query.node_ids or node.node_id in query.node_ids
        ]
        return VectorStoreQueryResult(
            nodes=selected,
            ids=[node.node_id for node in selected],
            similarities=[1.0] * len(selected),
        )

    monkeypatch.setattr(SimpleVectorStore, "query", query_store)

    retrieved = indexer._retriever(2, filters).retrieve("What is the battery range?")

    assert {result.node.node_id for result in retrieved} == {"text-node", "image-node"}


# --- media files --------------------------------------------------------------


def test_a_media_file_is_a_node_like_anything_else():
    """One block, no text; there is no separate class and no modality flag."""
    block = ContentBlock(
        block_id="a1:0", kind=VIDEO, media_key="blobs/v", caption="q3 teardown"
    )
    asset = _asset([block], metadata={"file_path": "/w/q3.mp4"})

    nodes = _indexer().nodes_from(asset)

    assert len(nodes) == 1
    assert not isinstance(nodes[0], ImageNode), "a video is not an image"
    assert nodes[0].text == "q3 teardown"
    assert nodes[0].metadata["media_key"] == "blobs/v"
