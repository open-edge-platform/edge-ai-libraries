# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import queue
import threading
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

import config

logger = logging.getLogger(__name__)

# End-of-stream marker put on the queue by the producer.
_SENTINEL = object()


def streaming_materialize(
    indexer: Any,
    assets: Sequence[Any],
    *,
    batch_size: Optional[int] = None,
    queue_max: Optional[int] = None,
) -> Dict[str, int]:
    """Embed and insert `assets`' nodes through a bounded producer/consumer queue."""
    batch_size = batch_size or config.INGEST_BATCH_SIZE
    queue_max = queue_max or config.INGEST_QUEUE_MAX
    work: "queue.Queue[Any]" = queue.Queue(maxsize=queue_max)
    state: Dict[str, Any] = {"error": None}
    cancelled = threading.Event()

    def put(item: Any) -> bool:
        # Polling put so the producer is not stranded on a full queue after a consumer failure.
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
        except Exception as error:  # noqa: BLE001
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
            first = work.get()
            if first is _SENTINEL:
                break
            batch: List[Any] = [first]
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
# Process-local and not persisted; bounded to _PHASE_MAX entries.
_PHASES: "Dict[str, str]" = {}
_PHASE_LOCK = threading.Lock()
_PHASE_MAX = 1000


def _set_phase(asset_id: str, phase: str) -> None:
    with _PHASE_LOCK:
        # "failed" sticks until a new materialization attempt starts.
        if _PHASES.get(asset_id) == "failed" and phase != "materializing":
            return
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

# (pool_id, asset_id) -> number of in-flight ingests
_INGESTING: "Dict[tuple, int]" = {}
_INGESTING_LOCK = threading.Lock()


def _begin_ingesting(pool_ids: Sequence[str], asset_ids: Sequence[str]) -> List[tuple]:
    keys = [(pool_id, asset_id) for pool_id in dict.fromkeys(pool_ids) for asset_id in dict.fromkeys(asset_ids)]
    with _INGESTING_LOCK:
        for key in keys:
            _INGESTING[key] = _INGESTING.get(key, 0) + 1
    return keys


def _end_ingesting(keys: Sequence[tuple]) -> None:
    with _INGESTING_LOCK:
        for key in keys:
            count = _INGESTING.get(key, 0) - 1
            if count > 0:
                _INGESTING[key] = count
            else:
                _INGESTING.pop(key, None)


def ingesting_asset_ids(pool_id: Optional[str]) -> frozenset:
    with _INGESTING_LOCK:
        return frozenset(asset_id for pool, asset_id in _INGESTING if pool == pool_id)


_ACTIVE_INGESTS: "Dict[tuple, int]" = {}


def _begin_active(library_id: Optional[str], pool_ids: Sequence[str]) -> List[tuple]:
    keys = [(library_id, None)] + [(library_id, pool_id) for pool_id in dict.fromkeys(pool_ids)]
    with _INGESTING_LOCK:
        for key in keys:
            _ACTIVE_INGESTS[key] = _ACTIVE_INGESTS.get(key, 0) + 1
    return keys


def _end_active(keys: Sequence[tuple]) -> None:
    with _INGESTING_LOCK:
        for key in keys:
            count = _ACTIVE_INGESTS.get(key, 0) - 1
            if count > 0:
                _ACTIVE_INGESTS[key] = count
            else:
                _ACTIVE_INGESTS.pop(key, None)


def ingest_active(library_id: Optional[str] = None, pool_id: Optional[str] = None) -> bool:
    with _INGESTING_LOCK:
        if library_id is None:
            return bool(_ACTIVE_INGESTS)
        return (library_id, pool_id) in _ACTIVE_INGESTS


def _emit_phase_signal(asset_id: str, phase: str) -> None:
    # "ready" is only logged here; `ingest` records it after all pools are synced.
    logger.info("materialize phase %s: asset=%s", phase, asset_id)
    if phase != "ready":
        _set_phase(asset_id, phase)


def _embed_insert_batched(indexer: Any, items: Any, batch_size: int) -> int:
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
    """Materialize a PDF into `indexer` in two flushed phases, text first; falls back to plain extraction."""
    import config
    from core.extractor import extract_pdf

    indexer.delete_by_metadata("asset_id", [asset_id])
    try:
        return _two_phase(
            indexer, path, asset_id, metadata, put_blob, source_id,
            dpi=dpi, detector=detector, ocr=ocr, render=render,
            text_layer=text_layer, read_text=read_text,
            batch_size=config.INGEST_BATCH_SIZE,
            on_phase=on_phase,
        )
    except Exception:  # noqa: BLE001
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

        # `layer` must be used by one thread at a time: pdfplumber/PDFium is not thread-safe.
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
            except Exception as error:  # noqa: BLE001
                visual_state["error"] = error

        worker = threading.Thread(
            target=_extract_visual, name="extract-visual", daemon=True
        )
        worker.start()

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

        # Read against the full stream so a figure's surrounding_text sees the prose.
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
    """Materialize a structured file into `indexer` in two flushed phases, text first."""
    import config
    from types import SimpleNamespace

    from core.content import BINARY_KINDS
    from core.structured import extract_structured

    batch_size = config.INGEST_BATCH_SIZE
    indexer.delete_by_metadata("asset_id", [asset_id])

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

        if text_ids:
            _embed_insert_batched(
                indexer,
                indexer.iter_node_items(asset, only_block_ids=text_ids),
                batch_size,
            )
            indexer.flush()
        _signal("text_ready")

        if image_ids:
            _embed_insert_batched(
                indexer,
                indexer.iter_node_items(asset, only_block_ids=image_ids),
                batch_size,
            )
            indexer.flush()
        _signal("ready")
        return full
    except Exception:  # noqa: BLE001
        logger.exception(
            "Two-phase structured ingest failed for %s; falling back to extract", path
        )
        indexer.delete_by_metadata("asset_id", [asset_id])
        from core.extractor import extract

        return extract(path, asset_id, put_blob, metadata)


def _asset_sync_failed(pool: Any, asset: Any, sync_failed: bool) -> bool:
    """Whether a non-frozen sync target that accepts this asset failed or is unavailable."""
    from assetlib.sources import binding
    from core.indexer import accepts_asset
    from core.multimodal.routing import effective_configuration

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
        if accepts_asset(asset, effective_configuration(source)):
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
    """Run a media job and sync the pools its completed results made stale."""
    from core.manager import registry
    from core.multimodal import captioning

    try:
        done = []
        for asset_id in asset_ids:
            try:
                if job(library, asset_id) == captioning.STATUS_COMPLETED:
                    done.append(asset_id)
            except Exception:  # noqa: BLE001
                logger.exception("Enrichment failed for asset %s", asset_id)
        # Never hold the registry lock across a job or sync; they may take minutes.
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
            except Exception:  # noqa: BLE001
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
    from core.file_asset_library import asset_id_for, file_origin, inline_origin

    asset_ids = [asset_id_for(file_origin(path)) for path in file_paths]
    if text:
        asset_ids.append(asset_id_for(inline_origin(text_reference)))
    keys = _begin_ingesting(pool_ids, asset_ids)
    active = _begin_active(getattr(library, "idx", None), pool_ids)
    try:
        _ingest(library, file_paths, text, text_reference, pool_ids, source_id)
    finally:
        _end_ingesting(keys)
        _end_active(active)


def _ingest(
    library: Any,
    file_paths: Sequence[str],
    text: str,
    text_reference: str,
    pool_ids: Sequence[str],
    source_id: str,
) -> None:
    """Extract, store, register and index assets in the background."""
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
        """First serving text vector projection in the target pools that accepts this origin."""
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
        except Exception:  # noqa: BLE001 - skip one bad file, keep the batch
            logger.exception("Extraction failed for %s", path)
            continue
        if not stream.blocks:
            continue
        assets.append(
            library.create_asset(origin=origin, stream=stream, source_id=source_id)
        )
        stored_files.append(path)
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
        # Also sync other pools holding the old version of a replaced asset.
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
        except Exception:  # noqa: BLE001
            sync_failed = True
            logger.exception("Sync failed for pool %s", pool_id)
        _record_sync_failures(library, pool_id, assets, sync_failed)
    registry.save()

    # Does not overwrite a "failed" phase recorded above.
    for asset in assets:
        _set_phase(asset.asset_id, "ready")

    # Order matters: initial sync, then captioning, then transcription.
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
