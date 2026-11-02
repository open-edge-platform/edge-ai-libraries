# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The background ingest seam between document/fused and standalone media paths.

No model, database, or running engine is needed: real streams and indexer types
pin primary selection (G3/G20), job ordering (G5), and file ownership (G7).
"""

import asyncio
from contextlib import contextmanager
from threading import RLock
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks

import config
from api import asset_library as asset_library_api
from core import extractor, manager, materialize
from core.content import (
    AUDIO,
    IMAGE,
    ROLE_AUDIO,
    ROLE_IMAGE,
    ROLE_LONG_VIDEO,
    ROLE_SHORT_VIDEO,
    TEXT,
    VIDEO,
    ContentBlock,
    ContentStream,
    file_uri,
)
from core.file_asset_library import asset_id_for, file_origin
from core.indexer import MultimodalIndexer, VectorIndexer
from core.multimodal import captioning, transcription
from schemas import AssetCreateRequest


class _Library:
    name = "library-1"
    library_id = "lib-1"

    def __init__(self, pools=None):
        self.asset_pools = pools or {}
        self.assets = {}
        self.file_map = {}
        self.events = []
        self.blobs = []

    def content_source(self, source_id=None):
        return SimpleNamespace(source_id=source_id or "content-1")

    def blob_writer(self, source_id):
        assert source_id == "content-1"

        def write(data, content_type=None):
            self.blobs.append((data, content_type))
            return f"blob-{len(self.blobs)}"

        return write

    def create_asset(self, origin, stream, source_id):
        self.events.append(("store", stream.asset_id))
        return SimpleNamespace(asset_id=stream.asset_id, origin=origin, content=stream)

    def register_assets(self, assets):
        self.assets.update((asset.asset_id, asset) for asset in assets)
        self.events.append(("register",))

    def add_assets_to_pool(self, pool_id, asset_ids):
        pool = self.asset_pools[pool_id]
        pool.asset_ids.extend(aid for aid in asset_ids if aid not in pool.asset_ids)

    def note_assets_changed(self, asset_ids):
        self.events.append(("changed", tuple(asset_ids)))

    def sync_asset_pool(self, pool_id):
        self.events.append(("sync", pool_id))


def _pool(projections=(), serving=None, asset_ids=()):
    return SimpleNamespace(
        projections=tuple(projections),
        serving=tuple(projections if serving is None else serving),
        asset_ids=list(asset_ids),
    )


def _registry(monkeypatch, library):
    registry = SimpleNamespace(
        lock=RLock(),
        save=lambda: library.events.append(("save",)),
        get=lambda name: library,
    )
    monkeypatch.setattr(manager, "registry", registry)
    monkeypatch.setattr(asset_library_api, "registry", registry)
    return registry


def _stream(asset_id, kind=TEXT, role=""):
    return ContentStream(
        asset_id,
        [ContentBlock(
            f"{asset_id}:0", kind=kind,
            text="prose" if kind == TEXT else "",
            media_key="blob" if kind != TEXT else "",
            metadata={"role": role} if role else {},
        )],
    )


class _TextProjection(VectorIndexer):
    def __init__(self, name, accepted=True):
        self.name = name
        self.accepted = accepted

    def accepts(self, asset):
        return self.accepted


class _MediaProjection(MultimodalIndexer):
    def __init__(self):
        pass

    def accepts(self, asset):
        raise AssertionError("a multimodal indexer cannot be a document primary")


@pytest.mark.parametrize("suffix, phase_function", [
    (".pdf", "two_phase_ingest"),
    (".html", "two_phase_structured"),
])
def test_g3_primary_is_first_accepting_serving_text_projection(
    monkeypatch, suffix, phase_function
):
    media = _MediaProjection()
    preparing = _TextProjection("preparing")
    rejected = _TextProjection("rejected", accepted=False)
    primary = _TextProjection("primary")
    later = _TextProjection("later")
    library = _Library({
        "first": _pool([preparing, media, rejected], serving=[media, rejected]),
        "second": _pool([primary, later]),
    })
    _registry(monkeypatch, library)
    monkeypatch.setattr(materialize, "_structured_two_phase_applies", lambda path: True)
    chosen = []

    def two_phase(indexer, path, asset_id, metadata, put_blob, source_id):
        chosen.append(indexer)
        return _stream(asset_id)

    monkeypatch.setattr(materialize, phase_function, two_phase)
    monkeypatch.setattr(
        extractor, "extract",
        lambda *args: pytest.fail("a serving text primary should use two phases"),
    )

    materialize.ingest(
        library, ["/w/report" + suffix], "", "", ["first", "second"], "content-1"
    )

    assert chosen == [primary]
    assert [("sync", "first"), ("sync", "second")] == [
        event for event in library.events if event[0] == "sync"
    ]


@pytest.mark.parametrize("suffix", [".pdf", ".html"])
def test_g3_without_serving_text_primary_uses_plain_extract(monkeypatch, suffix):
    media = _MediaProjection()
    preparing = _TextProjection("preparing")
    library = _Library({"p": _pool([media, preparing], serving=[media])})
    _registry(monkeypatch, library)
    extracted = []

    def extract(path, asset_id, put_blob):
        extracted.append(path)
        return _stream(asset_id)

    monkeypatch.setattr(extractor, "extract", extract)
    for name in ("two_phase_ingest", "two_phase_structured"):
        monkeypatch.setattr(
            materialize, name, lambda *args: pytest.fail("no eligible primary")
        )

    materialize.ingest(library, ["/w/report" + suffix], "", "", ["p"], "content-1")

    assert extracted == ["/w/report" + suffix]
    assert ("sync", "p") in library.events, "ordinary sync still feeds all sources"


def test_g5_api_defers_job_registration_then_syncs_captions_transcribes(monkeypatch):
    monkeypatch.setattr(config, "VIDEO_SUMMARY_BASE_URL", "http://summary:8000")
    monkeypatch.setattr(config, "ASR_ENABLED", True)
    library = _Library({"p": _pool()})
    _registry(monkeypatch, library)
    paths = ["/w/clip.mp4", "/w/voice.wav", "/w/picture.png", "/w/long.mp4"]
    roles = [
        (VIDEO, ROLE_SHORT_VIDEO), (AUDIO, ROLE_AUDIO),
        (IMAGE, ROLE_IMAGE), (VIDEO, ROLE_LONG_VIDEO),
    ]
    streams = {}

    def extract(path, asset_id, put_blob):
        library.events.append(("extract", path))
        kind, role = roles[paths.index(path)]
        streams[asset_id] = _stream(asset_id, kind, role)
        return streams[asset_id]

    monkeypatch.setattr(extractor, "extract", extract)
    monkeypatch.setattr(asset_library_api, "_resolve_uploads", lambda paths: paths)
    caption_predicate = captioning.needs_caption
    transcript_predicate = transcription.needs_transcript
    predicates = []

    def check(name, predicate, stream):
        assert streams[stream.asset_id] is stream, "inspect the extracted stream"
        predicates.append((name, stream.asset_id))
        return predicate(stream)

    monkeypatch.setattr(captioning, "needs_caption", lambda stream: check("caption", caption_predicate, stream))
    monkeypatch.setattr(transcription, "needs_transcript", lambda stream: check("transcript", transcript_predicate, stream))

    def job(name, asset_id):
        assert asset_id in library.assets
        assert ("sync", "p") in library.events, "first sync precedes either job"
        assert materialize.materialization_phase(asset_id) == "ready"
        library.events.append((name, asset_id))
        return captioning.STATUS_COMPLETED

    monkeypatch.setattr(captioning, "caption_asset", lambda lib, aid: job("caption", aid))
    monkeypatch.setattr(transcription, "transcribe_asset", lambda lib, aid: job("transcript", aid))
    tasks = BackgroundTasks()

    result = asyncio.run(asset_library_api.create_assets(
        library.name, AssetCreateRequest(file_paths=paths, asset_pool_ids=["p"]), tasks
    ))

    assert result.status == "materializing" and "warnings" not in result.model_dump()
    assert library.events == [] and predicates == [], "nothing inspects content inline"
    assert len(tasks.tasks) == 1 and tasks.tasks[0].func is materialize.ingest
    assert all(materialize.materialization_phase(aid) == "materializing" for aid in result.asset_ids)
    asyncio.run(tasks())

    assert len(predicates) == 2 * len(paths)
    assert [event[0] for event in library.events if event[0] in {"sync", "caption", "transcript"}] == [
        "sync", "caption", "sync", "transcript", "sync"
    ]
    assert ("caption", result.asset_ids[0]) in library.events
    assert ("transcript", result.asset_ids[1]) in library.events


@pytest.mark.parametrize("caption_enabled, asr_enabled, expected", [
    (False, False, []),
    (True, False, ["caption"]),
    (False, True, ["transcript"]),
])
def test_g5_disabled_services_do_not_register_jobs(
    monkeypatch, caption_enabled, asr_enabled, expected
):
    monkeypatch.setattr(config, "VIDEO_SUMMARY_BASE_URL", "http://summary:8000" if caption_enabled else "")
    monkeypatch.setattr(config, "ASR_ENABLED", asr_enabled)
    library = _Library()
    _registry(monkeypatch, library)
    monkeypatch.setattr(
        extractor, "extract",
        lambda path, aid, writer: _stream(
            aid, VIDEO if path.endswith(".mp4") else AUDIO,
            ROLE_SHORT_VIDEO if path.endswith(".mp4") else ROLE_AUDIO,
        ),
    )
    jobs = []
    monkeypatch.setattr(captioning, "caption_asset", lambda lib, aid: jobs.append("caption"))
    monkeypatch.setattr(transcription, "transcribe_asset", lambda lib, aid: jobs.append("transcript"))

    materialize.ingest(library, ["/w/clip.mp4", "/w/voice.wav"], "", "", [], "content-1")

    assert jobs == expected, "unassigned media can still be enriched if enabled"


def test_g5_reingest_syncs_existing_pools_and_transcribes_after_caption_failure(monkeypatch):
    monkeypatch.setattr(config, "VIDEO_SUMMARY_BASE_URL", "http://summary:8000")
    monkeypatch.setattr(config, "ASR_ENABLED", True)
    video_id = asset_id_for(file_origin("/w/clip.mp4"))
    library = _Library({"new": _pool(), "existing": _pool(asset_ids=[video_id])})
    library.assets[video_id] = SimpleNamespace(asset_id=video_id)
    _registry(monkeypatch, library)
    monkeypatch.setattr(
        extractor, "extract",
        lambda path, aid, writer: _stream(
            aid, VIDEO if path.endswith(".mp4") else AUDIO,
            ROLE_SHORT_VIDEO if path.endswith(".mp4") else ROLE_AUDIO,
        ),
    )

    def sync(pool_id):
        library.events.append(("sync", pool_id))
        if pool_id == "new":
            raise RuntimeError("one source is unavailable")

    def caption(lib, aid):
        library.events.append(("caption", aid))
        return captioning.STATUS_FAILED

    def transcribe(lib, aid):
        library.events.append(("transcript", aid))
        return captioning.STATUS_COMPLETED

    library.sync_asset_pool = sync
    monkeypatch.setattr(captioning, "caption_asset", caption)
    monkeypatch.setattr(transcription, "transcribe_asset", transcribe)

    materialize.ingest(
        library, ["/w/clip.mp4", "/w/voice.wav"], "", "", ["new"], "content-1"
    )

    assert ("changed", (video_id,)) in library.events
    assert [event[0:2] for event in library.events if event[0] in {"sync", "caption", "transcript"}] == [
        ("sync", "new"), ("sync", "existing"), ("caption", video_id),
        ("transcript", asset_id_for(file_origin("/w/voice.wav"))), ("sync", "new"),
    ]
    assert library.events[-1] == ("save",), "both failures and later success are persisted"


def test_g5_enrichment_failures_are_saved_and_other_jobs_and_pools_continue(monkeypatch):
    library = _Library({"bad": _pool(asset_ids=["ok"]), "good": _pool(asset_ids=["ok"])})
    registry = _registry(monkeypatch, library)

    class Guard:
        held = False

        def __enter__(self):
            self.held = True

        def __exit__(self, *args):
            self.held = False

    guard = Guard()
    registry.lock = guard
    registry.save = lambda: library.events.append(("save",))

    def job(lib, aid):
        assert not guard.held, "model work must not hold the registry lock"
        library.events.append(("job", aid))
        if aid == "crash":
            raise RuntimeError("unexpected job failure")
        return captioning.STATUS_FAILED if aid == "failed" else captioning.STATUS_COMPLETED

    def sync(pool_id):
        assert not guard.held, "sync must not hold the registry lock"
        library.events.append(("sync", pool_id))
        if pool_id == "bad":
            raise RuntimeError("sync failed")

    library.sync_asset_pool = sync
    materialize._enrich_and_save(library, ["failed", "crash", "ok"], job)

    assert library.events == [
        ("job", "failed"), ("job", "crash"), ("job", "ok"),
        ("sync", "bad"), ("sync", "good"), ("save",),
    ]
    library.events.clear()
    materialize._enrich_and_save(library, ["failed"], job)
    assert library.events == [("job", "failed"), ("save",)], "failure status is saved without re-embedding"


@pytest.mark.parametrize("job_module, job_name, kind, role", [
    (captioning, "caption_asset", VIDEO, ROLE_SHORT_VIDEO),
    (transcription, "transcribe_asset", AUDIO, ROLE_AUDIO),
])
def test_g5_real_job_failure_keeps_asset_lock_status_and_existing_blocks(
    monkeypatch, job_module, job_name, kind, role
):
    monkeypatch.setattr(config, "ASR_ENABLED", True)
    stream = _stream("job-asset", kind, role)
    original_blocks = [block.to_record() for block in stream.blocks]
    held = []

    @contextmanager
    def asset_lock(asset_id):
        held.append(asset_id)
        try:
            yield
        finally:
            held.remove(asset_id)

    @contextmanager
    def media_path(*args):
        assert held == ["job-asset"]
        yield "/w/media"

    def put_record(source, key, record):
        assert held == ["job-asset"], "failure record is written inside the asset lock"
        records.append(record)

    records = []
    asset = SimpleNamespace(
        asset_id="job-asset", content_source_id="", content_key="", content=stream,
        media_path=media_path, cached=stream,
    )
    library = _Library()
    library.assets[asset.asset_id] = asset
    library.content_store = SimpleNamespace(put_record=put_record)
    _registry(monkeypatch, library)
    monkeypatch.setattr(job_module, "asset_lock", asset_lock)
    monkeypatch.setattr(job_module, "note_derived", lambda *args: pytest.fail("failed jobs must not mark blocks stale"))

    def boom(path):
        raise RuntimeError("model unavailable")

    def job(lib, aid):
        if job_name == "caption_asset":
            client = SimpleNamespace(configured=True, caption=boom)
            return captioning.caption_asset(lib, aid, client=client)
        return transcription.transcribe_asset(lib, aid, transcriber=SimpleNamespace(transcribe=boom))

    materialize._enrich_and_save(library, [asset.asset_id], job)

    prefix = "caption" if job_name == "caption_asset" else "transcript"
    assert records[0]["metadata"][f"{prefix}_status"] == "failed"
    assert "model unavailable" in records[0]["metadata"][f"{prefix}_error"]
    assert records[0]["blocks"] == original_blocks
    assert held == [] and library.events[-1] == ("save",)


def test_g7_upload_and_ingest_media_reuses_staged_file_without_blob_copy(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "UPLOAD_DIR", str(tmp_path))
    library = _Library()
    _registry(monkeypatch, library)

    class Request:
        async def stream(self):
            yield b"picture-"
            yield b"bytes"

    uploaded = asyncio.run(asset_library_api.upload_file(library.name, "photos/a.png", Request()))
    materialize.ingest(library, [uploaded.file_path], "", "", [], "content-1")

    asset = library.assets[asset_id_for(file_origin(uploaded.file_path))]
    assert asset.content.blocks[0].media_key == file_uri(uploaded.file_path)
    assert asset.content.blocks[0].metadata["role"] == ROLE_IMAGE
    assert library.blobs == [], "upload already staged the bytes; extraction stores only the stream"
    assert uploaded.size == len(b"picture-bytes")
    assert sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*") if path.is_file()) == [
        "lib-1/photos/a.png"
    ], "neither a second media file nor a .part file is left behind"