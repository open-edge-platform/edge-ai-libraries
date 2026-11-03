# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Multimodal routing through the real streaming add and in-memory index.

Fake models return distinct media, corpus and query vectors: routing content
through the wrong tower must fail an assertion, not merely produce a record.
No model packages, media decoders or database services are needed.
"""

import threading
from contextlib import nullcontext
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

import config
from assetlib import AssetPool, Source
from assetlib.sources.binding import DEPRECATED, PREPARING, SERVING
from core import materialize
from core.content import (
    AUDIO,
    IMAGE,
    ROLE_AUDIO,
    ROLE_DOC_IMAGE,
    ROLE_IMAGE,
    ROLE_L1_SEGMENT,
    ROLE_L2_CAPTION,
    ROLE_L2_TRANSCRIPT,
    ROLE_L3_WIKI,
    ROLE_LONG_VIDEO,
    ROLE_SHORT_VIDEO,
    TEXT,
    VIDEO,
    ContentBlock,
    ContentStream,
)
from core.file_asset_library import FileAssetLibrary
from core.indexer import MultimodalIndexer, VectorIndexer, accepts_block
from databasehub.models import GraphCollection, VectorCollection
from llama_index.core import StorageContext
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.bridge.pydantic import PrivateAttr
from llama_index.core.schema import ImageNode, TextNode

from tests.test_sources.fakes import Library, add_source, ingest, serving_ids, state

DIMENSION = 4
IMAGE_VECTOR = [1.0, 0.0, 0.0, 0.0]
VIDEO_VECTOR = [0.0, 1.0, 0.0, 0.0]
DOCUMENT_VECTOR = [0.0, 0.0, 1.0, 0.0]
QUERY_VECTOR = [0.0, 0.0, 0.0, 1.0]


class FakeMultimodalEmbedding:
    dimension = DIMENSION
    frames_per_clip = 2

    def __init__(self, supported_roles):
        self.supported_roles = frozenset(supported_roles)
        self.images = []
        self.videos = []
        self.documents = []
        self.queries = []

    def embed_image(self, images):
        self.images.extend(images)
        return [list(IMAGE_VECTOR) for _ in images]

    def embed_video(self, frames):
        self.videos.append(list(frames))
        return list(VIDEO_VECTOR)

    def embed_documents(self, texts):
        self.documents.extend(texts)
        return [list(DOCUMENT_VECTOR) for _ in texts]

    def embed_text(self, texts):
        self.queries.extend(texts)
        return [list(QUERY_VECTOR) for _ in texts]


class FakeTextEmbedding(BaseEmbedding):
    _texts: list = PrivateAttr(default_factory=list)

    def _get_query_embedding(self, query):
        return list(QUERY_VECTOR)

    async def _aget_query_embedding(self, query):
        return self._get_query_embedding(query)

    def _get_text_embedding(self, text):
        self._texts.append(text)
        return list(DOCUMENT_VECTOR)


class FakeFusedEmbedding(FakeTextEmbedding):
    _fused: list = PrivateAttr(default_factory=list)

    def get_fused_embeddings(self, texts, images):
        self._fused.extend(zip(texts, images))
        return [list(IMAGE_VECTOR) for _ in texts]


class FakeParser:
    """One real node per block; sentence splitting is tested independently."""

    def run(self, documents):
        return [
            TextNode(
                id_=document.id_,
                text=document.text,
                metadata=dict(document.metadata),
            )
            for document in documents
        ]


class MemoryAdapter:
    def __init__(self):
        self.flushed = []

    def reconcile(self, collection):
        pass

    def storage_context(self, collection):
        return StorageContext.from_defaults()

    def flush(self, collection):
        self.flushed.append(collection.name)


@pytest.fixture(autouse=True)
def _small_streaming_batches(monkeypatch):
    monkeypatch.setattr(config, "INGEST_BATCH_SIZE", 2)
    monkeypatch.setattr(config, "INGEST_QUEUE_MAX", 2)
    monkeypatch.setattr(
        "core.node_parser.build_node_parser", lambda **_options: FakeParser()
    )


def _indexer(embedding, configuration=None, multimodal=True):
    options = dict(configuration or {})
    source = Source(
        source_id="source",
        source_type="vector",
        database_id="memory",
        location=VectorCollection("chunks", DIMENSION),
        configuration=dict(options),
    )
    key = "multimodal_embedding_instance" if multimodal else "embedding_model_instance"
    options[key] = embedding
    kind = MultimodalIndexer if multimodal else VectorIndexer
    return kind("projection", "pool", source, MemoryAdapter(), options)


def _block(block_id, kind=TEXT, role=None, text="", caption="display only"):
    return ContentBlock(
        block_id=block_id,
        kind=kind,
        text=text,
        caption=caption,
        media_key=f"blob/{block_id}" if kind in (IMAGE, VIDEO, AUDIO) else "",
        metadata={"role": role} if role else {},
    )


def _asset(*blocks, asset_kind=VIDEO):
    extension, media_type = {
        IMAGE: ("png", "image/png"),
        VIDEO: ("mp4", "video/mp4"),
        AUDIO: ("wav", "audio/wav"),
    }[asset_kind]
    for order, block in enumerate(blocks):
        block.reading_order = order
    stream = ContentStream(
        asset_id="asset",
        blocks=list(blocks),
        metadata={"file_name": f"media.{extension}"},
    )
    image = BytesIO()
    Image.new("RGB", (2, 2), "white").save(image, format="PNG")
    reads = []

    def read_blob(key):
        reads.append(key)
        return image.getvalue()

    return SimpleNamespace(
        asset_id=stream.asset_id,
        asset_kind=asset_kind,
        extension=extension,
        media_type=media_type,
        content=stream,
        content_source_id="content-source",
        read_blob=read_blob,
        reads=reads,
        media_path=lambda key, suffix: nullcontext(f"/media/{key}{suffix}"),
    )


def _stored_vectors(indexer):
    return dict(indexer._index.vector_store.data.embedding_dict)


def test_actual_add_streams_video_vectors_and_filters_by_coverage(monkeypatch):
    model = FakeMultimodalEmbedding((ROLE_SHORT_VIDEO, ROLE_L1_SEGMENT, ROLE_IMAGE))
    indexer = _indexer(model, {"asset_types": [VIDEO], "block_kinds": [VIDEO]})
    sampled = []

    def sample_frames(path, count):
        sampled.append((path, count))
        return ["frame-1", "frame-2"]

    monkeypatch.setattr("core.multimodal.frames.sample_frames", sample_frames)
    asset = _asset(
        _block("clip", VIDEO, ROLE_SHORT_VIDEO),
        _block("segment", VIDEO, ROLE_L1_SEGMENT),
        _block("long", VIDEO, ROLE_LONG_VIDEO),
        _block("image", IMAGE, ROLE_IMAGE),
        _block("prose", text="not a media document"),
        _block("caption", role=ROLE_L2_CAPTION, text="derived caption"),
    )

    assert indexer.accepts(asset)
    counts = indexer.add([asset])

    assert counts == {"documents_added": 1, "chunks_added": 2}
    assert _stored_vectors(indexer) == {"clip": VIDEO_VECTOR, "segment": VIDEO_VECTOR}
    assert len(sampled) == 2 and all(count == 2 for _, count in sampled)
    assert model.videos == [["frame-1", "frame-2"]] * 2
    assert model.images == model.documents == model.queries == []
    assert asset.reads == []
    assert indexer._assets_by_stream == {}
    assert indexer._adapter.flushed == ["chunks"]


def test_actual_add_keeps_image_vectors_and_uses_corpus_tower_for_derived_text():
    model = FakeMultimodalEmbedding(
        (ROLE_IMAGE, ROLE_DOC_IMAGE, ROLE_L2_CAPTION, ROLE_L2_TRANSCRIPT, ROLE_L3_WIKI)
    )
    # This deliberately broad fake runtime covers figures and derived text too;
    # block filters, not a production model's default representation, are under test.
    indexer = _indexer(model, {
        "asset_types": [IMAGE, VIDEO, AUDIO],
        "block_kinds": [IMAGE, TEXT], "block_roles": [],
    })
    asset = _asset(
        _block("image", IMAGE, ROLE_IMAGE),
        _block("figure", IMAGE, ROLE_DOC_IMAGE),
        _block("caption", role=ROLE_L2_CAPTION, text="a person by the window"),
        _block("transcript", role=ROLE_L2_TRANSCRIPT, text="spoken corpus words"),
        _block("wiki", role=ROLE_L3_WIKI, text="structured corpus knowledge"),
        _block("empty", role=ROLE_L2_CAPTION, text="  "),
        _block("prose", text="original prose stays with the text source"),
        _block("clip", VIDEO, ROLE_SHORT_VIDEO),
        asset_kind=IMAGE,
    )

    assert indexer.accepts(asset)
    counts = indexer.add([asset])

    assert counts == {"documents_added": 1, "chunks_added": 5}
    assert _stored_vectors(indexer) == {
        "image": IMAGE_VECTOR,
        "figure": IMAGE_VECTOR,
        "caption": DOCUMENT_VECTOR,
        "transcript": DOCUMENT_VECTOR,
        "wiki": DOCUMENT_VECTOR,
    }
    assert model.documents == [
        "a person by the window", "spoken corpus words", "structured corpus knowledge"
    ]
    assert model.queries == [], "neither the width probe nor ingestion is a query"
    assert len(model.images) == 2 and model.videos == []
    assert asset.reads == ["blob/image", "blob/figure"]
    assert isinstance(indexer._index.docstore.get_node("image"), ImageNode)
    assert indexer._index.docstore.get_node("image").text == "display only"
    assert indexer._assets_by_stream == {}


@pytest.mark.parametrize("configuration", [
    {"asset_types": [AUDIO], "block_kinds": [AUDIO]},
    {"asset_types": [AUDIO], "block_kinds": [TEXT]},
])
def test_audio_transcript_matches_audio_and_text_and_streams_as_corpus(configuration):
    transcript = _block("transcript", role=ROLE_L2_TRANSCRIPT, text="recognized speech")
    assert accepts_block(transcript, configuration)
    model = FakeMultimodalEmbedding((ROLE_L2_TRANSCRIPT,))
    indexer = _indexer(model, configuration)
    asset = _asset(
        _block("recording", AUDIO, ROLE_AUDIO),
        transcript,
        _block("caption", role=ROLE_L2_CAPTION, text="not a transcript"),
        _block("prose", text="not recognized speech"),
        asset_kind=AUDIO,
    )

    assert indexer.accepts(asset)
    counts = indexer.add([asset])

    assert counts == {"documents_added": 1, "chunks_added": 1}
    assert _stored_vectors(indexer) == {"transcript": DOCUMENT_VECTOR}
    assert model.documents == ["recognized speech"]
    assert model.queries == model.images == model.videos == []
    assert not accepts_block(asset.content.blocks[2], {"block_kinds": [AUDIO]})


def test_multimodal_iterator_respects_only_block_ids_and_block_roles():
    model = FakeMultimodalEmbedding((ROLE_IMAGE, ROLE_L2_CAPTION, ROLE_L2_TRANSCRIPT))
    indexer = _indexer(model, {
        "asset_types": [VIDEO], "block_roles": [ROLE_L2_TRANSCRIPT],
    })
    asset = _asset(
        _block("image", IMAGE, ROLE_IMAGE),
        _block("caption", role=ROLE_L2_CAPTION, text="not selected"),
        _block("first", role=ROLE_L2_TRANSCRIPT, text="first transcript"),
        _block("second", role=ROLE_L2_TRANSCRIPT, text="second transcript"),
    )

    items = list(indexer.iter_node_items(asset, only_block_ids={"image", "caption", "second"}))
    assert [(node.id_, modality, source) for node, modality, source in items] == [
        ("second", "document", "content-source")
    ]
    indexer.embed_items(items)

    assert items[0][0].embedding == DOCUMENT_VECTOR
    assert list(indexer.iter_node_items(asset, only_block_ids=set())) == []
    assert model.documents == ["second transcript"]
    assert model.images == model.videos == model.queries == []
    assert asset.reads == []


@pytest.mark.parametrize("filters", [
    {"block_kinds": [IMAGE, TEXT], "block_roles": []},
    {"block_kinds": [], "block_roles": [ROLE_IMAGE, ROLE_L2_CAPTION]},
    {"block_kinds": [], "block_roles": []},
])
def test_multimodal_batch_and_streaming_keep_the_same_media_and_corpus_vectors(filters):
    model = FakeMultimodalEmbedding((ROLE_IMAGE, ROLE_L2_CAPTION))
    indexer = _indexer(model, {"asset_types": [IMAGE], **filters})
    asset = _asset(
        _block("image", IMAGE, ROLE_IMAGE),
        _block("caption", role=ROLE_L2_CAPTION, text="corpus caption"),
        _block("prose", text="not a multimodal document"),
        asset_kind=IMAGE,
    )
    assert indexer.accepts(asset)
    assert indexer.configuration["block_kinds"] == filters["block_kinds"]
    assert indexer.configuration["block_roles"] == filters["block_roles"]
    indexer._assets_by_stream = {id(asset.content): asset}
    try:
        nodes = indexer.nodes_from(asset)
    finally:
        indexer._assets_by_stream = {}
    batch_vectors = {node.id_: node.embedding for node in nodes}

    indexer.add([asset])

    assert batch_vectors == _stored_vectors(indexer) == {
        "image": IMAGE_VECTOR, "caption": DOCUMENT_VECTOR
    }
    assert model.documents == ["corpus caption", "corpus caption"]
    assert len(model.images) == 2 and model.queries == []


def test_declared_width_probes_no_query_but_retrieval_still_uses_query_tower():
    model = FakeMultimodalEmbedding((ROLE_IMAGE,))
    indexer = _indexer(model, {"asset_types": [IMAGE]})

    assert indexer.dimension == DIMENSION and model.queries == []
    assert indexer._embedding_model.get_query_embedding("find a picture") == QUERY_VECTOR
    with pytest.raises(NotImplementedError, match="must be precomputed"):
        indexer._embedding_model.get_text_embedding("unprepared corpus content")
    assert model.queries == ["find a picture"]
    assert model.documents == []


@pytest.mark.parametrize("configuration", [{"block_kinds": [TEXT]}, {}])
def test_text_source_shares_batch_and_streaming_filters(configuration):
    model = FakeFusedEmbedding()
    indexer = _indexer(model, configuration, multimodal=False)
    asset = _asset(
        _block("prose", text="original prose"),
        _block("image", IMAGE, ROLE_IMAGE),
        _block("clip", VIDEO, ROLE_SHORT_VIDEO),
        _block("audio", AUDIO, ROLE_AUDIO),
        _block("segment", VIDEO, ROLE_L1_SEGMENT),
        _block("caption", role=ROLE_L2_CAPTION, text="derived caption"),
        _block("transcript", role=ROLE_L2_TRANSCRIPT, text="derived transcript"),
        _block("wiki", role=ROLE_L3_WIKI, text="derived wiki"),
    )
    indexer._blob_reader = lambda key, source: asset.read_blob(key)
    expected = {"prose"} if configuration else {"prose", "image", "clip", "audio"}

    batch_nodes = indexer.nodes_from(asset)
    assert {node.id_ for node in batch_nodes} == expected
    assert {node.id_ for node, _, _ in indexer.iter_node_items(asset)} == expected
    counts = indexer.add([asset])

    assert counts == {"documents_added": 1, "chunks_added": len(expected)}
    assert set(_stored_vectors(indexer)) == expected
    assert not any("derived" in text for text in model._texts)
    if configuration:
        assert asset.reads == [] and model._fused == []
    else:
        assert _stored_vectors(indexer)["image"] == IMAGE_VECTOR
        assert len(model._fused) == 2, "batch and streaming preserve main's fused path"


def test_actual_add_with_no_covered_blocks_does_not_flush():
    model = FakeMultimodalEmbedding((ROLE_SHORT_VIDEO,))
    indexer = _indexer(model, {"asset_types": [VIDEO]})

    counts = indexer.add([_asset(_block("prose", text="no media"))])

    assert counts == {"documents_added": 1, "chunks_added": 0}
    assert _stored_vectors(indexer) == {}
    assert indexer._adapter.flushed == []
    assert indexer._assets_by_stream == {}
    assert model.queries == []


def test_failed_streaming_producer_releases_asset_bindings(monkeypatch):
    model = FakeMultimodalEmbedding((ROLE_SHORT_VIDEO,))
    indexer = _indexer(model, {"asset_types": [VIDEO]})

    def fail(*_args):
        raise RuntimeError("cannot decode clip")

    monkeypatch.setattr("core.multimodal.frames.sample_frames", fail)
    with pytest.raises(RuntimeError, match="cannot decode clip"):
        indexer.add([_asset(_block("clip", VIDEO, ROLE_SHORT_VIDEO))])

    assert indexer._assets_by_stream == {}
    assert indexer._adapter.flushed == []


@pytest.mark.parametrize("failure_stage", ["embed_items", "insert_prepared"])
@pytest.mark.parametrize("blocked_on", ["node", "sentinel"])
def test_consumer_failure_cancels_full_queue_and_joins_before_unbinding(
    monkeypatch, failure_stage, blocked_on
):
    monkeypatch.setattr(config, "INGEST_BATCH_SIZE", 1)
    monkeypatch.setattr(config, "INGEST_QUEUE_MAX", 1)
    blocked = threading.Event()
    queue_type = materialize.queue.Queue

    class ObservedQueue(queue_type):
        def put(self, item, *args, **kwargs):
            target = (
                item is materialize._SENTINEL if blocked_on == "sentinel"
                else item is not materialize._SENTINEL and item[0].id_ == "caption-2"
            )
            if target and self.full():
                blocked.set()
            return super().put(item, *args, **kwargs)

    monkeypatch.setattr(materialize.queue, "Queue", ObservedQueue)
    indexer = _indexer(FakeMultimodalEmbedding((ROLE_L2_CAPTION,)), {
        "asset_types": [VIDEO], "block_roles": [ROLE_L2_CAPTION],
    })
    asset = _asset(*[
        _block(f"caption-{i}", role=ROLE_L2_CAPTION, text=f"caption {i}")
        for i in range(2 if blocked_on == "sentinel" else 20)
    ])
    iterate = indexer.iter_node_items
    producer_threads = []
    bindings_at_exit = []
    produced = []

    def tracked_items(asset):
        producer_threads.append(threading.current_thread())
        try:
            for item in iterate(asset):
                assert indexer._asset_of(asset.content) is asset
                produced.append(item)
                yield item
        finally:
            bindings_at_exit.append(indexer._assets_by_stream.get(id(asset.content)) is asset)

    failure = RuntimeError(f"{failure_stage} failed")

    def fail_with_full_queue(*_args):
        assert blocked.wait(3), "producer must reach a bounded-queue put before failure"
        raise failure

    monkeypatch.setattr(indexer, "iter_node_items", tracked_items)
    monkeypatch.setattr(indexer, failure_stage, fail_with_full_queue)

    with pytest.raises(RuntimeError) as raised:
        indexer.add([asset])

    assert raised.value is failure, "the consumer's original error must survive cleanup"
    assert len(producer_threads) == 1 and not producer_threads[0].is_alive()
    assert bindings_at_exit == [True], "producer cleanup precedes MM binding cleanup"
    assert len(produced) == (2 if blocked_on == "sentinel" else 3)
    assert indexer._assets_by_stream == {}
    assert indexer._adapter.flushed == []


@pytest.mark.parametrize("failure_stage", ["embed_items", "insert_prepared"])
def test_partial_streaming_sync_retries_whole_asset_despite_backend_presence(
    monkeypatch, failure_stage
):
    monkeypatch.setattr(config, "INGEST_BATCH_SIZE", 1)
    indexer = _indexer(FakeMultimodalEmbedding((ROLE_L2_CAPTION,)), {
        "asset_types": [VIDEO], "block_roles": [ROLE_L2_CAPTION],
    })
    asset = _asset(*[
        _block(f"caption-{i}", role=ROLE_L2_CAPTION, text=f"caption {i}")
        for i in range(6)
    ])
    library = FileAssetLibrary("library", databasehub=SimpleNamespace())
    pool = AssetPool("pool", "pool")
    pool.set_projections([indexer])
    library._asset_pools["pool"] = pool
    library._assets[asset.asset_id] = asset
    pool.add_asset_ids([asset.asset_id])
    events = []

    def present(collection, field, values):
        return {
            node.metadata[field] for node in indexer._index.docstore.docs.values()
            if node.metadata.get(field) in values
        }

    def delete(collection, field, values):
        events.append(("delete", list(values)))
        ids = [
            node.id_ for node in indexer._index.docstore.docs.values()
            if node.metadata.get(field) in values
        ]
        indexer._index.delete_nodes(ids, delete_from_docstore=True)
        return len(ids)

    monkeypatch.setattr(indexer._adapter, "present_metadata_values", present, raising=False)
    monkeypatch.setattr(indexer._adapter, "delete_by_metadata", delete, raising=False)
    operation = getattr(indexer, failure_stage)
    calls = 0

    def fail_second_batch(items):
        nonlocal calls
        calls += 1
        events.append((failure_stage, calls))
        result = operation(items)
        if calls == 2:
            raise RuntimeError("stream interrupted after partial writes")
        return result

    monkeypatch.setattr(indexer, failure_stage, fail_second_batch)
    library.sync_asset_pool("pool")

    status = pool.source_statuses["source"]
    assert status.status == "failed"
    assert status.stale_asset_ids == ["asset"]
    assert indexer.indexed_asset_ids(["asset"]) == {"asset"}
    assert 0 < len(_stored_vectors(indexer)) < 6
    assert indexer._assets_by_stream == {}
    monkeypatch.setattr(indexer, failure_stage, operation)
    events.clear()
    library.sync_asset_pool("pool")

    assert events[0] == ("delete", ["asset"])
    assert status.status == "ready" and status.stale_asset_ids == []
    assert status.indexed_asset_ids == ["asset"]
    assert status.indexed_revision == pool.revision
    assert _stored_vectors(indexer) == {f"caption-{i}": DOCUMENT_VECTOR for i in range(6)}
    assert len(indexer._index.docstore.docs) == 6, "retry replaces partial chunks"


class HookLibrary(Library):
    """Record hooks around real sync/backfill bookkeeping, without backends."""

    def __init__(self):
        self.events = []
        super().__init__()

    def build_projection(self, projection_id, name, source):
        projection = super().build_projection(projection_id, name, source)
        add = projection.add
        delete = projection.delete_by_metadata

        def recorded_add(assets):
            self.events.append(("add", source.source_id, [a.asset_id for a in assets]))
            return add(assets)

        def recorded_delete(field, ids):
            self.events.append(("delete", source.source_id, list(ids)))
            return delete(field, ids)

        projection.add = recorded_add
        projection.delete_by_metadata = recorded_delete
        return projection

    def _prepare_projection_add(self, pool, projection, assets):
        self.events.append(("prepare", projection.source.source_id, [a.asset_id for a in assets]))
        super()._prepare_projection_add(pool, projection, assets)

    def _finish_projection_add(self, pool, projection, assets):
        self.events.append(("finish", projection.source.source_id, [a.asset_id for a in assets]))
        super()._finish_projection_add(pool, projection, assets)


def _replacement_library():
    library = HookLibrary()
    add_source(library, "old")
    library.create_asset_pool("pool", "pool", [{"source_id": "old"}])
    ingest(library, "pool", "a", "b", "c", "d", "e")
    library.sync_asset_pool("pool")
    add_source(library, "new")
    library.set_asset_pool_sources(
        "pool", [{"source_id": "old"}, {"source_id": "new", "replaces": "old"}]
    )
    library.events.clear()
    return library


def test_sync_keeps_hooks_batched_backfill_and_replacement_lifecycle():
    library = _replacement_library()
    assert state(library, "pool", "new") == PREPARING

    library.sync_asset_pool("pool")

    assert library.events == [
        ("prepare", "new", ["a", "b", "c", "d", "e"]),
        ("delete", "new", ["a", "b"]),
        ("add", "new", ["a", "b"]),
        ("delete", "new", ["c", "d"]),
        ("add", "new", ["c", "d"]),
        ("delete", "new", ["e"]),
        ("add", "new", ["e"]),
        ("finish", "new", ["a", "b", "c", "d", "e"]),
    ]
    assert state(library, "pool", "new") == SERVING
    assert state(library, "pool", "old") == DEPRECATED
    assert serving_ids(library, "pool") == ["new"]
    assert "old" in library.asset_pools["pool"].frozen_sources

    library.update_source("new", enabled=False)
    ingest(library, "pool", "f")
    library.events.clear()
    library.sync_asset_pool("pool")
    assert library.events == [], "disabled and deprecated bindings take no writes or hooks"
    assert library.store["c_new"] == library.store["c_old"] == {"a", "b", "c", "d", "e"}


def test_failed_backfill_keeps_batch_progress_and_hooks_retry_only_missing_assets():
    library = _replacement_library()
    pool = library.asset_pools["pool"]
    projection = next(p for p in pool.projections if p.source.source_id == "new")
    add = projection.add
    attempts = []

    def fail_second_batch(assets):
        attempts.append([a.asset_id for a in assets])
        if len(attempts) == 2:
            # The first chunks of c landed, but the rest of its batch did not.
            projection.held.add(assets[0].asset_id)
            raise RuntimeError("second batch failed")
        return add(assets)

    projection.add = fail_second_batch
    library.sync_asset_pool("pool")

    status = pool.source_statuses["new"]
    assert status.status == "failed" and status.serving_state == PREPARING
    assert status.indexed_asset_ids == ["a", "b"]
    assert status.stale_asset_ids == ["c", "d", "e"]
    assert projection.indexed_asset_ids(pool.asset_ids) == {"a", "b", "c"}
    assert serving_ids(library, "pool") == ["old"]
    assert not any(event[0] == "finish" for event in library.events)

    library.events.clear()
    library.sync_asset_pool("pool")

    assert attempts == [["a", "b"], ["c", "d"], ["c", "d"], ["e"]]
    assert library.events[0] == ("prepare", "new", ["c", "d", "e"])
    assert library.events[1] == ("delete", "new", ["c", "d"])
    assert library.events[-1] == ("finish", "new", ["c", "d", "e"])
    assert status.status == "ready" and status.serving_state == SERVING
    assert status.indexed_asset_ids == ["a", "b", "c", "d", "e"]
    assert status.stale_asset_ids == []


def test_sync_orders_vector_before_non_chunk_projection_and_runs_both_hooks():
    library = HookLibrary()
    source = add_source(library, "text")
    vector = library.build_projection("vector", "pool", source)

    class GraphProjection:
        kind = "graph"
        source = Source("graph", "graph", GraphCollection("graph"))

        def accepts(self, asset):
            return True

        def add(self, assets):
            assert vector.held == {"a"}, "graph preparation requires vector chunks first"
            library.events.append(("add", "graph", [a.asset_id for a in assets]))

    graph = GraphProjection()
    pool = AssetPool("pool", "pool")
    pool.set_projections([graph, vector])
    library._asset_pools["pool"] = pool
    library.add_source(graph.source)
    ingest(library, "pool", "a")

    library.sync_asset_pool("pool")

    assert library.events == [
        ("prepare", "text", ["a"]),
        ("delete", "text", ["a"]),
        ("add", "text", ["a"]),
        ("finish", "text", ["a"]),
        ("prepare", "graph", ["a"]),
        ("add", "graph", ["a"]),
        ("finish", "graph", ["a"]),
    ]
    assert all(status.status == "ready" for status in pool.source_statuses.values())