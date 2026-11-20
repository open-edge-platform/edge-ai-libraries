# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Will this media asset be embedded? Worked out from what is configured now.

Three situations look the same from outside -- the asset is never found -- and
need telling apart because the remedies differ: there is no model for this kind
of media at all, there is a model but no source uses it, or a source does and is
still working or has broken. None of this is written on the asset. These tests
hold the asset fixed and change only the configuration, which is the point.
"""

from dataclasses import replace
from types import SimpleNamespace

import pytest

import config
from assetlib import Source
from assetlib.pool import AssetPool, SourceSyncStatus
from core.content import (
    AUDIO,
    IMAGE,
    ROLE_AUDIO,
    ROLE_IMAGE,
    ROLE_L2_CAPTION,
    ROLE_L2_TRANSCRIPT,
    ROLE_LONG_VIDEO,
    ROLE_SHORT_VIDEO,
    TEXT,
    VIDEO,
    ContentBlock,
    ContentStream,
)
from core.file_asset_library import FileAsset, describe_vector_source, file_origin
from core.indexer import MultimodalIndexer, VectorIndexer
from core.multimodal import coverage
from databasehub.models import VectorCollection


class _Model:
    def __init__(self, roles):
        self.supported_roles = frozenset(roles)


def _projection(roles=(ROLE_SHORT_VIDEO,), source_id="video-src", block_kinds=None):
    projection = MultimodalIndexer.__new__(MultimodalIndexer)
    projection.configuration = {"block_kinds": block_kinds} if block_kinds else {}
    projection._embedding = _Model(roles)
    projection.source = SimpleNamespace(source_id=source_id)
    return projection


def covered_pool(asset_id, ready=False, roles=(ROLE_SHORT_VIDEO,), **status):
    """A pool holding `asset_id` with one multimodal source over `roles`."""
    held = [asset_id] if ready else []
    return SimpleNamespace(
        asset_ids=[asset_id],
        projections=[_projection(roles)],
        unavailable_sources={},
        source_statuses={
            "video-src": SimpleNamespace(
                status=status.get("state", "ready"),
                error=status.get("error", ""),
                indexed_asset_ids=held,
                stale_asset_ids=status.get("stale", []),
            )
        },
    )


def _stream(role=ROLE_SHORT_VIDEO, asset_id="a1"):
    return ContentStream(
        asset_id=asset_id,
        blocks=[ContentBlock(f"{asset_id}:0", VIDEO, metadata={"role": role})],
    )


def _library(*pools):
    return SimpleNamespace(asset_pools={str(i): pool for i, pool in enumerate(pools)})


def _coverage(library, role=ROLE_SHORT_VIDEO):
    return coverage.embedding_coverage(library, "a1", _stream(role))


def test_a_document_is_not_media_and_has_no_coverage_to_report():
    stream = ContentStream(asset_id="a1", blocks=[ContentBlock("a1:0", text="hi")])

    result = coverage.embedding_coverage(_library(), "a1", stream)

    assert result.status == coverage.NOT_APPLICABLE


def test_an_asset_in_no_pool_is_unassigned():
    assert _coverage(_library()).status == coverage.UNASSIGNED


def test_a_long_recording_has_no_source_and_no_model_either():
    result = _coverage(_library(covered_pool("a1")), ROLE_LONG_VIDEO)

    assert result.status == coverage.NO_SOURCE
    assert "no embedding model supports" in result.reason


def test_an_image_has_a_model_but_nobody_configured_a_source_with_it():
    """The reason names the fix, which differs from the long-recording case."""
    result = _coverage(_library(covered_pool("a1")), ROLE_IMAGE)

    assert result.status == coverage.NO_SOURCE
    assert "add a vector source" in result.reason


def test_the_same_long_recording_becomes_covered_once_a_capable_source_exists():
    """The asset is untouched; only the configuration moved."""
    before = _coverage(_library(covered_pool("a1")), ROLE_LONG_VIDEO)
    after = _coverage(
        _library(covered_pool("a1", ready=True, roles=(ROLE_LONG_VIDEO,))),
        ROLE_LONG_VIDEO,
    )

    assert before.status == coverage.NO_SOURCE
    assert after.status == coverage.READY


def test_a_covered_clip_the_source_has_not_written_yet_is_pending():
    assert _coverage(_library(covered_pool("a1"))).status == coverage.PENDING


def test_a_covered_clip_the_source_holds_is_ready():
    assert _coverage(_library(covered_pool("a1", ready=True))).status == coverage.READY


def test_a_clip_whose_content_changed_since_it_was_written_is_pending_again():
    pool = covered_pool("a1", ready=True, stale=["a1"])

    assert _coverage(_library(pool)).status == coverage.PENDING


def test_a_failed_source_reports_its_error():
    pool = covered_pool("a1", state="failed", error="Milvus unreachable")

    result = _coverage(_library(pool))

    assert result.status == coverage.FAILED
    assert result.reason == "Milvus unreachable"


def test_with_several_covering_sources_the_least_settled_one_is_reported():
    ready = covered_pool("a1", ready=True)
    failed = covered_pool("a1", state="failed", error="boom")

    assert _coverage(_library(ready, failed)).status == coverage.FAILED


def test_a_source_that_failed_to_load_is_reported_as_failed_not_as_missing():
    """Saying "add a source" about a source that is already there misleads."""
    source = SimpleNamespace(
        name="video-viclip-embedding",
        configuration={"block_kinds": ["video"]},
        profile={"supported_roles": ["short_video", "l1_segment"]},
    )
    pool = SimpleNamespace(
        asset_ids=["a1"],
        projections=[],
        unavailable_sources={"s1": source},
        source_statuses={"s1": SimpleNamespace(error="model directory not found")},
    )

    result = _coverage(_library(pool))

    assert result.status == coverage.FAILED
    assert "video-viclip-embedding" in result.reason
    assert "model directory not found" in result.reason


def test_a_failed_source_for_another_kind_of_media_does_not_explain_this_one():
    source = SimpleNamespace(
        name="image-src",
        configuration={"block_kinds": ["image"]},
        profile={"supported_roles": ["image", "doc_image"]},
    )
    pool = SimpleNamespace(
        asset_ids=["a1"], projections=[], unavailable_sources={"s1": source},
        source_statuses={"s1": SimpleNamespace(error="boom")},
    )

    assert _coverage(_library(pool)).status == coverage.NO_SOURCE


class _FusedModel:
    def get_fused_embeddings(self, texts, images):
        raise AssertionError("coverage must not run inference")


def _image_case(*, text=False, fused=True, configuration=None, state="SERVING"):
    stream = ContentStream("a1", [ContentBlock(
        "a1:0", IMAGE, media_key="file:///not-read/picture.png",
        metadata={"role": ROLE_IMAGE},
    )])
    asset = FileAsset("a1", origin=file_origin("/not-read/picture.png"))
    asset.bind(lambda: pytest.fail("coverage must not reload content"))
    if text:
        projection = VectorIndexer.__new__(VectorIndexer)
        projection._embedding_model = _FusedModel() if fused else object()
        projection.configuration = {}
        projection.source = SimpleNamespace(source_id="image-src", enabled=True)
    else:
        projection = _projection((ROLE_IMAGE,), source_id="image-src")
    projection.configuration.update(configuration or {})
    status = SourceSyncStatus(
        "image-src", status="ready", indexed_asset_ids=["a1"], serving_state=state,
    )
    pool = AssetPool("p", "pictures", (projection,), ["a1"], source_statuses={"image-src": status})
    library = SimpleNamespace(assets={"a1": asset}, asset_pools={"p": pool})
    return library, pool, projection, stream


@pytest.mark.parametrize("text", [False, True], ids=["multimodal", "text-fused"])
def test_standalone_image_coverage_supports_both_legal_paths(text):
    library, _, _, stream = _image_case(text=text)

    assert coverage.embedding_coverage(library, "a1", stream).status == coverage.READY


def test_text_only_image_caption_is_not_fused_media_coverage():
    library, _, _, stream = _image_case(text=True, fused=False)
    stream.blocks[0].caption = "a searchable caption is not pixel coverage"

    assert coverage.embedding_coverage(library, "a1", stream).status == coverage.NO_SOURCE


@pytest.mark.parametrize("text", [False, True])
@pytest.mark.parametrize("configuration", [
    {"asset_types": ["pdf"]}, {"block_kinds": ["video"]},
    {"block_roles": ["doc_image"]},
])
def test_asset_and_block_filters_exclude_both_image_paths(text, configuration):
    library, _, _, stream = _image_case(text=text, configuration=configuration)

    assert coverage.embedding_coverage(library, "a1", stream).status == coverage.NO_SOURCE


@pytest.mark.parametrize("asset_type", ["png", "image", "image/png"])
def test_fused_image_coverage_accepts_extension_mime_and_family(asset_type):
    library, _, _, stream = _image_case(text=True, configuration={"asset_types": [asset_type]})

    assert coverage.embedding_coverage(library, "a1", stream).status == coverage.READY


@pytest.mark.parametrize("text", [False, True])
@pytest.mark.parametrize("state", ["PREPARING", "DEGRADE", "DISABLED"])
def test_non_serving_image_sources_never_report_ready(text, state):
    library, pool, projection, stream = _image_case(text=text, state=state)
    if state == "DISABLED":
        projection.source.enabled = False

    result = coverage.embedding_coverage(library, "a1", stream)

    assert result.status == (coverage.PENDING if state == "PREPARING" else coverage.NO_SOURCE)


def test_a_projection_not_published_as_serving_cannot_report_ready():
    library, pool, _, stream = _image_case(text=True)
    pool.serving = ()

    assert coverage.embedding_coverage(library, "a1", stream).status == coverage.PENDING


@pytest.mark.parametrize("text", [False, True])
@pytest.mark.parametrize("status, stale, expected", [
    ("ready", ["a1"], coverage.PENDING),
    ("failed", [], coverage.FAILED),
])
def test_fused_and_mm_image_coverage_keep_sync_failure_and_stale_semantics(text, status, stale, expected):
    library, pool, _, stream = _image_case(text=text)
    sync = pool.source_statuses["image-src"]
    sync.status, sync.stale_asset_ids, sync.error = status, stale, "write failed"

    result = coverage.embedding_coverage(library, "a1", stream)

    assert result.status == expected
    if expected == coverage.FAILED:
        assert result.reason == "write failed"


def _unavailable(pool, *, text=False, configuration=None, enabled=True, state="SERVING"):
    source = SimpleNamespace(
        source_id="broken", name="broken-image", enabled=enabled,
        configuration=configuration or {},
        profile={"encoder_kind": "text", "fused": True} if text else {
            "encoder_kind": "multimodal", "supported_roles": [ROLE_IMAGE],
        },
    )
    pool.unavailable_sources[source.source_id] = source
    pool.source_statuses[source.source_id] = SourceSyncStatus(
        source.source_id, status="failed", error="model unavailable", serving_state=state,
    )
    return source


@pytest.mark.parametrize("text", [False, True])
@pytest.mark.parametrize("ready_text", [False, True])
def test_unavailable_image_source_counts_as_failure_even_beside_a_ready_source(text, ready_text):
    library, pool, _, stream = _image_case(text=ready_text)
    _unavailable(pool, text=text)

    result = coverage.embedding_coverage(library, "a1", stream)

    assert result.status == coverage.FAILED
    assert "model unavailable" in result.reason


@pytest.mark.parametrize("options", [
    {"enabled": False}, {"state": "DEGRADE"},
    {"configuration": {"asset_types": ["pdf"]}},
    {"configuration": {"block_kinds": ["video"]}},
    {"configuration": {"block_roles": ["doc_image"]}},
])
def test_irrelevant_unavailable_source_does_not_mask_ready_coverage(options):
    library, pool, _, stream = _image_case(text=True)
    _unavailable(pool, **options)

    assert coverage.embedding_coverage(library, "a1", stream).status == coverage.READY


def test_frozen_sources_do_not_supply_media_coverage():
    library, pool, projection, stream = _image_case(text=True)
    pool.freeze("image-src", projection.source)

    assert coverage.embedding_coverage(library, "a1", stream).status == coverage.NO_SOURCE


@pytest.mark.parametrize("kind, role", [
    (VIDEO, ROLE_SHORT_VIDEO), (VIDEO, ROLE_LONG_VIDEO), (AUDIO, ROLE_AUDIO),
])
def test_text_fused_image_support_does_not_claim_video_or_audio_coverage(kind, role):
    library, _, _, _ = _image_case(text=True)
    stream = ContentStream("a1", [ContentBlock(
        "a1:0", kind, media_key="file:///not-read/media", metadata={"role": role},
    )], metadata={"transcript_status": "completed"})

    assert coverage.embedding_coverage(library, "a1", stream).status == coverage.NO_SOURCE


@pytest.mark.parametrize("transcript_status, expected", [
    ("pending", coverage.PENDING), ("failed", coverage.FAILED),
    ("skipped", coverage.NO_SOURCE), ("completed", coverage.READY),
])
def test_audio_keeps_transcript_dependency_even_beside_a_text_fused_source(transcript_status, expected):
    library, pool, _, _ = _image_case(text=True)
    transcript = _projection((ROLE_L2_TRANSCRIPT,), source_id="transcript-src", block_kinds=["audio"])
    pool.projections += (transcript,)
    pool.source_statuses["transcript-src"] = SourceSyncStatus(
        "transcript-src", status="ready", indexed_asset_ids=["a1"],
    )
    pool.refresh_serving()
    stream = ContentStream("a1", [ContentBlock(
        "a1:0", AUDIO, media_key="file:///not-read/voice.wav", metadata={"role": ROLE_AUDIO},
    )], metadata={"transcript_status": transcript_status, "transcript_error": "ASR failed"})

    assert coverage.embedding_coverage(library, "a1", stream).status == expected


# Video and its caption are independent consumers, with independent vector spaces.
# These fakes skip constructors/inference, not source policy or file acceptance.
def _video_source(*, caption, configuration=None, params=None):
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
        name="video captions" if caption else "original clips",
        source_type="vector", database_id="vectors",
        location=VectorCollection("video_captions" if caption else "video_originals", 4),
        configuration={**options, **(configuration or {})}, profile=profile,
    )


def _policy_projection(source):
    projection = MultimodalIndexer.__new__(MultimodalIndexer)
    projection.source = source
    # Mirror the runtime's already-resolved configuration without resolving it
    # from today's defaults or constructing a model.
    projection.configuration = {**source.configuration, **source.profile["params"]}
    projection._embedding = _Model(source.profile["supported_roles"])
    return projection


@pytest.fixture
def video_coverage_case(monkeypatch):
    monkeypatch.setattr(config, "VIDEO_SUMMARY_BASE_URL", "http://summary.invalid")

    def make(*, caption_status=None, text=None, indexed=True, original=False,
             source=None, filename="clip.mp4"):
        stream = _stream()
        stream.blocks[0].media_key = f"file:///not-read/{filename}"
        stream.blocks[0].caption = "A file-name display caption is not derived text."
        if caption_status is not None:
            stream.metadata["caption_status"] = caption_status
        if caption_status == "failed":
            stream.metadata["caption_error"] = "summary service timed out"
        if text is not None:
            stream.blocks.append(ContentBlock(
                "a1:caption", TEXT, text=text,
                metadata={"role": ROLE_L2_CAPTION, "source_block_id": "a1:0"},
            ))
        asset = FileAsset("a1", origin=file_origin(f"/not-read/{filename}"))
        asset.bind(lambda: pytest.fail("coverage must not load the asset's content"))
        projections = [_policy_projection(source or _video_source(caption=True))]
        if original:
            projections.insert(0, _policy_projection(_video_source(caption=False)))
        statuses = {
            p.source.source_id: SourceSyncStatus(
                p.source.source_id, status="ready", indexed_revision=7,
                indexed_asset_ids=["a1"] if indexed or (original and p is projections[0]) else [],
            ) for p in projections
        }
        pool = AssetPool("video-pool", "videos", projections, ["a1"], revision=7,
                         source_statuses=statuses)
        library = SimpleNamespace(assets={"a1": asset}, asset_pools={"video-pool": pool})
        return library, pool, projections[-1], stream

    return make


def test_video_original_and_caption_defaults_select_distinct_models_and_collections(monkeypatch):
    for category, model in (
        ("VIDEO", "viclip-b-fp16"),
        ("IMAGE", "gme-Qwen2-VL-2B-Instruct-OV"),
    ):
        monkeypatch.setattr(config, f"{category}_EMBEDDING_MODEL_ID", model)
        monkeypatch.setattr(config, f"{category}_EMBEDDING_BACKEND", config.LOCAL_OPENVINO)
    original = _video_source(caption=False)
    caption = _video_source(caption=True)
    # No explicit model is needed for either representation at source creation.
    original_profile = describe_vector_source({"asset_types": ["video"]})
    caption_profile = describe_vector_source({
        "asset_types": ["video"], "block_roles": [ROLE_L2_CAPTION],
    })

    assert original_profile["multimodal_model"]["name"] == "viclip-b"
    assert caption_profile["multimodal_model"]["name"] == "gme_qwen2vl"
    assert original_profile["params"]["block_kinds"] == [VIDEO]
    assert ROLE_L2_CAPTION not in original_profile["params"]["block_roles"]
    assert caption_profile["params"]["block_kinds"] == [TEXT]
    assert caption_profile["params"]["block_roles"] == [ROLE_L2_CAPTION]
    assert original_profile["profile_hash"] != caption_profile["profile_hash"]
    assert original.source_id != caption.source_id
    assert original.location.name != caption.location.name
    assert _policy_projection(original).covers(_stream().blocks[0])
    assert not _policy_projection(caption).covers(_stream().blocks[0])
    derived = ContentBlock("a1:caption", TEXT, text="A real caption.", metadata={"role": ROLE_L2_CAPTION})
    assert _policy_projection(caption).covers(derived)
    assert not _policy_projection(original).covers(derived)


@pytest.mark.parametrize("caption_status", [None, "pending", "completed", "skipped", "failed"])
@pytest.mark.parametrize("text", [None, "", " \n\t", "A family walks along a beach."])
@pytest.mark.parametrize("indexed", [False, True], ids=["not-indexed", "indexed"])
def test_caption_only_coverage_requires_real_text_and_indexing(
    video_coverage_case, caption_status, text, indexed
):
    library, pool, projection, stream = video_coverage_case(
        caption_status=caption_status, text=text, indexed=indexed,
    )

    result = coverage.embedding_coverage(library, "a1", stream)

    expected = (
        (coverage.READY if indexed else coverage.PENDING) if text and text.strip()
        else coverage.FAILED if caption_status == "failed"
        else coverage.NO_SOURCE if caption_status == "skipped"
        else coverage.PENDING
    )
    assert pool.source_statuses[projection.source.source_id].status == "ready"
    assert result.status == expected
    if text and text.strip():
        assert "captioning failed" not in result.reason
    elif caption_status == "failed":
        assert "captioning failed" in result.reason
        assert "summary service timed out" in result.reason
    elif caption_status == "skipped":
        assert "skipped" in result.reason
    elif not text or not text.strip():
        assert "waiting for its caption" in result.reason


def test_caption_only_coverage_without_a_service_is_no_source(video_coverage_case, monkeypatch):
    library, _, _, stream = video_coverage_case()
    monkeypatch.setattr(config, "VIDEO_SUMMARY_BASE_URL", "")

    result = coverage.embedding_coverage(library, "a1", stream)

    assert result.status == coverage.NO_SOURCE
    assert "ENGINE_VIDEO_SUMMARY_BASE_URL" in result.reason


@pytest.mark.parametrize('caption_status', ['pending', 'skipped', 'failed'])
def test_missing_caption_does_not_hide_a_failed_indexing_source(video_coverage_case, caption_status):
    library, pool, projection, stream = video_coverage_case(caption_status=caption_status)
    pool.source_statuses[projection.source.source_id].mark_failed('caption collection unavailable')

    found = coverage.embedding_coverage(library, 'a1', stream)

    assert found.status == coverage.FAILED
    assert found.reason == 'caption collection unavailable'


@pytest.mark.parametrize('role', ['l2_caption', 'l2_transcript'])
def test_existing_external_text_does_not_require_automatic_enrichment(video_coverage_case, monkeypatch, role):
    source = _video_source(caption=True)
    source.profile['params']['block_roles'] = [role]
    library, _, _, stream = video_coverage_case(source=source)
    stream.metadata.update(caption_status='skipped', transcript_status='skipped')
    stream.blocks.append(ContentBlock('external', TEXT, text='Externally supplied text.', metadata={'role': role}))
    monkeypatch.setattr(config, 'VIDEO_SUMMARY_BASE_URL', '')
    monkeypatch.setattr(config, 'ASR_ENABLED', False)

    assert coverage.embedding_coverage(library, 'a1', stream).status == coverage.READY


@pytest.mark.parametrize("text", [None, "", " \n\t"])
def test_ready_pool_after_materializing_zero_caption_nodes_is_still_pending(video_coverage_case, text):
    library, pool, projection, stream = video_coverage_case(caption_status="completed", text=text)
    materialized_asset = FileAsset("a1", origin=library.assets["a1"].origin, cached=stream)

    assert list(projection.iter_node_items(materialized_asset)) == []
    # Pool bookkeeping can acknowledge the asset even though no block made a
    # node. That acknowledgement is not proof of searchable caption content.
    pool.source_statuses[projection.source.source_id].mark_ready(pool.revision, ["a1"])

    result = coverage.embedding_coverage(library, "a1", stream)

    assert result.status == coverage.PENDING
    assert "waiting for its caption" in result.reason


@pytest.mark.parametrize("failure", ["stale", "preparing", "unpublished", "write-failed"])
def test_real_indexed_caption_still_obeys_its_source_state(video_coverage_case, failure):
    library, pool, projection, stream = video_coverage_case(
        caption_status="completed", text="A real caption.",
    )
    status = pool.source_statuses[projection.source.source_id]
    if failure == "stale":
        status.stale_asset_ids = ["a1"]
    elif failure == "preparing":
        status.serving_state = "PREPARING"
        pool.refresh_serving()
    elif failure == "unpublished":
        pool.serving = ()
    else:
        status.mark_failed("caption collection write failed")

    result = coverage.embedding_coverage(library, "a1", stream)

    assert result.status == (coverage.FAILED if failure == "write-failed" else coverage.PENDING)
    if failure == "write-failed":
        assert result.reason == "caption collection write failed"


@pytest.mark.parametrize("separate_pools", [False, True], ids=["same-pool", "separate-pools"])
@pytest.mark.parametrize("original_state, caption_state, expected", [
    ("ready", "pending", coverage.PENDING),
    ("ready", "skipped", coverage.NO_SOURCE),
    ("ready", "failed", coverage.FAILED),
    ("failed", "pending", coverage.FAILED),
    ("pending", "completed", coverage.PENDING),
    ("ready", "completed", coverage.READY),
])
def test_original_and_caption_sources_report_the_least_settled_consumer(
    video_coverage_case, separate_pools, original_state, caption_state, expected
):
    library, pool, caption, stream = video_coverage_case(
        caption_status=caption_state, text="A real caption." if caption_state == "completed" else None,
        original=True,
    )
    original = pool.projections[0]
    status = pool.source_statuses[original.source.source_id]
    if original_state == "failed":
        status.mark_failed("ViCLIP collection unavailable")
    elif original_state == "pending":
        status.indexed_asset_ids = []
    if separate_pools:
        pool.projections = (original,)
        pool.refresh_serving()
        library.asset_pools["captions"] = AssetPool(
            "captions", "captions", (caption,), ["a1"],
            source_statuses={caption.source.source_id: pool.source_statuses.pop(caption.source.source_id)},
        )

    result = coverage.embedding_coverage(library, "a1", stream)

    assert result.status == expected
    if original_state == "failed":
        assert result.reason == "ViCLIP collection unavailable"


@pytest.mark.parametrize("caption_status", [None, "pending", "skipped", "failed", "completed"])
@pytest.mark.parametrize("explicit_empty_roles", [False, True], ids=["default-roles", "empty-roles"])
def test_viclip_without_an_explicit_caption_role_never_waits_for_captioning(
    video_coverage_case, caption_status, explicit_empty_roles
):
    params = {"block_roles": []} if explicit_empty_roles else None
    source = _video_source(caption=False, params=params)
    library, _, _, stream = video_coverage_case(
        caption_status=caption_status, source=source,
        text="Existing caption text." if caption_status == "completed" else None,
    )

    assert coverage.embedding_coverage(library, "a1", stream).status == coverage.READY


@pytest.mark.parametrize("selector, filename, matches", [
    ("mp4", "clip.mp4", True), ("video/mp4", "clip.mp4", True),
    ("video", "clip.mp4", True), ("mp4", "clip.webm", False),
    ("video/mp4", "clip.webm", False), ("webm", "clip.mp4", False),
    ("video/webm", "clip.mp4", False), ("pdf", "clip.mp4", False),
    ("image", "clip.mp4", False), ("audio", "clip.mp4", False),
    ("mp4", "document.pdf", False), ("video/mp4", "picture.png", False),
    ("mp4", "recording.wav", False),
])
@pytest.mark.parametrize("unavailable", [False, True], ids=["active", "unavailable"])
def test_caption_coverage_uses_frozen_extension_and_mime_scope(
    video_coverage_case, monkeypatch, selector, filename, matches, unavailable
):
    source = _video_source(
        caption=True, configuration={"asset_types": ["audio" if matches else "video"]},
        params={"asset_types": [selector]},
    )
    library, pool, projection, stream = video_coverage_case(
        source=source, filename=filename, caption_status="completed", text="A real caption.",
    )
    if unavailable:
        pool.projections = ()
        pool.unavailable_sources[source.source_id] = source
        pool.source_statuses[source.source_id].mark_failed("frozen GME model directory is missing")
        pool.refresh_serving()
    monkeypatch.setattr(coverage.registry, "resolve", lambda *a, **k: pytest.fail("do not re-resolve profiles"))

    result = coverage.embedding_coverage(library, "a1", stream)

    expected = (coverage.FAILED if unavailable else coverage.READY) if matches else coverage.NO_SOURCE
    assert result.status == expected
    if unavailable and matches:
        assert source.name in result.reason
        assert "frozen GME model directory is missing" in result.reason
    assert projection.configuration["asset_types"] == [selector]


@pytest.mark.parametrize("key, allowed, excluded", [
    ("asset_types", ["mp4"], ["webm"]),
    ("block_kinds", [TEXT], [VIDEO]),
    ("block_roles", [ROLE_L2_CAPTION], [ROLE_SHORT_VIDEO]),
])
@pytest.mark.parametrize("frozen_accepts", [False, True])
def test_unavailable_caption_source_uses_frozen_filters_not_raw_options_or_defaults(
    video_coverage_case, monkeypatch, key, allowed, excluded, frozen_accepts
):
    source = _video_source(
        caption=True,
        configuration={key: excluded if frozen_accepts else allowed},
        params={key: allowed if frozen_accepts else excluded},
    )
    library, pool, projection, stream = video_coverage_case(source=source, original=True)
    pool.projections = tuple(p for p in pool.projections if p is not projection)
    pool.unavailable_sources[source.source_id] = source
    pool.source_statuses[source.source_id].mark_failed("persisted caption model cannot load")
    pool.refresh_serving()
    monkeypatch.setattr(config, "EMBEDDING_BACKEND", "unrelated-todays-default")
    monkeypatch.setattr(config, "IMAGE_EMBEDDING_MODEL_ID", "unrelated-todays-model")
    monkeypatch.setattr(coverage.registry, "resolve", lambda *a, **k: pytest.fail("use frozen options"))

    result = coverage.embedding_coverage(library, "a1", stream)

    assert result.status == (coverage.FAILED if frozen_accepts else coverage.READY)
    if frozen_accepts:
        assert source.name in result.reason
        assert "persisted caption model cannot load" in result.reason


@pytest.mark.parametrize("key, excluded", [
    ("asset_types", ["webm"]), ("block_kinds", [VIDEO]),
    ("block_roles", [ROLE_SHORT_VIDEO]),
])
def test_unavailable_caption_source_keeps_explicit_empty_frozen_filters(
    video_coverage_case, key, excluded
):
    source = _video_source(caption=True, configuration={key: excluded}, params={key: []})
    source = Source.from_record(source.to_record())
    library, pool, _, stream = video_coverage_case(
        source=source, caption_status="completed", text="A real caption.",
    )
    pool.projections = ()
    pool.unavailable_sources[source.source_id] = source
    pool.source_statuses[source.source_id].mark_failed("persisted caption model cannot load")
    pool.refresh_serving()

    result = coverage.embedding_coverage(library, "a1", stream)

    assert result.status == coverage.FAILED
    assert "persisted caption model cannot load" in result.reason


@pytest.mark.parametrize("state", ["disabled", "deprecated", "frozen"])
def test_frozen_caption_source_does_not_make_original_video_wait(video_coverage_case, state):
    library, pool, projection, stream = video_coverage_case(original=True)
    if state == "disabled":
        projection.source = replace(projection.source, enabled=False)
    elif state == "deprecated":
        pool.source_statuses[projection.source.source_id].serving_state = "DEGRADE"
    else:
        pool.freeze(projection.source.source_id, projection.source)
    pool.refresh_serving()

    assert coverage.embedding_coverage(library, "a1", stream).status == coverage.READY
