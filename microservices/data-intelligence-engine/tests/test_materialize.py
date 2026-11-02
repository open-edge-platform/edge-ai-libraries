# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The streaming embed engine: a producer fills a bounded queue, one consumer
drains it into micro-batches.

`streaming_materialize` is driven here through a fake indexer that records how it
was called -- which nodes were embedded, in what batches, how often the write was
flushed. What is pinned is the engine's contract: every node reaches
`embed_items` then `insert_prepared`, batches never exceed `batch_size`, the write
is flushed once at the end (and not at all when nothing was written), a bounded
queue never deadlocks, and a producer error surfaces to the caller rather than
hanging the consumer.
"""

from threading import RLock
from types import SimpleNamespace

import pytest
from PIL import Image

from core import materialize
from core.content import IMAGE, ROLE_DOC_IMAGE, TEXT, ContentBlock, ContentStream
from core.layout import LayoutBlock
from core.materialize import streaming_materialize


class FakeIndexer:
    """Only the three hooks `streaming_materialize` calls, with a record of each."""

    def __init__(self, items_per_asset):
        self._items_per_asset = items_per_asset
        self.embed_batches = []
        self.insert_batches = []
        self.flushed = 0

    def iter_node_items(self, asset):
        yield from self._items_per_asset[asset.asset_id]

    def embed_items(self, items):
        self.embed_batches.append(list(items))
        for node, modality, _ in items:
            node.embedding = [2.0] if modality == "fused" else [1.0]

    def insert_prepared(self, nodes):
        nodes = list(nodes)
        self.insert_batches.append(nodes)
        return len(nodes)

    def flush(self):
        self.flushed += 1


def _item(index, modality="text", source="src"):
    return (SimpleNamespace(embedding=None, nid=index), modality, source)


def _asset(asset_id):
    return SimpleNamespace(asset_id=asset_id)


def test_every_node_is_embedded_then_inserted_in_bounded_batches():
    items = [_item(i) for i in range(5)]
    indexer = FakeIndexer({"a": items})

    counts = streaming_materialize(indexer, [_asset("a")], batch_size=2, queue_max=10)

    assert counts == {"documents_added": 1, "chunks_added": 5}
    assert all(len(batch) <= 2 for batch in indexer.insert_batches)
    assert sum(len(batch) for batch in indexer.insert_batches) == 5
    assert len(indexer.embed_batches) == len(indexer.insert_batches)
    assert indexer.flushed == 1
    # Each node was embedded (by the consumer) before it was inserted.
    assert all(node.embedding is not None for node, _, _ in items)


def test_text_and_fused_nodes_both_flow_through_embed_items():
    items = [_item(0, "text"), _item(1, "fused"), _item(2, "text")]
    indexer = FakeIndexer({"a": items})

    streaming_materialize(indexer, [_asset("a")], batch_size=16, queue_max=16)

    modalities = [modality for batch in indexer.embed_batches for _, modality, _ in batch]
    assert sorted(modalities) == ["fused", "text", "text"]
    assert all(node.embedding is not None for node, _, _ in items)


def test_documents_added_counts_assets_and_chunks_count_nodes():
    indexer = FakeIndexer({"a": [_item(0)], "b": [_item(1), _item(2)]})

    counts = streaming_materialize(
        indexer, [_asset("a"), _asset("b")], batch_size=16, queue_max=16
    )

    assert counts == {"documents_added": 2, "chunks_added": 3}


def test_nothing_to_index_inserts_nothing_and_does_not_flush():
    indexer = FakeIndexer({"a": []})

    counts = streaming_materialize(indexer, [_asset("a")], batch_size=4, queue_max=4)

    assert counts == {"documents_added": 1, "chunks_added": 0}
    assert indexer.insert_batches == []
    assert indexer.flushed == 0


def test_a_tiny_queue_applies_backpressure_without_deadlocking():
    items = [_item(i) for i in range(50)]
    indexer = FakeIndexer({"a": items})

    counts = streaming_materialize(indexer, [_asset("a")], batch_size=4, queue_max=1)

    assert counts["chunks_added"] == 50
    assert sum(len(batch) for batch in indexer.insert_batches) == 50


def test_a_producer_error_is_raised_to_the_caller_not_hung():
    class BoomIndexer(FakeIndexer):
        def iter_node_items(self, asset):
            yield _item(0)
            raise RuntimeError("producer boom")

    indexer = BoomIndexer({"a": []})

    with pytest.raises(RuntimeError, match="producer boom"):
        streaming_materialize(indexer, [_asset("a")], batch_size=4, queue_max=4)


# --- ingest: the background orchestrator --------------------------------------


def test_ingest_extracts_stores_registers_pools_and_syncs(monkeypatch):
    """The whole slow path a 202 defers to: extract each file, store+register it,
    add it to the named pools, then sync. Each step is recorded on a fake library."""
    created, registered, pooled, synced = [], [], [], []

    class FakeLibrary:
        def __init__(self):
            self.assets = {}
            self.asset_pools = {}
            self.file_map = {}

        def blob_writer(self, source_id=None):
            assert source_id == "content-1"
            return lambda *_args: "blob"

        def create_asset(self, origin, stream, source_id=None):
            assert source_id == "content-1"
            asset = SimpleNamespace(asset_id=stream.asset_id, origin=origin)
            created.append(asset)
            return asset

        def register_assets(self, assets):
            registered.extend(assets)
            self.assets.update((asset.asset_id, asset) for asset in assets)

        def add_assets_to_pool(self, pool_id, asset_ids):
            pooled.append((pool_id, list(asset_ids)))

        def note_assets_changed(self, _asset_ids):
            raise AssertionError("a first ingest replaces nothing")

        def sync_asset_pool(self, pool_id):
            synced.append(pool_id)

    import core.extractor as extractor_module
    import core.file_asset_library as file_asset_library
    import core.manager as manager

    monkeypatch.setattr(
        extractor_module,
        "extract",
        lambda _path, asset_id, _put_blob: ContentStream(
            asset_id=asset_id, blocks=[ContentBlock(f"{asset_id}:0", text="report")]
        ),
    )
    monkeypatch.setattr(file_asset_library, "file_origin", lambda path: f"file://{path}")
    monkeypatch.setattr(file_asset_library, "asset_id_for", lambda _origin: "asset-1")
    saves = []
    monkeypatch.setattr(
        manager, "registry", SimpleNamespace(lock=RLock(), save=lambda: saves.append(1))
    )

    library = FakeLibrary()
    materialize.ingest(library, ["manual.pdf"], "", "", ["pool-1"], "content-1")

    assert [asset.asset_id for asset in created] == ["asset-1"]
    assert [asset.asset_id for asset in registered] == ["asset-1"]
    assert pooled == [("pool-1", ["asset-1"])]
    assert synced == ["pool-1"]
    assert library.file_map == {"manual.pdf": "manual.pdf"}
    assert saves, "the task persists the library after indexing"


def test_ingest_skips_a_file_that_fails_to_extract(monkeypatch):
    """One bad file is logged and skipped; the client already has its 202."""
    import core.extractor as extractor_module
    import core.file_asset_library as file_asset_library
    import core.manager as manager

    def boom(_path, _asset_id, _put_blob):
        raise RuntimeError("cannot read pdf")

    monkeypatch.setattr(extractor_module, "extract", boom)
    monkeypatch.setattr(file_asset_library, "file_origin", lambda path: f"file://{path}")
    monkeypatch.setattr(file_asset_library, "asset_id_for", lambda _origin: "asset-1")
    monkeypatch.setattr(
        manager, "registry", SimpleNamespace(lock=RLock(), save=lambda: None)
    )

    synced = []

    class FakeLibrary:
        asset_pools = {}  # no pools -> no primary projection -> plain extract path

        def blob_writer(self, source_id=None):
            return lambda *_args: "blob"

        def sync_asset_pool(self, pool_id):  # pragma: no cover - must not run
            synced.append(pool_id)

    # Nothing extracted -> nothing registered or synced, and no crash.
    materialize.ingest(FakeLibrary(), ["broken.pdf"], "", "", ["pool-1"], "content-1")
    assert synced == []


# --- two_phase_ingest: text first, figures second -----------------------------


class RecordingIndexer:
    """Records the order of delete/embed/insert/flush so phase ordering is testable.

    `iter_node_items` is a stand-in: it yields each block as its own `(node,
    modality, source)` so the orchestration (which blocks land in which phase, and
    when the flush and signal happen) can be checked without real embedding.
    """

    def __init__(self):
        self.ops = []

    def delete_by_metadata(self, field, values):
        self.ops.append(("delete", field, tuple(values)))
        return 0

    def iter_node_items(self, asset, only_block_ids=None):
        for block in asset.content.ordered():
            if only_block_ids is not None and block.block_id not in only_block_ids:
                continue
            modality = "fused" if block.kind == IMAGE else "text"
            yield block, modality, asset.content_source_id

    def embed_items(self, items):
        self.ops.append(("embed", [block.block_id for block, _, _ in items]))

    def insert_prepared(self, nodes):
        self.ops.append(("insert", [node.block_id for node in nodes]))
        return len(nodes)

    def flush(self):
        self.ops.append(("flush",))


class _TextLayer:
    def __init__(self, pages_text, candidates=None, region_texts=None):
        self._pages_text = pages_text
        self._candidates = candidates if candidates is not None else [[] for _ in pages_text]
        self._region_texts = dict(region_texts or {})
        self.closed = False

    def page_count(self):
        return len(self._pages_text)

    def page_text(self, index):
        return self._pages_text[index]

    def candidates(self, index):
        return self._candidates[index]

    def region_text(self, index, pixel_bbox):
        return self._region_texts.get(tuple(pixel_bbox), "")

    def close(self):
        self.closed = True


class _Detector:
    def __init__(self, per_page):
        self._per_page = per_page

    def detect(self, images):
        return self._per_page


def _blob_writer():
    written = []
    return written, (lambda data, content_type=None: written.append(data) or f"blob{len(written)}")


def test_two_phase_ingest_embeds_text_before_figures(monkeypatch):
    indexer = RecordingIndexer()
    monkeypatch.setattr(materialize, "_emit_phase_signal", lambda asset_id, phase: None)
    page = Image.new("RGB", (100, 200), "white")
    layer = _TextLayer(
        pages_text=["Body text. See Figure 1."],
        candidates=[[{"bbox": (10, 10, 90, 40), "page": 1, "text": "Figure 1 shows the setup."}]],
        region_texts={(10, 50, 90, 150): "Figure 1"},
    )
    detector = _Detector([[LayoutBlock((10, 50, 90, 150), "image", 0.9, "image")]])
    _written, put_blob = _blob_writer()

    stream = materialize.two_phase_ingest(
        indexer, "/w/report.pdf", "asset-1", None, put_blob, "src",
        text_layer=layer, detector=detector,
        render=lambda path, dpi: [page],
        read_text=lambda path: {0: "Body text. See Figure 1."},
        on_phase=lambda asset_id, phase: indexer.ops.append(("signal", phase)),
    )

    kinds = [block.kind for block in stream.blocks]
    assert TEXT in kinds and IMAGE in kinds
    assert all(b.metadata["role"] == ROLE_DOC_IMAGE for b in stream.blocks if b.kind == IMAGE)
    text_id = next(b.block_id for b in stream.blocks if b.kind == TEXT)
    image_id = next(b.block_id for b in stream.blocks if b.kind == IMAGE)
    ops = indexer.ops

    assert ops[0][0] == "delete", "idempotent delete runs first"

    def first(pred):
        return next(i for i, op in enumerate(ops) if pred(op))

    i_text = first(lambda op: op[0] == "insert" and text_id in op[1])
    i_text_ready = first(lambda op: op == ("signal", "text_ready"))
    i_image = first(lambda op: op[0] == "insert" and image_id in op[1])
    i_ready = first(lambda op: op == ("signal", "ready"))
    # Text is inserted and flushed and signalled retrievable before the figure.
    assert i_text < i_text_ready < i_image < i_ready
    assert sum(1 for op in ops if op == ("flush",)) == 2, "one flush per phase"
    assert layer.closed


def test_two_phase_ingest_scanned_pdf_is_one_phase(monkeypatch):
    indexer = RecordingIndexer()
    monkeypatch.setattr(materialize, "_emit_phase_signal", lambda a, phase: None)
    page = Image.new("RGB", (100, 100), "white")
    layer = _TextLayer(pages_text=[""])  # no text layer -> scanned
    detector = _Detector([[LayoutBlock((10, 10, 90, 40), "text", 0.9, "text")]])
    _written, put_blob = _blob_writer()

    stream = materialize.two_phase_ingest(
        indexer, "/w/scan.pdf", "a1", None, put_blob, "src",
        text_layer=layer, detector=detector, ocr=lambda image, context=None: "scanned text",
        render=lambda path, dpi: [page],
        on_phase=lambda asset_id, phase: indexer.ops.append(("signal", phase)),
    )

    insert_index = next(i for i, op in enumerate(indexer.ops) if op[0] == "insert")
    text_ready_index = indexer.ops.index(("signal", "text_ready"))
    ready_index = indexer.ops.index(("signal", "ready"))
    assert insert_index < text_ready_index < ready_index
    assert [block.kind for block in stream.blocks] == [TEXT]
    assert stream.blocks[0].text == "scanned text"


def test_two_phase_ingest_degrades_to_text_only_when_figures_fail(monkeypatch):
    monkeypatch.setattr(materialize, "_emit_phase_signal", lambda a, p: None)
    indexer = RecordingIndexer()
    page = Image.new("RGB", (100, 200), "white")
    layer = _TextLayer(pages_text=["Body text."])

    class BoomDetector:
        def detect(self, images):
            raise RuntimeError("detect boom")

    _written, put_blob = _blob_writer()
    stream = materialize.two_phase_ingest(
        indexer, "/w/report.pdf", "a1", None, put_blob, "src",
        text_layer=layer, detector=BoomDetector(),
        render=lambda path, dpi: [page],
        read_text=lambda path: {0: "Body text."},
    )

    # Figures blew up, but the text still landed and the stream is text-only.
    assert [block.kind for block in stream.blocks] == [TEXT]
    assert stream.blocks[0].text == "Body text."


# --- two_phase_structured: a docx/pptx/xlsx/html file, text first --------------


def _html_with_image(tmp_path) -> str:
    """An HTML file with prose, an embedded picture and a table -- no binary parser
    needed, so the two-phase orchestration can be tested on a real path."""
    import base64
    from io import BytesIO

    buffer = BytesIO()
    Image.new("RGB", (8, 8), (10, 20, 30)).save(buffer, format="PNG")
    data_uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    path = tmp_path / "page.html"
    path.write_text(
        f"<html><body><p>Intro prose about the mount.</p>"
        f'<img src="{data_uri}" alt="camera mount"/>'
        f"<table><tr><th>name</th><th>value</th></tr>"
        f"<tr><td>temp</td><td>42</td></tr></table></body></html>",
        encoding="utf-8",
    )
    return str(path)


def test_two_phase_structured_embeds_text_before_figures(monkeypatch, tmp_path):
    monkeypatch.setattr(materialize, "_emit_phase_signal", lambda a, p: None)
    indexer = RecordingIndexer()
    _written, put_blob = _blob_writer()

    stream = materialize.two_phase_structured(
        indexer, _html_with_image(tmp_path), "asset-1", None, put_blob, "src",
        on_phase=lambda asset_id, phase: indexer.ops.append(("signal", phase)),
    )

    kinds = [block.kind for block in stream.ordered()]
    assert TEXT in kinds and IMAGE in kinds
    assert all(b.metadata["role"] == ROLE_DOC_IMAGE for b in stream.blocks if b.kind == IMAGE)
    text_ids = {b.block_id for b in stream.blocks if b.kind != IMAGE}
    image_id = next(b.block_id for b in stream.blocks if b.kind == IMAGE)
    ops = indexer.ops

    assert ops[0][0] == "delete", "idempotent delete runs first"

    def first(pred):
        return next(i for i, op in enumerate(ops) if pred(op))

    i_text = first(lambda op: op[0] == "insert" and text_ids & set(op[1]))
    i_text_ready = first(lambda op: op == ("signal", "text_ready"))
    i_image = first(lambda op: op[0] == "insert" and image_id in op[1])
    i_ready = first(lambda op: op == ("signal", "ready"))
    # Text is inserted, flushed and signalled retrievable before the figure.
    assert i_text < i_text_ready < i_image < i_ready
    assert sum(1 for op in ops if op == ("flush",)) == 2, "one flush per phase"
    # Phase 2 embeds only the figure, never re-embedding a text node.
    embeds_after_text_ready = [op[1] for i, op in enumerate(ops)
                               if op[0] == "embed" and i > i_text_ready]
    assert embeds_after_text_ready == [[image_id]]


def test_two_phase_structured_degrades_to_text_only_when_extract_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(materialize, "_emit_phase_signal", lambda a, p: None)
    indexer = RecordingIndexer()
    _written, put_blob = _blob_writer()

    def boom(*args, **kwargs):
        raise RuntimeError("walk boom")

    # Fail the structured walk; the fallback is a plain extraction the sync finishes,
    # and the partial insert is cleaned up with a second delete.
    monkeypatch.setattr("core.structured.extract_structured", boom)
    path = tmp_path / "notes.txt"
    path.write_text("just prose", encoding="utf-8")

    stream = materialize.two_phase_structured(
        indexer, str(path), "a1", None, put_blob, "src",
    )

    # It did not raise: a stream came back for the sync to finish, the partial
    # insert was cleaned up, and nothing figure-like survived the failure.
    assert stream.asset_id == "a1"
    assert [op for op in indexer.ops if op[0] == "delete"], "partial insert cleaned up"
    assert not any(block.kind == IMAGE for block in stream.blocks)
