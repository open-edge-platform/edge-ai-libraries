# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Describing a clip in the background, safely enough to do twice.

The caption job runs minutes after the asset was stored, against a service that
can time out, and a timed-out call gets retried. So every property worth
testing here is about what a second run does: it must replace the description
rather than append one, must not revert an ingest that landed in between, and
must not throw away the vector the clip already has when the description fails.

That last one is the reason embedding and captioning are separate jobs at all.
"""

import threading
from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace

import pytest

import config
from assetlib import Source
from assetlib.content import asset_key
from assetlib.pool import AssetPool, SourceSyncStatus
from assetlib.sources.binding import DEGRADE, PREPARING, SERVING
from core.content import (
    AUDIO,
    ROLE_L2_CAPTION,
    ROLE_L2_TRANSCRIPT,
    TEXT,
    ROLE_IMAGE,
    ROLE_LONG_VIDEO,
    ROLE_SHORT_VIDEO,
    VIDEO,
    ContentBlock,
    ContentStream,
)
from core.file_asset_library import FileAsset, describe_vector_source, file_origin
from core.indexer import MultimodalIndexer
from core.multimodal import captioning, registry
from core.multimodal.video_summary_client import VideoSummaryError
from databasehub.models import VectorCollection
from tests.test_sources.fakes import Library, add_source, ingest


class FakeClient:
    """A video summary service that answers however the test needs it to."""

    def __init__(self, text="A family walks along a beach.", error=None):
        self.configured = True
        self.text = text
        self.error = error
        self.calls = 0

    def caption(self, video_path, prompt=None):
        self.calls += 1
        if self.error:
            raise VideoSummaryError(self.error)
        return self.text


class FakeStore:
    """The content store, as a dict of records."""

    def __init__(self):
        self.records = {}
        self.writes = 0

    def put_record(self, source, key, record):
        self.records[key] = record
        self.writes += 1
        return key

    def get_record(self, source, key):
        return self.records[key]


class FakeLibrary:
    """Only the surface `caption_asset` touches."""

    def __init__(self, asset, stream):
        self.content_store = FakeStore()
        self.assets = {asset.asset_id: asset}
        self.asset_pools = {}
        self.changed = []
        self.changed_sources = []
        self._source = SimpleNamespace(source_id="object-1")
        self.content_store.records[asset.content_key] = stream.to_record()

    def content_source(self, source_id=None):
        return self._source

    def source_for(self, source_id):
        return self._source

    def note_assets_changed(self, asset_ids, source_ids=None):
        self.changed.extend(asset_ids)
        self.changed_sources.extend(sorted(source_ids or ()))


def pool_with(asset_id, **sources):
    """A pool holding `asset_id`, with one multimodal source per `name=roles`."""
    projections = []
    for source_id, roles in sources.items():
        projection = MultimodalIndexer.__new__(MultimodalIndexer)
        projection.configuration = {}
        projection._embedding = SimpleNamespace(supported_roles=frozenset(roles))
        projection.source = SimpleNamespace(source_id=source_id)
        projections.append(projection)
    return SimpleNamespace(
        asset_ids=[asset_id], projections=projections, unavailable_sources={},
        frozen_sources={},
    )


def _stream(asset_id="a1", role=ROLE_SHORT_VIDEO, blocks=None):
    media = ContentBlock(
        block_id=f"{asset_id}:0",
        kind=VIDEO,
        media_key="blobs/abc",
        caption="holiday clip",
        reading_order=0,
        metadata={"role": role},
    )
    return ContentStream(
        asset_id=asset_id,
        blocks=[media] + list(blocks or []),
        metadata={"file_name": "holiday.mp4", "asset_id": asset_id},
    )


def _setup(stream=None, **client_kwargs):
    stream = stream or _stream()
    asset = SimpleNamespace(
        asset_id=stream.asset_id,
        content=stream,
        cached=stream,
        content_source_id="object-1",
        content_key=asset_key(stream.asset_id),
        read_blob=lambda _key: b"\x00\x01",
        media_path=lambda _key, _suffix=".mp4": nullcontext("/tmp/x.mp4"),
    )
    library = FakeLibrary(asset, stream)
    return library, asset, FakeClient(**client_kwargs)


def _stored(library, asset):
    return ContentStream.from_record(library.content_store.records[asset.content_key])


# --- the happy path ------------------------------------------------------------


def test_a_description_becomes_a_text_block_pointing_back_at_the_clip(monkeypatch):
    library, asset, client = _setup()
    library.asset_pools = {
        "p": pool_with("a1", viclip={ROLE_SHORT_VIDEO}, gme={ROLE_L2_CAPTION})
    }

    status = captioning.caption_asset(library, "a1", client)

    stored = _stored(library, asset)
    caption = [b for b in stored.blocks if b.block_id == "a1:caption"][0]
    assert status == captioning.STATUS_COMPLETED
    assert caption.kind == TEXT
    assert caption.text == "A family walks along a beach."
    assert caption.metadata["role"] == ROLE_L2_CAPTION
    assert caption.metadata["source_block_id"] == "a1:0"
    assert library.changed == ["a1"], "the pools must re-sync for the new block"
    assert library.changed_sources == ["gme"], "only the source that takes captions"


def test_a_description_no_source_takes_is_stored_without_re_embedding_the_clip():
    """Marking the asset changed would re-encode the clip for the same vector."""
    library, asset, client = _setup()
    library.asset_pools = {"p": pool_with("a1", viclip={ROLE_SHORT_VIDEO})}

    status = captioning.caption_asset(library, "a1", client)

    assert status == captioning.STATUS_COMPLETED
    assert any(b.block_id == "a1:caption" for b in _stored(library, asset).blocks)
    assert library.changed == []


def test_a_source_that_could_not_be_loaded_is_re_opened_too():
    library, asset, client = _setup()
    pool = pool_with("a1")
    pool.unavailable_sources = {
        "gme": SimpleNamespace(
            profile={"supported_roles": [ROLE_L2_CAPTION]}, configuration={}
        )
    }
    library.asset_pools = {"p": pool}

    captioning.caption_asset(library, "a1", client)

    assert library.changed_sources == ["gme"]


@pytest.mark.parametrize("frozen_state", ["disabled", "deprecated"])
@pytest.mark.parametrize("role, kind", [(ROLE_L2_CAPTION, TEXT), (ROLE_L2_TRANSCRIPT, AUDIO)])
def test_frozen_derived_source_keeps_stale_and_catches_up_on_enable_or_rollback(
    monkeypatch, frozen_state, role, kind
):
    library = Library()
    source = add_source(library, "old", block_kinds=[kind], block_roles=[role])
    library._sources["old"] = replace(
        source, profile={"encoder_kind": "multimodal", "supported_roles": [role]}
    )
    pool = library.create_asset_pool("pool", "pool", [{"source_id": "old"}])
    ingest(library, "pool", "a")
    library.sync_asset_pool("pool")
    if frozen_state == "disabled":
        library.update_source("old", enabled=False)
    else:
        add_source(library, "new")
        library.set_asset_pool_sources(
            "pool", [{"source_id": "old"}, {"source_id": "new", "replaces": "old"}]
        )
        library.sync_asset_pool("pool")
        assert pool.source_statuses["old"].serving_state == DEGRADE
    assert "old" in pool.frozen_sources
    status = pool.source_statuses["old"]
    revision = pool.revision
    asset = library.assets["a"]
    block = ContentBlock("a:derived", TEXT, text="new derived content", metadata={"role": role})
    asset.cached.blocks.append(block)
    builds = list(library.builds)

    with monkeypatch.context() as check:
        check.setattr(library, "build_projection", lambda *args: pytest.fail("must not load frozen models"))
        check.setattr(library, "describe_source", lambda *args: pytest.fail("use the persisted profile"))
        assert captioning.note_derived(library, asset, [block])
        library.sync_asset_pool("pool")

    assert library.builds == builds
    assert pool.revision == revision + 1
    assert status.stale_asset_ids == ["a"]
    assert status.indexed_revision < pool.revision
    if frozen_state == "disabled":
        assert library.update_source("old", enabled=True) == ["pool"]
    else:
        library.set_asset_pool_sources(
            "pool", [{"source_id": "new"}, {"source_id": "old", "replaces": "new"}]
        )
    assert status.serving_state == PREPARING
    assert status.stale_asset_ids == ["a"]
    projection = next(p for p in pool.projections if p.source.source_id == "old")
    add = projection.add
    materialized = []

    def capture_add(assets):
        materialized.extend(b.block_id for a in assets for b in a.content.blocks)
        return add(assets)

    projection.add = capture_add
    library.sync_asset_pool("pool")

    assert projection.adds == [["a"]], "old backend records must not skip new derived content"
    assert "a:derived" in materialized
    assert status.stale_asset_ids == []
    assert status.indexed_revision == pool.revision
    assert status.serving_state == SERVING
    if frozen_state == "deprecated":
        assert pool.source_statuses["new"].serving_state == DEGRADE


@pytest.mark.parametrize("role, kind", [(ROLE_L2_CAPTION, TEXT), (ROLE_L2_TRANSCRIPT, AUDIO)])
def test_frozen_source_profile_respects_derived_role_and_kind_filters(role, kind):
    library, asset, _ = _setup()
    pool = pool_with("a1")

    def source(roles, configuration=None):
        return SimpleNamespace(profile={"supported_roles": roles}, configuration=configuration or {})

    pool.frozen_sources = {
        "taking": source([role], {"block_kinds": [kind], "block_roles": [role]}),
        "wrong-model-role": source([ROLE_SHORT_VIDEO]),
        "wrong-kind": source([role], {"block_kinds": [VIDEO]}),
        "wrong-role-filter": source([role], {"block_roles": [ROLE_IMAGE]}),
        "text-source": source([]),
    }
    library.asset_pools = {"p": pool, "other-asset": pool_with("other")}
    block = ContentBlock("derived", TEXT, text="new content", metadata={"role": role})

    assert captioning.sources_taking(library, asset, [block]) == {"taking"}


# --- running it twice ----------------------------------------------------------


def test_a_second_run_replaces_the_description_rather_than_adding_one(monkeypatch):
    """The block id is a domain coordinate, so a retry addresses the same block."""
    stream = _stream(blocks=[
        ContentBlock(
            block_id="a1:caption",
            kind=TEXT,
            text="an earlier, worse description",
            reading_order=1,
            metadata={"role": ROLE_L2_CAPTION, "source_block_id": "a1:0"},
        )
    ])
    library, asset, client = _setup(stream)

    captioning.caption_asset(library, "a1", client)

    stored = _stored(library, asset)
    captions = [b for b in stored.blocks if b.block_id == "a1:caption"]
    assert len(captions) == 1
    assert captions[0].text == "A family walks along a beach."


def test_an_already_completed_asset_is_not_sent_to_the_service_again(monkeypatch):
    library, asset, client = _setup()
    captioning.caption_asset(library, "a1", client)

    status = captioning.caption_asset(library, "a1", client)

    assert status == captioning.STATUS_COMPLETED
    assert client.calls == 1, "the second run cost nothing"


def test_the_stream_is_re_read_so_a_concurrent_ingest_is_not_reverted(monkeypatch):
    """The job holds a stream from minutes ago; the store holds the truth.

    Merging into the in-memory copy would silently drop whatever a re-ingest
    wrote while the vision model was running.
    """
    library, asset, client = _setup()
    # A re-ingest lands after the job was queued: same asset, new block.
    reingested = _stream()
    reingested.blocks.append(
        ContentBlock(block_id="a1:extra", kind=TEXT, text="added later", reading_order=1)
    )
    library.content_store.records[asset.content_key] = reingested.to_record()

    captioning.caption_asset(library, "a1", client)

    stored = _stored(library, asset)
    assert {b.block_id for b in stored.blocks} == {"a1:0", "a1:extra", "a1:caption"}


# --- failure keeps what already worked ----------------------------------------


def test_a_failed_description_is_recorded_without_touching_the_blocks(monkeypatch):
    """The clip was embedded at sync time; a caption failure must not undo it."""
    library, asset, client = _setup(error="service unavailable")

    status = captioning.caption_asset(library, "a1", client)

    stored = _stored(library, asset)
    assert status == captioning.STATUS_FAILED
    assert [b.block_id for b in stored.blocks] == ["a1:0"]
    assert stored.metadata["caption_status"] == captioning.STATUS_FAILED
    assert "service unavailable" in stored.metadata["caption_error"]
    assert library.changed == [], "nothing changed, so nothing to re-embed"


def test_a_later_success_clears_the_recorded_error(monkeypatch):
    library, asset, client = _setup(error="timed out")
    captioning.caption_asset(library, "a1", client)
    client.error = None

    captioning.caption_asset(library, "a1", client)

    stored = _stored(library, asset)
    assert stored.metadata["caption_status"] == captioning.STATUS_COMPLETED
    assert "caption_error" not in stored.metadata


# --- what is not captioned -----------------------------------------------------


def test_a_long_recording_is_never_sent_to_the_service():
    library, asset, client = _setup(_stream(role=ROLE_LONG_VIDEO))

    status = captioning.caption_asset(library, "a1", client)

    assert status == captioning.STATUS_SKIPPED
    assert client.calls == 0


def test_an_image_is_embedded_but_not_described():
    """A visual vector already carries what it looks like."""
    library, asset, client = _setup(_stream(role=ROLE_IMAGE))

    status = captioning.caption_asset(library, "a1", client)

    assert status == captioning.STATUS_SKIPPED
    assert client.calls == 0


def test_an_unconfigured_service_is_skipped_rather_than_failed():
    """Turning the video summary service on later should find the job pending, not terminally failed."""
    library, asset, client = _setup()
    client.configured = False

    status = captioning.caption_asset(library, "a1", client)

    assert status == captioning.STATUS_SKIPPED
    assert library.content_store.writes == 0


# --- reported state ------------------------------------------------------------


def test_the_reported_status_tells_pending_apart_from_skipped(monkeypatch):
    monkeypatch.setattr(config, "VIDEO_SUMMARY_BASE_URL", "http://summary:8000")
    pending = captioning.caption_status(_stream())
    skipped = captioning.caption_status(_stream(role=ROLE_LONG_VIDEO))

    assert pending["caption_status"] == captioning.STATUS_PENDING
    assert pending["role"] == ROLE_SHORT_VIDEO
    assert skipped["caption_status"] == captioning.STATUS_SKIPPED
    assert skipped["role"] == ROLE_LONG_VIDEO


def test_without_a_service_a_clip_reports_skipped_and_why(monkeypatch):
    """No job is queued, so "pending" would wait forever."""
    monkeypatch.setattr(config, "VIDEO_SUMMARY_BASE_URL", "")

    found = captioning.caption_status(_stream())

    assert found["caption_status"] == captioning.STATUS_SKIPPED
    assert found["error"] == captioning.NOT_CONFIGURED
    assert not captioning.needs_caption(_stream()), "and no job is queued"


def test_a_recorded_status_wins_over_the_current_configuration(monkeypatch):
    monkeypatch.setattr(config, "VIDEO_SUMMARY_BASE_URL", "")
    stream = _stream()
    stream.metadata["caption_status"] = captioning.STATUS_COMPLETED

    assert captioning.caption_status(stream)["caption_status"] == captioning.STATUS_COMPLETED


def test_two_threads_captioning_one_asset_write_one_description(monkeypatch):
    library, asset, client = _setup()

    threads = [
        threading.Thread(target=captioning.caption_asset, args=(library, "a1", client))
        for _ in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    stored = _stored(library, asset)
    assert len([b for b in stored.blocks if b.block_id == "a1:caption"]) == 1
    assert client.calls == 1, "the lock plus the completed check admits one caller"


# Real origins and frozen profiles matter here: an l2_caption on a video file
# must not reopen an audio/PDF/image source just because its model supports text.
def _scoped_source(*, caption=True, configuration=None, params=None):
    options = {
        "asset_types": ["mp4"],
        "embedding_backend": config.LOCAL_OPENVINO,
        "embedding_model": (
            "gme-Qwen2-VL-2B-Instruct-OV" if caption
            else "viclip-b-fp16"
        ),
    }
    if caption:
        options["block_roles"] = [ROLE_L2_CAPTION]
    profile = describe_vector_source(options)
    if params is not None:
        profile = {**profile, "params": {**profile["params"], **params}}
    return Source(
        source_id="caption-gme" if caption else "original-viclip",
        source_type="vector", database_id="vectors",
        name="captions" if caption else "original video",
        location=VectorCollection("video_captions" if caption else "video_originals", 4),
        configuration={**options, **(configuration or {})}, profile=profile,
    )


def _scoped_projection(source):
    projection = MultimodalIndexer.__new__(MultimodalIndexer)
    projection.source = source
    projection.configuration = {**source.configuration, **source.profile["params"]}
    projection._embedding = SimpleNamespace(supported_roles=frozenset(source.profile["supported_roles"]))
    return projection


@pytest.fixture
def scoped_caption_case():
    def make(lifecycle="active", *, filename="clip.mp4", configuration=None, params=None):
        stream = _stream()
        stream.metadata["file_name"] = filename
        asset = FileAsset(
            "a1", origin=file_origin(f"/not-read/{filename}"),
            content_source_id="object-1", content_key=asset_key("a1"),
        )
        asset.bind(lambda: pytest.fail("source selection must not load asset content"))
        library = FakeLibrary(asset, stream)
        source = _scoped_source(configuration=configuration, params=params)
        if lifecycle == "disabled":
            source = replace(source, enabled=False)
        projection = _scoped_projection(source)
        status = SourceSyncStatus(
            source.source_id, status="ready", indexed_revision=3,
            indexed_asset_ids=[asset.asset_id],
            serving_state=DEGRADE if lifecycle == "deprecated" else SERVING,
        )
        pool = AssetPool("videos", "videos", (projection,), [asset.asset_id], revision=3,
                         source_statuses={source.source_id: status})
        if lifecycle == "unavailable":
            pool.projections = ()
            pool.unavailable_sources[source.source_id] = source
            status.mark_failed("GME artifacts unavailable")
            pool.refresh_serving()
        elif lifecycle in {"disabled", "deprecated"}:
            pool.freeze(source.source_id, source)
        library.asset_pools = {"videos": pool}
        block = ContentBlock(
            "a1:caption", TEXT, text="A family walks along a beach.",
            metadata={"role": ROLE_L2_CAPTION, "source_block_id": "a1:0"},
        )
        return library, asset, pool, projection, block

    return make


@pytest.mark.parametrize("lifecycle", ["active", "disabled", "deprecated", "unavailable"])
@pytest.mark.parametrize("selector, filename, matches", [
    ("mp4", "clip.mp4", True), ("video/mp4", "clip.mp4", True),
    ("video", "clip.mp4", True), ("mp4", "clip.webm", False),
    ("video/mp4", "clip.webm", False), ("webm", "clip.mp4", False),
    ("video/webm", "clip.mp4", False), ("pdf", "clip.mp4", False),
    ("application/pdf", "clip.mp4", False), ("image", "clip.mp4", False),
    ("image/png", "clip.mp4", False), ("audio", "clip.mp4", False),
    ("audio/wav", "clip.mp4", False),
    ("mp4", "document.pdf", False), ("video/mp4", "picture.png", False),
    ("mp4", "recording.wav", False),
])
def test_caption_notifications_respect_exact_file_scope_for_every_source_lifecycle(
    scoped_caption_case, lifecycle, selector, filename, matches
):
    library, asset, _, projection, block = scoped_caption_case(
        lifecycle, filename=filename, params={"asset_types": [selector]},
    )
    expected = {projection.source.source_id} if matches else set()

    assert captioning.sources_taking(library, asset, [block]) == expected
    assert captioning.note_derived(library, asset, [block]) is matches
    assert library.changed == ([asset.asset_id] if matches else [])
    assert library.changed_sources == sorted(expected)
    assert asset.cached is None, "file acceptance must use provenance, not load the stream"


@pytest.mark.parametrize("lifecycle", ["active", "disabled", "deprecated", "unavailable"])
@pytest.mark.parametrize("key, allowed, excluded", [
    ("asset_types", ["video/mp4"], ["webm"]),
    ("block_kinds", [TEXT], [VIDEO]),
    ("block_roles", [ROLE_L2_CAPTION], [ROLE_SHORT_VIDEO]),
])
@pytest.mark.parametrize("frozen_accepts", [False, True])
def test_caption_notifications_use_frozen_params_over_raw_filters_and_current_defaults(
    scoped_caption_case, monkeypatch, lifecycle, key, allowed, excluded, frozen_accepts
):
    library, asset, _, projection, block = scoped_caption_case(
        lifecycle,
        configuration={key: excluded if frozen_accepts else allowed},
        params={key: allowed if frozen_accepts else excluded},
    )
    recorded_profile = projection.source.to_record()["profile"]
    monkeypatch.setattr(config, "EMBEDDING_BACKEND", "unrelated-current-backend")
    monkeypatch.setattr(config, "IMAGE_EMBEDDING_MODEL_ID", "unrelated-current-model")

    def forbidden(*args, **kwargs):
        pytest.fail("derived notifications must use persisted policy without resolving or loading models")

    monkeypatch.setattr(registry, "resolve", forbidden)
    monkeypatch.setattr(registry, "default_for", forbidden)
    monkeypatch.setattr(registry, "load", forbidden)
    expected = {projection.source.source_id} if frozen_accepts else set()

    assert captioning.sources_taking(library, asset, [block]) == expected
    assert captioning.note_derived(library, asset, [block]) is frozen_accepts
    assert library.changed_sources == sorted(expected)
    assert projection.source.to_record()["profile"] == recorded_profile


@pytest.mark.parametrize("lifecycle", ["active", "disabled", "deprecated", "unavailable"])
@pytest.mark.parametrize("key, excluded", [
    ("asset_types", ["webm"]), ("block_kinds", [VIDEO]),
    ("block_roles", [ROLE_SHORT_VIDEO]),
])
def test_empty_frozen_caption_filters_override_nonempty_raw_exclusions(
    scoped_caption_case, lifecycle, key, excluded
):
    library, asset, _, projection, block = scoped_caption_case(
        lifecycle, configuration={key: excluded}, params={key: []},
    )

    assert captioning.note_derived(library, asset, [block])
    assert library.changed == [asset.asset_id]
    assert library.changed_sources == [projection.source.source_id]


@pytest.mark.parametrize("filename", ["clip.mp4", "clip.webm"])
def test_active_caption_consumer_calls_projection_accepts_with_the_actual_asset(
    scoped_caption_case, monkeypatch, filename
):
    library, asset, _, projection, block = scoped_caption_case(filename=filename)
    accepts = projection.accepts
    calls = []

    def checked(candidate):
        calls.append(candidate)
        return accepts(candidate)

    monkeypatch.setattr(projection, "accepts", checked)

    taking = captioning.sources_taking(library, asset, [block])

    assert calls == [asset]
    assert taking == ({projection.source.source_id} if filename.endswith(".mp4") else set())
    assert asset.cached is None


def test_active_caption_consumer_honors_accepts_veto_even_when_file_and_block_match(
    scoped_caption_case, monkeypatch
):
    library, asset, _, projection, block = scoped_caption_case()
    calls = []

    def reject(candidate):
        calls.append(candidate)
        return False

    monkeypatch.setattr(projection, "accepts", reject)

    assert not captioning.note_derived(library, asset, [block])
    assert calls == [asset]
    assert library.changed == []


@pytest.mark.parametrize("lifecycle", ["active", "disabled", "deprecated", "unavailable"])
def test_caption_completion_reopens_only_gme_not_the_original_viclip_collection(
    scoped_caption_case, monkeypatch, lifecycle
):
    library, asset, pool, caption, _ = scoped_caption_case(
        lifecycle, configuration={"asset_types": ["audio"], "block_kinds": [VIDEO]},
        params={"asset_types": ["video/mp4"], "block_kinds": [TEXT]},
    )
    original = _scoped_projection(_scoped_source(caption=False))
    pool.projections += (original,)
    pool.source_statuses[original.source.source_id] = SourceSyncStatus(
        original.source.source_id, status="ready", indexed_revision=3, indexed_asset_ids=["a1"],
    )
    pool.refresh_serving()
    monkeypatch.setattr(asset, "media_path", lambda *a, **k: nullcontext("/not-read/clip.mp4"))
    record_change = library.note_assets_changed

    def note_assets_changed(asset_ids, source_ids=None):
        record_change(asset_ids, source_ids)
        assert pool.mark_assets_changed(asset_ids, source_ids)

    monkeypatch.setattr(library, "note_assets_changed", note_assets_changed)

    assert captioning.caption_asset(library, asset.asset_id, FakeClient()) == captioning.STATUS_COMPLETED

    assert original.source.source_id != caption.source.source_id
    assert original.collection.name != caption.collection.name
    assert original.source.profile["multimodal_model"]["name"] == "viclip-b"
    assert caption.source.profile["multimodal_model"]["name"] == "gme_qwen2vl"
    assert library.changed_sources == [caption.source.source_id]
    assert pool.source_statuses[caption.source.source_id].stale_asset_ids == ["a1"]
    assert pool.source_statuses[original.source.source_id].stale_asset_ids == []
    assert pool.revision == 4
    stored = _stored(library, asset)
    assert stored.metadata["caption_status"] == captioning.STATUS_COMPLETED
    assert [b.text for b in stored.blocks if b.metadata.get("role") == ROLE_L2_CAPTION] == [
        "A family walks along a beach."
    ]


def test_an_asset_outside_a_caption_sources_pool_never_reopens_it(scoped_caption_case):
    library, asset, pool, _, block = scoped_caption_case()
    pool.asset_ids = ["another-asset"]

    assert captioning.sources_taking(library, asset, [block]) == set()
    assert not captioning.note_derived(library, asset, [block])
    assert library.changed == []
