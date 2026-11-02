# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Streaming materialization: embed an asset's nodes as they are built, off the
request thread.

This module contains two pieces:

- `streaming_materialize` is the producer/consumer engine a vector projection
  embeds through (`core/indexer.py:VectorIndexer.add`). A producer thread builds
  nodes block by block onto a *bounded* queue; this thread is the single consumer
  -- GME is not thread-safe, so only ever one thread embeds -- draining the queue
  into micro-batches, embedding each by modality and inserting it. Bounded so a
  large document applies backpressure rather than building every node before any
  is embedded, and streaming so its early text is searchable without waiting for
  the rest.

- `ingest` is the background task `create_assets` hands the slow work to, so the
  request returns 202 at once instead of blocking on render/detect/OCR. It is the
  same extract -> store -> register -> sync sequence the endpoint used to run
  inline, moved here whole; the embedding inside `sync` now goes through the
  streaming engine above.
"""

import logging
import queue
import threading
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

import config

logger = logging.getLogger(__name__)

# Put on the queue once per producer when it is done, so the consumer knows no
# more nodes are coming. A unique object, never a node, so it cannot be mistaken
# for one.
_SENTINEL = object()


def streaming_materialize(
    indexer: Any,
    assets: Sequence[Any],
    *,
    batch_size: Optional[int] = None,
    queue_max: Optional[int] = None,
) -> Dict[str, int]:
    """Embed and insert `assets`' nodes through a bounded producer/consumer queue.

    The producer thread walks each asset's nodes (`indexer.iter_node_items`) and
    puts `(node, modality, source_id)` onto a queue capped at `queue_max`; the cap
    is the backpressure. This thread drains the queue into batches of up to
    `batch_size`, embeds each (`indexer.embed_items`) and inserts it
    (`indexer.insert_prepared`), then flushes once (`indexer.flush`).

    Any error the producer hits is captured and re-raised here after the threads
    join. A consumer failure cancels queue writes and joins the producer before
    returning, so the caller can safely release its asset/model bindings.
    """
    batch_size = batch_size or config.INGEST_BATCH_SIZE
    queue_max = queue_max or config.INGEST_QUEUE_MAX
    work: "queue.Queue[Any]" = queue.Queue(maxsize=queue_max)
    state: Dict[str, Any] = {"error": None}
    cancelled = threading.Event()

    def put(item: Any) -> bool:
        # A plain blocking put would strand the producer on a full queue after
        # the consumer failed. The sentinel must be cancellable for the same reason.
        while not cancelled.is_set():
            try:
                work.put(item, timeout=0.1)
                return True
            except queue.Full:
                continue
        return False

    def produce() -> None:
        try:
            for asset in assets:
                if cancelled.is_set():
                    return
                for item in indexer.iter_node_items(asset):
                    if not put(item):
                        return
        except Exception as error:  # noqa: BLE001 - re-raised on the consumer
            state["error"] = error
        finally:
            put(_SENTINEL)

    producer = threading.Thread(
        target=produce, name="materialize-producer", daemon=True
    )
    producer.start()

    counts = {"documents_added": len(assets), "chunks_added": 0}
    try:
        done = False
        while not done:
            first = work.get()  # block until the next batch has at least one node
            if first is _SENTINEL:
                break
            batch: List[Any] = [first]
            # Take whatever else is already waiting, up to a full batch, without
            # blocking -- so a batch forms from what is ready rather than stalling.
            while len(batch) < batch_size:
                try:
                    item = work.get_nowait()
                except queue.Empty:
                    break
                if item is _SENTINEL:
                    done = True
                    break
                batch.append(item)
            indexer.embed_items(batch)
            counts["chunks_added"] += indexer.insert_prepared(
                [node for node, _, _ in batch]
            )
    finally:
        cancelled.set()
        producer.join()

    if state["error"] is not None:
        raise state["error"]
    if counts["chunks_added"]:
        indexer.flush()
    return counts


# --- Materialization progress, per asset -------------------------------------
# A process-local record of how far each asset's ingest has got, so the console
# can show "text searchable" before "fully ready". Ingest runs in a background
# task in this same process, so a module-level dict is enough; it is ephemeral by
# design -- after a restart an asset reports no phase and the client just shows
# nothing, which is correct for a live-progress affordance. Bounded so a long-
# lived process cannot accumulate entries without limit.
_PHASES: "Dict[str, str]" = {}
_PHASE_LOCK = threading.Lock()
_PHASE_MAX = 1000


def _set_phase(asset_id: str, phase: str) -> None:
    with _PHASE_LOCK:
        # A later flush/enrichment signal must not hide a failed sync. Only a
        # newly accepted materialization attempt explicitly resets the failure.
        if _PHASES.get(asset_id) == "failed" and phase != "materializing":
            return
        # Re-insert so the most recent asset is last; trim oldest past the cap.
        _PHASES.pop(asset_id, None)
        _PHASES[asset_id] = phase
        while len(_PHASES) > _PHASE_MAX:
            _PHASES.pop(next(iter(_PHASES)))


def begin_materialization(asset_ids: Iterable[str]) -> None:
    """Mark freshly-accepted assets as materializing, before extraction starts."""
    for asset_id in asset_ids:
        _set_phase(asset_id, "materializing")


def materialization_phase(asset_id: str) -> Optional[str]:
    """How far `asset_id`'s ingest has got, or None if untracked (e.g. post-restart)."""
    with _PHASE_LOCK:
        return _PHASES.get(asset_id)


def _emit_phase_signal(asset_id: str, phase: str) -> None:
    """Record that `asset_id` reached a materialization phase, for the client.

    Two phases a client can act on: ``"text_ready"`` (path-1 text embedded and
    flushed, so the prose is retrievable) and ``"ready"`` (path-2 figures in too).
    The phase is both logged and stored in the process-local tracker above, which
    `GET /assets` reports as each asset's ``materialization``.
    """
    logger.info("materialize phase %s: asset=%s", phase, asset_id)
    _set_phase(asset_id, phase)


def _embed_insert_batched(indexer: Any, items: Any, batch_size: int) -> int:
    """Embed and insert nodes in batches of `batch_size`; return how many landed.

    The non-overlapping sibling of `streaming_materialize`: a two-phase ingest
    already overlaps path-2 extraction with path-1 embedding at the phase level, so
    within a phase a plain batched loop -- no queue, no extra thread -- keeps memory
    bounded while reusing the same embed/insert primitives.
    """
    count = 0
    batch: List[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) >= batch_size:
            indexer.embed_items(batch)
            count += indexer.insert_prepared([node for node, _, _ in batch])
            batch = []
    if batch:
        indexer.embed_items(batch)
        count += indexer.insert_prepared([node for node, _, _ in batch])
    return count


def two_phase_ingest(
    indexer: Any,
    path: str,
    asset_id: str,
    metadata: Any,
    put_blob: Any,
    source_id: Optional[str],
    *,
    dpi: Optional[int] = None,
    detector: Any = None,
    ocr: Any = None,
    render: Any = None,
    text_layer: Any = None,
    read_text: Any = None,
    on_phase: Optional[Callable[[str, str], None]] = None,
) -> Any:
    """Materialize a PDF into `indexer` in two flushed phases, text first.

    Path 1 (text layer) is embedded and flushed before path 2 (figures), so a
    digital PDF's prose is retrievable while its figures are still being rendered
    and detected -- that slow extraction runs, overlapped, on a worker thread.
    Returns the full `ContentStream` for the caller to persist. `on_phase`, when
    supplied, observes the same ``text_ready`` and ``ready`` milestones emitted
    by production without replacing the normal phase signal.

    Self-contained on failure: on any unexpected error it drops whatever it had
    inserted for this asset and falls back to a plain full extraction, so the
    projection is left either fully holding the asset or not at all -- never half --
    and the ordinary sync can finish it.
    """
    import config
    from core.extractor import extract_pdf

    indexer.delete_by_metadata("asset_id", [asset_id])  # idempotent re-ingest
    try:
        return _two_phase(
            indexer, path, asset_id, metadata, put_blob, source_id,
            dpi=dpi, detector=detector, ocr=ocr, render=render,
            text_layer=text_layer, read_text=read_text,
            batch_size=config.INGEST_BATCH_SIZE,
            on_phase=on_phase,
        )
    except Exception:  # noqa: BLE001 - clean up partial inserts and fall back
        logger.exception("Two-phase ingest failed for %s; falling back to extract", path)
        indexer.delete_by_metadata("asset_id", [asset_id])
        return extract_pdf(
            path, asset_id, put_blob, metadata,
            dpi=dpi, detector=detector, ocr=ocr, render=render,
            read_text=read_text,
        )


def _two_phase(
    indexer, path, asset_id, metadata, put_blob, source_id, *,
    dpi, detector, ocr, render, text_layer, read_text, batch_size, on_phase,
):
    import config
    from types import SimpleNamespace

    from core.extractor import (
        _PdfTextLayer,
        assemble_stream,
        digital_text_blocks,
        digital_visual_blocks,
        extract_layout,
        pdf_has_text_layer,
    )

    dpi = int(dpi if dpi is not None else config.LAYOUT_RENDER_DPI)

    def _asset(stream):
        return SimpleNamespace(
            asset_id=asset_id, content=stream, content_source_id=source_id
        )

    def _signal(phase):
        _emit_phase_signal(asset_id, phase)
        if on_phase is not None:
            on_phase(asset_id, phase)

    layer = text_layer or _PdfTextLayer(path, dpi)
    try:
        try:
            digital = pdf_has_text_layer(layer)
        except Exception:  # noqa: BLE001 - unreadable text layer: treat as scanned
            digital = False

        if not digital:
            # No fast path for a scan: one phase, everything via path 3 (full OCR).
            full = extract_layout(
                path, asset_id, put_blob, metadata,
                detector=detector, ocr=ocr, render=render, dpi=dpi,
            )
            _embed_insert_batched(
                indexer, indexer.iter_node_items(_asset(full)), batch_size
            )
            indexer.flush()
            _signal("text_ready")
            _signal("ready")
            return full

        # Digital. Path-1 text (from the plain-text reader) is extracted here (fast),
        # then embedded while path-2 (slow render/detect) runs on a worker. The
        # pdfplumber `layer` is touched by one thread at a time -- path-1 reads its
        # page count here, finishing before the worker starts, and the main thread
        # touches no pdfplumber document while embedding -- because one
        # pdfplumber/PDFium document is not safe for concurrent access.
        text_blocks = digital_text_blocks(
            path, asset_id, text_layer=layer, read_text=read_text,
        )
        visual_state: Dict[str, Any] = {"blocks": [], "error": None}

        def _extract_visual():
            try:
                visual_state["blocks"] = digital_visual_blocks(
                    path, asset_id, put_blob, text_layer=layer,
                    detector=detector, render=render, dpi=dpi,
                )
            except Exception as error:  # noqa: BLE001 - surfaced after join
                visual_state["error"] = error

        worker = threading.Thread(
            target=_extract_visual, name="extract-visual", daemon=True
        )
        worker.start()

        # Phase 1: embed path-1 text (overlaps the worker's extraction), flush,
        # signal -- the text is retrievable now.
        text_stream = assemble_stream(asset_id, path, metadata, text_blocks)
        _embed_insert_batched(
            indexer, indexer.iter_node_items(_asset(text_stream)), batch_size
        )
        indexer.flush()
        _signal("text_ready")

        worker.join()
        if visual_state["error"] is not None:
            logger.error(
                "Path-2 extraction failed for %s; keeping text only", path,
                exc_info=visual_state["error"],
            )
        visual_blocks = visual_state["blocks"]
        full = assemble_stream(asset_id, path, metadata, text_blocks + visual_blocks)

        # Phase 2: embed only the path-2 blocks, read against the full stream so a
        # figure's surrounding_text sees the prose around it.
        visual_ids = {block.block_id for block in visual_blocks}
        if visual_ids:
            _embed_insert_batched(
                indexer,
                indexer.iter_node_items(_asset(full), only_block_ids=visual_ids),
                batch_size,
            )
            indexer.flush()
        _signal("ready")
        return full
    finally:
        layer.close()


def _structured_two_phase_applies(path: str) -> bool:
    """Whether `path` is a structured file carrying pictures worth a two-phase run.

    Mirrors `extractor.extract`'s routing: a docx/pptx/xlsx/html file with images
    is walked natively (so this two-phase path applies); one with none is left to
    the plain-text reader during the ordinary sync, exactly as before.
    """
    from core import structured

    return bool(structured.structured_kind(path)) and structured.has_media(path)


def two_phase_structured(
    indexer: Any,
    path: str,
    asset_id: str,
    metadata: Any,
    put_blob: Any,
    source_id: Optional[str],
    *,
    on_phase: Optional[Callable[[str, str], None]] = None,
) -> Any:
    """Materialize a structured file into `indexer` in two flushed phases, text first.

    The same payoff as the PDF two-phase -- a document's prose is retrievable
    before its figures' (slower) fused vectors are computed -- but simpler to
    reach: a docx/pptx/xlsx/html walk has no render/detect to overlap, so there is
    no worker thread, just embed-text-flush then embed-figures-flush. Phase 2 reads
    the figures against the *full* stream, so a figure's `surrounding_text` still
    sees the prose around it. Returns the full `ContentStream` for the caller to
    persist.

    Self-contained on failure: drops whatever it inserted for this asset and falls
    back to a plain extraction, so the projection holds the asset fully or not at
    all, and the ordinary sync can finish it.
    """
    import config
    from types import SimpleNamespace

    from core.content import BINARY_KINDS
    from core.structured import extract_structured

    batch_size = config.INGEST_BATCH_SIZE
    indexer.delete_by_metadata("asset_id", [asset_id])  # idempotent re-ingest

    def _asset(stream):
        return SimpleNamespace(
            asset_id=asset_id, content=stream, content_source_id=source_id
        )

    def _signal(phase):
        _emit_phase_signal(asset_id, phase)
        if on_phase is not None:
            on_phase(asset_id, phase)

    try:
        full = extract_structured(path, asset_id, put_blob, metadata)
        asset = _asset(full)
        text_ids = {b.block_id for b in full.blocks if b.kind not in BINARY_KINDS}
        image_ids = {b.block_id for b in full.blocks if b.kind in BINARY_KINDS}

        # Phase 1: text and tables embedded and flushed -- the prose is retrievable
        # now, without waiting on the figures' fused vectors.
        if text_ids:
            _embed_insert_batched(
                indexer,
                indexer.iter_node_items(asset, only_block_ids=text_ids),
                batch_size,
            )
            indexer.flush()
        _signal("text_ready")

        # Phase 2: the figures, read against the full stream so a figure's
        # surrounding_text sees the prose around it.
        if image_ids:
            _embed_insert_batched(
                indexer,
                indexer.iter_node_items(asset, only_block_ids=image_ids),
                batch_size,
            )
            indexer.flush()
        _signal("ready")
        return full
    except Exception:  # noqa: BLE001 - clean up partial inserts and fall back
        logger.exception(
            "Two-phase structured ingest failed for %s; falling back to extract", path
        )
        indexer.delete_by_metadata("asset_id", [asset_id])
        from core.extractor import extract

        return extract(path, asset_id, put_blob, metadata)


def _asset_sync_failed(pool: Any, asset: Any, sync_failed: bool) -> bool:
    """Whether an active sync target for this asset failed, including unloads.

    Pool sync normally records failures per source rather than raising. Asset
    filters still apply to those records: another file type's failed source
    must not condemn this asset. Preparing targets take writes; frozen ones do
    not. Minimal libraries without per-source bookkeeping retain their ordinary
    success/exception semantics.
    """
    from assetlib.sources import binding
    from core.indexer import accepts_asset

    if pool is None:
        return sync_failed
    if asset.asset_id not in pool.asset_ids:
        return False
    projections = getattr(pool, "projections", ())
    unavailable = getattr(pool, "unavailable_sources", {})
    frozen = getattr(pool, "frozen_sources", {})
    statuses = getattr(pool, "source_statuses", {})
    if not projections and not unavailable:
        return sync_failed and not frozen
    for projection in projections:
        source = getattr(projection, "source", None)
        source_id = getattr(source, "source_id", None)
        status = statuses.get(source_id)
        if source_id in frozen or binding.is_frozen(source, status):
            continue
        if (sync_failed or getattr(status, "status", None) == "failed") and projection.accepts(asset):
            return True
    for source_id, source in unavailable.items():
        if source_id in frozen or binding.is_frozen(source, statuses.get(source_id)):
            continue
        if accepts_asset(asset, source.configuration):
            # No projection means this target could not be synced, even if the
            # outer pool sync completed and did not raise an exception.
            return True
    return False


def _record_sync_failures(
    library: Any, pool_id: str, assets: Sequence[Any], sync_failed: bool,
) -> None:
    pool = library.asset_pools.get(pool_id)
    for asset in assets:
        if _asset_sync_failed(pool, asset, sync_failed):
            _set_phase(asset.asset_id, "failed")


def _enrich_and_save(library: Any, asset_ids: Sequence[str], job: Callable) -> None:
    """Run a media job and sync the pools its completed results made stale.

    The jobs own the per-asset read/modify/write lock and record model failures
    on the stream. Do not hold the registry lock across a job or a sync: both
    may load a model and take minutes. Only snapshot pool membership under it;
    `registry.save` takes the same reentrant lock while persisting. Even an
    unexpected job or sync failure must not lose already-recorded job status or
    prevent the remaining assets (and the later transcription pass) from running.
    """
    from core.manager import registry
    from core.multimodal import captioning

    try:
        done = []
        for asset_id in asset_ids:
            try:
                if job(library, asset_id) == captioning.STATUS_COMPLETED:
                    done.append(asset_id)
            except Exception:  # noqa: BLE001 - isolate a failed background job
                logger.exception("Enrichment failed for asset %s", asset_id)
        with registry.lock:
            pool_ids = [
                pool_id
                for pool_id, pool in library.asset_pools.items()
                if any(asset_id in pool.asset_ids for asset_id in done)
            ]
        for pool_id in pool_ids:
            sync_failed = False
            try:
                library.sync_asset_pool(pool_id)
            except Exception:  # noqa: BLE001 - leave its failure on pool status
                sync_failed = True
                logger.exception("Enrichment sync failed for pool %s", pool_id)
            _record_sync_failures(
                library, pool_id,
                [library.assets[asset_id] for asset_id in done if asset_id in library.assets],
                sync_failed,
            )
    finally:
        registry.save()


def ingest(
    library: Any,
    file_paths: Sequence[str],
    text: str,
    text_reference: str,
    pool_ids: Sequence[str],
    source_id: str,
) -> None:
    """Extract, store, register and index assets -- the whole slow path, in the
    background.

    This is exactly what `create_assets` used to do inline, lifted out so the
    endpoint can return 202 before any of it runs. Extraction is slow and
    holds no lock; the registry lock wraps only the fast bookkeeping (registering
    the assets, adding them to pools, recording provenance). A file that fails to
    extract is logged and skipped rather than failing the batch -- the client
    already has its 202, and the rest of the batch should still land.
    """
    from core.content import ContentStream
    from core.extractor import extract
    from core.file_asset_library import FileAsset, asset_id_for, file_origin, inline_origin
    from core.indexer import MultimodalIndexer, VectorIndexer
    from core.loader import text_to_documents
    from core.manager import registry
    from core.knowledge.okf import is_okf
    from core.multimodal import captioning, transcription

    import os

    def _primary_vector_projection(origin: str):
        """The first serving text vector across the target pools that accepts this
        asset, judged from its origin alone -- so a PDF can be embedded straight
        off the two-phase pipeline (text first) rather than extracted then synced.
        Everything else (graph sources, other vector sources, other pools) is left
        to the ordinary sync over the persisted stream.
        """
        probe = FileAsset(asset_id=asset_id_for(origin), origin=origin)
        for pool_id in pool_ids:
            pool = library.asset_pools.get(pool_id)
            if pool is None:
                continue
            for projection in pool.serving:
                if (
                    isinstance(projection, VectorIndexer)
                    and not isinstance(projection, MultimodalIndexer)
                    and projection.accepts(probe)
                ):
                    return projection
        return None

    put_blob = library.blob_writer(source_id)
    assets: List[Any] = []
    stored_files: List[str] = []
    caption_ids: List[str] = []
    transcript_ids: List[str] = []
    for path in file_paths:
        origin = file_origin(path)
        if is_okf(path):
            assets.append(library.create_okf_asset(origin))
            stored_files.append(path)
            continue
        asset_id = asset_id_for(origin)
        primary = _primary_vector_projection(origin)
        try:
            if primary is not None and path.lower().endswith(".pdf"):
                stream = two_phase_ingest(
                    primary, path, asset_id, None, put_blob, source_id
                )
            elif primary is not None and _structured_two_phase_applies(path):
                stream = two_phase_structured(
                    primary, path, asset_id, None, put_blob, source_id
                )
            else:
                stream = extract(path, asset_id, put_blob)
        except Exception:  # noqa: BLE001 - one bad file must not sink the batch
            logger.exception("Extraction failed for %s", path)
            continue
        if not stream.blocks:
            continue
        assets.append(
            library.create_asset(origin=origin, stream=stream, source_id=source_id)
        )
        stored_files.append(path)
        # These decisions need the extracted stream, which the 202 request did
        # not have. Ask it directly instead of re-reading the content store.
        if captioning.needs_caption(stream):
            caption_ids.append(asset_id)
        if transcription.needs_transcript(stream):
            transcript_ids.append(asset_id)
    if text:
        loaded = text_to_documents(text)
        if loaded:
            origin = inline_origin(text_reference)
            assets.append(
                library.create_asset(
                    origin=origin,
                    stream=ContentStream.from_documents(loaded, asset_id_for(origin)),
                    source_id=source_id,
                )
            )
    if not assets:
        logger.warning("No content could be extracted; nothing to index")
        return

    with registry.lock:
        replaced_asset_ids = [
            asset.asset_id for asset in assets if asset.asset_id in library.assets
        ]
        library.register_assets(assets)
        for pool_id in pool_ids:
            library.add_assets_to_pool(
                pool_id, [asset.asset_id for asset in assets]
            )
        if replaced_asset_ids:
            library.note_assets_changed(replaced_asset_ids)
        for path in stored_files:
            library.file_map[os.path.basename(path)] = path
        # A replaced asset's other pools hold the old version too, so sync them
        # even though this request did not name them.
        sync_pool_ids = list(pool_ids)
        for pool_id, pool in library.asset_pools.items():
            if pool_id not in sync_pool_ids and any(
                asset_id in pool.asset_ids for asset_id in replaced_asset_ids
            ):
                sync_pool_ids.append(pool_id)

    registry.save()
    for pool_id in sync_pool_ids:
        sync_failed = False
        try:
            library.sync_asset_pool(pool_id)
        except Exception:  # noqa: BLE001 - a failed pool is recorded on its status
            sync_failed = True
            logger.exception("Sync failed for pool %s", pool_id)
        _record_sync_failures(library, pool_id, assets, sync_failed)
    registry.save()

    # Successful assets are fully materialized -- figures and graph included.
    # Failed targets above latch "failed", which _set_phase will not overwrite
    # with this final ready or a later phase signal.
    for asset in assets:
        _set_phase(asset.asset_id, "ready")

    # Materialization progress keeps main's meaning: stored blocks are ready,
    # independently of the longer jobs reported by `/enrichment`. Initial sync
    # must finish before captioning, and captioning before transcription.
    if caption_ids:
        _enrich_and_save(library, caption_ids, captioning.caption_asset)
    if transcript_ids:
        _enrich_and_save(library, transcript_ids, transcription.transcribe_asset)


__all__ = [
    "ingest",
    "streaming_materialize",
    "begin_materialization",
    "materialization_phase",
]
