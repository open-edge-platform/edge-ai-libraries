# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Materialization follows per-asset sync results, not a successful sync call."""

from types import SimpleNamespace

import pytest

from assetlib.pool import AssetPool, SourceSyncStatus
from core import extractor, materialize
from core.file_asset_library import FileAsset, FileAssetLibrary, asset_id_for, file_origin
from core.multimodal import captioning, transcription
from schemas import AssetOut
from tests.test_asset_pool import FakeProjection
from tests.test_mm_ingest_integration import _Library, _TextProjection, _registry, _stream


class _Projection:
    def __init__(self, source_id, extension="", enabled=True):
        self.source = SimpleNamespace(source_id=source_id, enabled=enabled)
        self.extension = extension

    def accepts(self, asset):
        return not self.extension or asset.extension == self.extension


@pytest.fixture
def setup_ingest(monkeypatch):
    monkeypatch.setattr(materialize, "_PHASES", {})
    monkeypatch.setattr(extractor, "extract", lambda path, aid, writer: _stream(aid))
    library = _Library()
    _registry(monkeypatch, library)

    def create_asset(origin, stream, source_id):
        return FileAsset(stream.asset_id, origin=origin, cached=stream)

    monkeypatch.setattr(library, "create_asset", create_asset)
    return library


def _pool(projections=(), *, unavailable=None):
    statuses = {
        p.source.source_id: SourceSyncStatus(p.source.source_id)
        for p in projections
    }
    for source_id in unavailable or {}:
        statuses[source_id] = SourceSyncStatus(source_id, status="failed", error="model not loaded")
    return AssetPool("p", "target", tuple(projections), source_statuses=statuses,
                     unavailable_sources=unavailable or {})


def _ingest(library, paths=("/not-read/report.txt",), pool_ids=("p",)):
    ids = [asset_id_for(file_origin(path)) for path in paths]
    materialize.begin_materialization(ids)
    materialize.ingest(library, paths, "", "", pool_ids, "content-1")
    return ids


@pytest.mark.parametrize("raises", [False, True], ids=["recorded-failure", "raised-failure"])
def test_sync_failure_is_failed_even_if_sync_does_not_raise(setup_ingest, raises):
    library = setup_ingest
    pool = _pool([_Projection("source")])
    library.asset_pools["p"] = pool

    def sync(pool_id):
        pool.source_statuses["source"].mark_failed("embedding failed")
        if raises:
            raise RuntimeError("backend unreachable")

    library.sync_asset_pool = sync
    aid, = _ingest(library)

    assert materialize.materialization_phase(aid) == "failed"
    assert library.events[-1] == ("save",)


@pytest.mark.parametrize("raises", [False, True])
def test_sync_failure_only_marks_assets_the_failed_target_accepts(setup_ingest, raises):
    library = setup_ingest
    pdf, text = _Projection("pdf", "pdf"), _Projection("text", "txt")
    pool = _pool([pdf, text])
    library.asset_pools["p"] = pool

    def sync(pool_id):
        pool.source_statuses["pdf"].mark_failed("PDF embedding failed")
        pool.source_statuses["text"].mark_ready(pool.revision, pool.asset_ids)
        if raises:
            # A separate target pool can also fail; it still must not condemn
            # assets no projection in that pool accepts.
            if pool_id == "pdf-only":
                raise RuntimeError("PDF backend unreachable")

    if raises:
        library.asset_pools["pdf-only"] = _pool([pdf])
    library.sync_asset_pool = sync
    pdf_id, text_id = _ingest(
        library, ("/not-read/report.pdf", "/not-read/report.txt"), tuple(library.asset_pools),
    )

    assert materialize.materialization_phase(pdf_id) == "failed"
    assert materialize.materialization_phase(text_id) == "ready"


@pytest.mark.parametrize("enabled, state, asset_types, expected", [
    (True, "SERVING", ["txt"], "failed"),
    (True, "PREPARING", ["txt"], "failed"),
    (False, "SERVING", ["txt"], "ready"),
    (True, "DEGRADE", ["txt"], "ready"),
    (True, "SERVING", ["pdf"], "ready"),
])
def test_unloaded_sources_fail_only_their_actual_active_targets(
    setup_ingest, enabled, state, asset_types, expected,
):
    library = setup_ingest
    source = SimpleNamespace(
        source_id="unloaded", enabled=enabled, configuration={"asset_types": asset_types},
    )
    pool = _pool(unavailable={source.source_id: source})
    pool.source_statuses[source.source_id].serving_state = state
    library.asset_pools["p"] = pool

    aid, = _ingest(library)

    assert materialize.materialization_phase(aid) == expected


@pytest.mark.parametrize("state", ["DISABLED", "DEGRADE", "frozen"])
def test_frozen_failed_sources_do_not_fail_materialization(setup_ingest, state):
    library = setup_ingest
    projection = _Projection("source", enabled=state != "DISABLED")
    pool = _pool([projection])
    pool.source_statuses["source"].mark_failed("old failure")
    if state == "DEGRADE":
        pool.source_statuses["source"].serving_state = state
    if state == "frozen":
        pool.freeze("source")
    library.asset_pools["p"] = pool

    aid, = _ingest(library)

    assert materialize.materialization_phase(aid) == "ready"


def test_failure_in_a_replaced_assets_existing_pool_is_not_lost(setup_ingest):
    library = setup_ingest
    aid = asset_id_for(file_origin("/not-read/report.txt"))
    library.assets[aid] = FileAsset(aid)
    existing = _pool([_Projection("old")])
    existing.asset_ids.append(aid)
    existing.source_statuses["old"].mark_failed("old pool unavailable")
    library.asset_pools.update(p=_pool(), existing=existing)

    _ingest(library)

    assert materialize.materialization_phase(aid) == "failed"
    assert ("sync", "existing") in library.events


def test_failure_does_not_change_sync_caption_transcript_order(setup_ingest, monkeypatch):
    library = setup_ingest
    pool = _pool([_Projection("source")])
    library.asset_pools["p"] = pool
    monkeypatch.setattr(captioning, "needs_caption", lambda stream: True)
    monkeypatch.setattr(transcription, "needs_transcript", lambda stream: True)

    def sync(pool_id):
        library.events.append(("sync", pool_id))
        pool.source_statuses["source"].mark_failed("write failed")

    def job(name, aid):
        assert materialize.materialization_phase(aid) == "failed"
        # Neither a late phase signal nor a successful enrichment may erase it.
        materialize._emit_phase_signal(aid, "ready")
        library.events.append((name, aid))
        return captioning.STATUS_COMPLETED

    library.sync_asset_pool = sync
    monkeypatch.setattr(captioning, "caption_asset", lambda lib, aid: job("caption", aid))
    monkeypatch.setattr(transcription, "transcribe_asset", lambda lib, aid: job("transcript", aid))

    aid, = _ingest(library)

    assert materialize.materialization_phase(aid) == "failed"
    assert [e[0] for e in library.events if e[0] in {"sync", "caption", "transcript"}] == [
        "sync", "caption", "sync", "transcript", "sync",
    ]


def test_failure_is_sticky_until_a_new_materialization_attempt():
    aid = "retry-status-asset"
    materialize.begin_materialization([aid])
    materialize._set_phase(aid, "failed")
    materialize._set_phase(aid, "text_ready")
    materialize._set_phase(aid, "ready")
    assert materialize.materialization_phase(aid) == "failed"

    materialize.begin_materialization([aid])
    assert materialize.materialization_phase(aid) == "materializing"
    materialize._set_phase(aid, "ready")
    assert materialize.materialization_phase(aid) == "ready"


def test_asset_schema_accepts_a_failed_materialization_phase():
    asset = AssetOut(id="a", name="a", origin="", kind="document", materialization="failed")

    assert asset.materialization == "failed"


def test_a_raised_sync_without_source_bookkeeping_still_fails(setup_ingest):
    library = setup_ingest
    library.asset_pools["p"] = SimpleNamespace(projections=(), serving=(), asset_ids=[])

    def sync(pool_id):
        raise RuntimeError("backend unreachable")

    library.sync_asset_pool = sync
    aid, = _ingest(library)

    assert materialize.materialization_phase(aid) == "failed"


def test_two_phase_ready_is_superseded_by_failed_final_sync(setup_ingest, monkeypatch):
    library = setup_ingest
    primary = _TextProjection("primary")
    primary.source = SimpleNamespace(source_id="primary")
    pool = _pool([primary])
    library.asset_pools["p"] = pool

    def two_phase(indexer, path, aid, metadata, writer, source_id):
        assert indexer is primary
        materialize._emit_phase_signal(aid, "text_ready")
        materialize._emit_phase_signal(aid, "ready")
        return _stream(aid)

    def sync(pool_id):
        assert all(materialize.materialization_phase(aid) == "ready" for aid in pool.asset_ids)
        pool.source_statuses["primary"].mark_failed("final sync failed")

    monkeypatch.setattr(materialize, "two_phase_ingest", two_phase)
    library.sync_asset_pool = sync
    aid, = _ingest(library, ("/not-read/report.pdf",))

    assert materialize.materialization_phase(aid) == "failed"


@pytest.mark.parametrize("raises", [False, True])
def test_later_enrichment_sync_failure_cannot_be_erased_by_success(
    setup_ingest, monkeypatch, raises,
):
    library = setup_ingest
    pool = _pool([_Projection("source")])
    library.asset_pools["p"] = pool
    monkeypatch.setattr(captioning, "needs_caption", lambda stream: True)
    monkeypatch.setattr(transcription, "needs_transcript", lambda stream: True)
    sync_count = 0

    def sync(pool_id):
        nonlocal sync_count
        sync_count += 1
        library.events.append(("sync", pool_id))
        status = pool.source_statuses["source"]
        if sync_count == 2:
            if raises:
                raise RuntimeError("enrichment sync failed")
            status.mark_failed("enrichment sync failed")
        else:
            status.mark_ready(pool.revision, pool.asset_ids)

    def job(name, aid):
        expected = "ready" if name == "caption" else "failed"
        assert materialize.materialization_phase(aid) == expected
        library.events.append((name, aid))
        return captioning.STATUS_COMPLETED

    library.sync_asset_pool = sync
    monkeypatch.setattr(captioning, "caption_asset", lambda lib, aid: job("caption", aid))
    monkeypatch.setattr(transcription, "transcribe_asset", lambda lib, aid: job("transcript", aid))
    aid, = _ingest(library)

    assert materialize.materialization_phase(aid) == "failed"
    assert [e[0] for e in library.events if e[0] in {"sync", "caption", "transcript"}] == [
        "sync", "caption", "sync", "transcript", "sync",
    ]
    assert library.events[-1] == ("save",)


def test_real_pool_sync_records_failure_without_raising_and_reingest_recovers(monkeypatch):
    monkeypatch.setattr(materialize, "_PHASES", {})
    monkeypatch.setattr(extractor, "extract", lambda path, aid, writer: _stream(aid))
    library = FileAssetLibrary("real-sync", databasehub=SimpleNamespace())
    library.events = []
    _registry(monkeypatch, library)
    monkeypatch.setattr(library, "blob_writer", lambda source_id: lambda *args: "unused")
    monkeypatch.setattr(
        library, "create_asset",
        lambda origin, stream, source_id: FileAsset(stream.asset_id, origin=origin, cached=stream),
    )
    projection = FakeProjection(fail_times=1)
    pool = AssetPool("p", "real-sync")
    pool.set_projections([projection])
    library._asset_pools["p"] = pool
    library._sources[projection.source.source_id] = projection.source

    aid, = _ingest(library)

    status = pool.source_statuses[projection.source.source_id]
    assert status.status == "failed" and "backend unavailable" in status.error
    assert materialize.materialization_phase(aid) == "failed"
    assert aid in status.stale_asset_ids

    _ingest(library)

    assert status.status == "ready" and status.error is None
    assert materialize.materialization_phase(aid) == "ready"
    assert status.indexed_asset_ids == [aid] and status.stale_asset_ids == []