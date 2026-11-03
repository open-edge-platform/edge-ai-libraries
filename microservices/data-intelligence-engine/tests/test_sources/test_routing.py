# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Per-role routing: the filters a source takes blocks by, and the pool report."""

from dataclasses import replace

from assetlib import Source
from core.content import AUDIO, TEXT, VIDEO, ContentBlock
from core.file_asset_library import describe_vector_source
from core.indexer import accepts_block
from databasehub.models import VectorCollection

from tests.test_sources.fakes import Library, ingest


def _clip(role):
    return ContentBlock("b", kind=VIDEO, metadata={"role": role})


def test_block_kinds_select_by_kind_regardless_of_role():
    options = {"block_kinds": ["video"]}
    assert accepts_block(_clip("short_video"), options)
    # A kind filter alone does not judge roles: the source's model does, later.
    assert accepts_block(_clip("long_video"), options)
    assert not accepts_block(ContentBlock("t", kind=TEXT, text="x"), options)


def test_block_roles_tell_a_transcript_from_prose():
    transcript = ContentBlock("t", kind=TEXT, text="x", metadata={"role": "l2_transcript"})
    prose = ContentBlock("p", kind=TEXT, text="x")
    options = {"block_kinds": ["text"], "block_roles": ["l2_transcript"]}
    assert accepts_block(transcript, options)
    assert not accepts_block(prose, options)


def test_no_filters_take_everything():
    assert accepts_block(ContentBlock("a", kind=AUDIO), {})


class _RoutingLibrary(Library):
    """Real profiles, so routing reads the real model roles."""

    def describe_source(self, source):
        return describe_vector_source(source.configuration)


def _source(library, source_id, **options):
    source = Source(
        source_id=source_id,
        name=source_id,
        source_type="vector",
        database_id="db",
        location=VectorCollection(f"c_{source_id}", 4),
        configuration=options,
    )
    return library.add_source(replace(source, profile=library.describe_source(source)))


def test_the_report_shows_which_source_takes_each_role():
    library = _RoutingLibrary()
    _source(library, "image-gme", asset_types=["image"])
    _source(library, "video-xclip", asset_types=["video"])
    # Derived content belongs to multimodal sources only; block_roles narrows
    # this one to transcripts alone.
    _source(library, "asr-gme", asset_types=["audio"])
    library.create_asset_pool(
        asset_pool_id="pool",
        name="pool",
        source_configurations=[
            {"source_id": "image-gme"},
            {"source_id": "video-xclip"},
            {"source_id": "asr-gme"},
        ],
    )

    report = library.routing("pool")

    def names(role):
        return [(r["source_name"], r["via"]) for r in report["routes"][role]]

    assert names("image") == [("image-gme", "vector")]
    assert names("doc_image") == [], "standalone images do not include PDF figures"
    assert names("short_video") == [("video-xclip", "vector")]
    assert names("l1_segment") == [("video-xclip", "vector")]
    assert names("l2_transcript") == [("asr-gme", "vector")]
    assert names("audio") == [("asr-gme", "transcript")], "through what was said"
    assert names("long_video") == [], "no model here embeds a long recording"
    assert set(report["uncovered"]) == {"text", "doc_image", "long_video", "l2_caption", "l3_wiki"}


def test_a_preparing_source_does_not_count_as_covering():
    library = _RoutingLibrary()
    _source(library, "text", embedding_backend="openvino", embedding_model="BAAI/bge-small-en-v1.5")
    library.create_asset_pool(asset_pool_id="pool", name="pool")
    ingest(library, "pool", "a")
    library.set_asset_pool_sources("pool", [{"source_id": "text"}])

    report = library.routing("pool")

    assert report["routes"]["text"][0]["effective_state"] == "PREPARING"
    assert "text" in report["uncovered"]
    assert report["routes"]["image"][0]["via"] == "caption"


def test_block_kinds_audio_selects_a_recordings_transcript():
    transcript = ContentBlock(
        "t", kind=TEXT, text="x", metadata={"role": "l2_transcript"}
    )
    assert accepts_block(transcript, {"block_kinds": ["audio"]})
    assert accepts_block(transcript, {"block_kinds": ["text"]}), "it is still text"
    assert not accepts_block(transcript, {"block_kinds": ["image"]})

    library = _RoutingLibrary()
    _source(library, "audio-gme", asset_types=["audio"])
    library.create_asset_pool(
        asset_pool_id="pool", name="pool", source_configurations=[{"source_id": "audio-gme"}]
    )
    routes = library.routing("pool")["routes"]
    assert [r["via"] for r in routes["audio"]] == ["transcript"]
    assert [r["via"] for r in routes["l2_transcript"]] == ["vector"]
    assert routes["image"] == [], "asked for audio only"


def test_a_multimodal_source_also_takes_derived_text_it_embeds():
    library = _RoutingLibrary()
    _source(
        library, "gme-all", asset_types=["image"],
        block_roles=["image", "l2_caption", "l3_wiki"],
    )
    library.create_asset_pool(
        asset_pool_id="pool", name="pool", source_configurations=[{"source_id": "gme-all"}]
    )
    routes = library.routing("pool")["routes"]
    assert [r["via"] for r in routes["image"]] == ["vector"]
    assert routes["doc_image"] == [], "image asset scope excludes document figures"
    assert [r["via"] for r in routes["l2_caption"]] == ["vector"]
    assert [r["via"] for r in routes["l3_wiki"]] == ["vector"]
    assert routes["l2_transcript"] == [], "image assets cannot produce audio transcripts"
    assert routes["text"] == [], "a document's prose has no role and stays with text sources"


def test_a_video_caption_source_never_advertises_raw_video_vectors():
    library = _RoutingLibrary()
    _source(library, "captions", asset_types=["video"], block_roles=["l2_caption"])
    library.create_asset_pool(
        asset_pool_id="pool", name="pool", source_configurations=[{"source_id": "captions"}]
    )

    routes = library.routing("pool")["routes"]

    assert [r["via"] for r in routes["l2_caption"]] == ["vector"]
    for role in ("short_video", "long_video", "l1_segment"):
        assert all(r["via"] != "vector" for r in routes[role])
    assert routes["image"] == routes["doc_image"] == routes["text"] == []


def test_a_precise_image_selector_still_has_image_family_routing_potential():
    library = _RoutingLibrary()
    _source(library, "png", asset_types=["image/png"])
    library.create_asset_pool(
        asset_pool_id="pool", name="pool", source_configurations=[{"source_id": "png"}]
    )

    routes = library.routing("pool")["routes"]

    assert [r["via"] for r in routes["image"]] == ["vector"]
    assert routes["doc_image"] == routes["l2_caption"] == routes["l2_transcript"] == []
