# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tool-layer tests against the in-process fake Pipeline Manager.

How to run (from ``mcp/``; no running VSS needed, network access is blocked)::

    uv run pytest                              # whole suite
    uv run pytest tests/test_tools.py          # this file
    uv run pytest tests/test_tools.py -k search -v

These are plain pytest tests (``assert``, fixtures, ``parametrize``), not
``unittest.TestCase`` classes. Async tests run through the anyio plugin, which
comes with FastMCP's anyio dependency. Shared fixtures (``fake``, ``deps``,
``settings``) are in ``conftest.py`` and data builders are in ``fakes.py``.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from src.clients import VssClient, VssError
from src.tools import Deps
from src.tools.discovery import (
    get_deployment_info,
    list_tags,
    list_videos,
    match_tags,
    resolve_video,
    tag_counts,
)
from src.tools.ingest import index_video
from src.tools.search import (
    get_search,
    list_searches,
    refetch_search,
    search_video,
    watch_search,
)
from src.tools.summary import get_video_timeline, summarize_video

from tests.fakes import (
    BASE_URL,
    DATASTORE_URL,
    FakeVss,
    make_features,
    make_hit,
    make_settings,
    make_state,
    make_temp_image,
    make_video,
    seed_searches,
)

pytestmark = pytest.mark.anyio


def posted_body(fake: FakeVss, path: str) -> dict:
    return next(body for method, request_path, body in fake.requests if request_path == path)


def request_paths(fake: FakeVss, method: str | None = None) -> list[str]:
    return [
        path
        for request_method, path, _ in fake.requests
        if method is None or request_method == method
    ]


def library_fetches(fake: FakeVss) -> int:
    return sum(1 for method, path, _ in fake.requests if method == "GET" and path == "/videos")


def unnamed_hit(video_id: str) -> dict:
    hit = make_hit(video_id, 0.9, 10)
    hit["metadata"]["video_metadata"] = {}
    return hit


@pytest.fixture
def tagged_fake() -> FakeVss:
    return FakeVss(
        videos=[
            make_video("v1", "a.mp4", tags=["Camera 2", "Parking Lot"]),
            make_video("v2", "b.mp4", tags=["Camera 3"]),
        ],
        states=[make_state("s1", "v1"), make_state("s2", "v2")],
        hits=[make_hit("v1", 0.9, 10)],
    )


# Discovery


async def test_deployment_info_counts_indexed_videos(fake: FakeVss, deps: Deps) -> None:
    fake.videos = [make_video("v1", "a.mp4", indexed=True), make_video("v2", "b.mp4")]

    info = await get_deployment_info(deps)

    assert info["search_enabled"]
    assert info["videos_total"] == 2
    assert info["videos_indexed"] == 1
    assert info["videos_index_unknown"] == 1


async def test_deployment_info_has_no_unknowns_when_every_status_is_known(
    fake: FakeVss, deps: Deps
) -> None:
    fake.videos = [
        make_video("v1", "a.mp4", indexed=True),
        make_video("v2", "b.mp4", indexed=False),
    ]

    info = await get_deployment_info(deps)

    assert info["videos_indexed"] == 1
    assert info["videos_index_unknown"] == 0


async def test_deployment_info_reports_server_time_for_time_ranges(deps: Deps) -> None:
    """Agents compute search ranges themselves and need a clock to do it."""

    info = await get_deployment_info(deps)

    parsed = datetime.strptime(info["server_time_utc"], "%Y-%m-%dT%H:%M:%SZ")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((now - parsed).total_seconds()) < 60


async def test_deployment_info_surfaces_upload_guidance(deps: Deps) -> None:
    info = await get_deployment_info(deps)

    assert info["upload"] == {
        "url": "http://vss.test/manager/videos",
        "method": "POST",
        "content_type": "multipart/form-data",
        "file_field": "video",
        "tags_field": "tags",
    }


async def test_list_videos_surfaces_the_real_filename(fake: FakeVss, deps: Deps) -> None:
    """The `name` column holds multer's hex; dataStore.fileName is the truth."""

    fake.videos = [make_video("v1", "warehouse.mp4")]

    result = await list_videos(deps)

    assert result["videos"][0]["name"] == "warehouse.mp4"
    assert result["videos"][0]["indexed"] is None


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ({"searchEmbeddings": True}, True),
        ({"textEmbeddings": True}, True),
        ({"searchEmbeddings": False, "textEmbeddings": True}, True),
        ({"searchEmbeddings": False}, False),
        ({}, None),
    ],
)
async def test_indexing_status_comes_from_the_video_row(
    flags: dict, expected: bool | None
) -> None:
    fake = FakeVss(videos=[{**make_video("v1", "a.mp4"), **flags}])
    deps = Deps(client=fake.client(), settings=make_settings())

    listed = await list_videos(deps)

    assert listed["videos"][0]["indexed"] is expected


async def test_summary_runs_are_not_read_as_indexing_status(
    fake: FakeVss, deps: Deps
) -> None:
    """Only the row's own flags count; no state listing is fetched."""

    fake.videos = [make_video("v1", "a.mp4")]
    fake.states = [make_state("s1", "v1")]

    info = await get_deployment_info(deps)
    listed = await list_videos(deps)

    assert info["videos_indexed"] == 0
    assert info["videos_index_unknown"] == 1
    assert listed["videos"][0]["indexed"] is None
    assert "/summary/ui" not in request_paths(fake)


async def test_empty_library_has_zero_indexed_videos(deps: Deps) -> None:
    info = await get_deployment_info(deps)

    assert info["videos_indexed"] == 0


async def test_deployment_info_omits_indexing_counts_in_summary_only_mode() -> None:
    """Summary-only deployments have no search index counts."""

    fake = FakeVss(videos=[make_video("v1", "a.mp4", indexed=True)])
    deps = Deps(
        client=fake.client(),
        settings=make_settings(),
        features=make_features(summary=True, search=False),
    )

    info = await get_deployment_info(deps)

    assert info["videos_total"] == 1
    assert "videos_indexed" not in info
    assert "videos_index_unknown" not in info


async def test_list_videos_omits_indexed_flag_in_summary_only_mode() -> None:
    fake = FakeVss(videos=[make_video("v1", "a.mp4", indexed=True)])
    deps = Deps(
        client=fake.client(),
        settings=make_settings(),
        features=make_features(summary=True, search=False),
    )

    result = await list_videos(deps)

    assert "indexed" not in result["videos"][0]


async def test_resolve_video_omits_indexed_flag_in_summary_only_mode() -> None:
    fake = FakeVss(videos=[make_video("v1", "a.mp4", indexed=True)])
    deps = Deps(
        client=fake.client(),
        settings=make_settings(),
        features=make_features(summary=True, search=False),
    )

    resolution = await resolve_video(deps, "v1")

    assert "indexed" not in resolution["candidates"][0]


async def test_list_videos_filters_by_tag(fake: FakeVss, deps: Deps) -> None:
    fake.videos = [
        make_video("v1", "a.mp4", ["outdoor"]),
        make_video("v2", "b.mp4", ["indoor"]),
    ]

    result = await list_videos(deps, tag="Outdoor")

    assert len(result["videos"]) == 1
    assert result["videos"][0]["video_id"] == "v1"


async def test_resolve_video_matches_a_substring(fake: FakeVss, deps: Deps) -> None:
    fake.videos = [
        make_video("v1", "warehouse-friday.mp4"),
        make_video("v2", "lobby.mp4"),
    ]

    result = await resolve_video(deps, "warehouse")

    assert result["unambiguous"]
    assert result["candidates"][0]["video_id"] == "v1"
    assert result["candidates"][0]["match"] == "substring"


async def test_resolve_video_prefers_an_exact_id(fake: FakeVss, deps: Deps) -> None:
    fake.videos = [make_video("v1", "a.mp4"), make_video("v2", "v1.mp4")]

    result = await resolve_video(deps, "v1")

    assert result["candidates"][0]["match"] == "exact_id"
    assert result["candidates"][0]["video_id"] == "v1"


async def test_resolve_video_is_ambiguous_with_several_candidates(
    fake: FakeVss, deps: Deps
) -> None:
    fake.videos = [
        make_video("v1", "warehouse-1.mp4"),
        make_video("v2", "warehouse-2.mp4"),
    ]

    result = await resolve_video(deps, "warehouse")

    assert not result["unambiguous"]
    assert len(result["candidates"]) == 2


async def test_resolve_video_returns_no_candidates_when_nothing_matches(
    fake: FakeVss, deps: Deps
) -> None:
    fake.videos = [make_video("v1", "a.mp4")]

    result = await resolve_video(deps, "nonexistent")

    assert result["candidates"] == []
    assert not result["unambiguous"]


# Summary


async def test_summarize_requests_a_final_summary_by_default(
    fake: FakeVss, deps: Deps
) -> None:
    """VSS's API and UI both produce a final summary unless told not to."""

    fake.videos = [make_video("v1", "clip.mp4")]
    fake.state_on_create = make_state("s1", "v1", final="complete")

    result = await summarize_video(deps, "v1")

    assert posted_body(fake, "/summary")["produceFinalSummary"] is True
    assert result["completed"]
    assert result["summary"] == "Rolled up."


async def test_summarize_can_request_chunk_level_only(
    fake: FakeVss, deps: Deps
) -> None:
    fake.videos = [make_video("v1", "clip.mp4")]
    fake.state_on_create = make_state("s1", "v1", final="na")

    await summarize_video(deps, "v1", final_summary=False)

    assert posted_body(fake, "/summary")["produceFinalSummary"] is False


async def test_summarize_terminates_although_status_stays_na(
    fake: FakeVss, deps: Deps
) -> None:
    """Chunk-only summaries should finish even when final status stays `na`."""

    fake.videos = [make_video("v1", "clip.mp4")]
    fake.state_on_create = make_state("s1", "v1", final="na")

    result = await summarize_video(deps, "v1", final_summary=False)

    assert result["completed"]
    assert len(result["timeline"]) == 2
    assert "summary" not in result


async def test_summarize_with_final_summary_waits_for_complete(
    fake: FakeVss, deps: Deps
) -> None:
    fake.videos = [make_video("v1", "clip.mp4")]
    fake.state_on_create = make_state("s1", "v1", final="complete")

    result = await summarize_video(deps, "v1", final_summary=True)

    assert result["completed"]
    assert result["summary"] == "Rolled up."
    assert posted_body(fake, "/summary")["produceFinalSummary"] is True


async def test_summarize_returns_a_partial_timeline_when_the_budget_expires() -> None:
    """A stuck pipeline must degrade to a partial result, not hang."""

    fake = FakeVss(videos=[make_video("v1", "clip.mp4")])
    fake.state_on_create = make_state("s1", "v1", in_progress=3, chunking="inProgress")
    deps = Deps(client=fake.client(), settings=make_settings(default_wait_seconds=0.05))

    result = await summarize_video(deps, "v1")

    assert not result["completed"]
    assert result["state_id"] == "s1"
    assert "timeline" in result


async def test_summarize_builds_a_body_that_passes_validation(
    fake: FakeVss, deps: Deps
) -> None:
    """frameOverlap + samplingFrame must equal multiFrame."""

    fake.videos = [make_video("v1", "clip.mp4")]
    fake.state_on_create = make_state("s1", "v1", final="complete")

    await summarize_video(deps, "v1")

    posted = posted_body(fake, "/summary")
    sampling = posted["sampling"]
    assert sampling["frameOverlap"] + sampling["samplingFrame"] == sampling["multiFrame"]
    assert sampling["multiFrame"] <= 8
    assert "evamPipeline" in posted["evam"]
    assert posted["title"] == "clip.mp4"


async def test_focus_extends_rather_than_replaces_the_frame_prompt(
    fake: FakeVss, deps: Deps
) -> None:
    fake.videos = [make_video("v1", "clip.mp4")]
    fake.state_on_create = make_state("s1", "v1", final="complete")

    await summarize_video(deps, "v1", focus="forklifts")

    prompt = posted_body(fake, "/summary")["prompts"]["framePrompt"]
    assert "Describe the frame." in prompt
    assert "forklifts" in prompt


async def test_summarize_rejects_an_unknown_video(deps: Deps) -> None:
    with pytest.raises(VssError, match="No video with id"):
        await summarize_video(deps, "missing")


async def test_timeline_reports_when_a_video_was_never_summarized(
    fake: FakeVss, deps: Deps
) -> None:
    fake.videos = [make_video("v1", "clip.mp4")]

    with pytest.raises(VssError, match="has not been summarized"):
        await get_video_timeline(deps, video_id="v1")


async def test_timeline_by_state_id(fake: FakeVss, deps: Deps) -> None:
    fake.states = [make_state("s1", "v1", captions=3)]

    result = await get_video_timeline(deps, state_id="s1")

    assert len(result["timeline"]) == 3


# Search


async def test_embedding_search_does_not_infer_coverage_from_summaries() -> None:
    fake = FakeVss(
        videos=[make_video("v1", "clip.mp4")],
        hits=[make_hit("v1", 0.9, 10)],
    )
    deps = Deps(
        client=fake.client(),
        settings=make_settings(),
        features=make_features(summary=False, search=True),
    )

    result = await search_video(deps, "person")

    assert result["count"] == 1
    assert "not indexed" not in json.dumps(result)
    assert "were not searched" not in json.dumps(result)
    assert "index_video" not in json.dumps(result)
    assert "/summary/ui" not in request_paths(fake)


async def test_search_returns_slim_ranked_hits(fake: FakeVss, deps: Deps) -> None:
    fake.videos = [make_video("v1", "clip.mp4")]
    fake.states = [make_state("s1", "v1")]
    fake.hits = [make_hit("v1", 0.51, 10), make_hit("v1", 0.93, 40)]

    result = await search_video(deps, "man in green pants")

    assert result["count"] == 2
    assert result["results"][0]["score"] == 0.93
    assert "score_breakdown" not in result["results"][0]
    assert "coverage" not in result


async def test_search_returns_a_host_reachable_download_url(
    fake: FakeVss, deps: Deps
) -> None:
    """A backend-joined hit is directly downloadable."""

    hit = make_hit("v1", 0.9, 10)
    hit["videoPlaybackUrl"] = "/vss/v1/source.mp4"
    fake.videos = [make_video("v1", "clip.mp4")]
    fake.states = [make_state("s1", "v1")]
    fake.hits = [hit]

    result = await search_video(deps, "man in green pants")

    assert result["results"][0]["url"] == f"{DATASTORE_URL}/vss/v1/source.mp4"
    assert "media" not in result["results"][0]


async def test_no_matches_does_not_claim_missing_summaries_were_not_searched(
    fake: FakeVss, deps: Deps
) -> None:
    """Summary history cannot establish the scope of the search index."""

    fake.videos = [make_video("v1", "a.mp4"), make_video("v2", "b.mp4")]
    fake.states = [make_state("s1", "v1")]

    result = await search_video(deps, "forklift")

    assert result["count"] == 0
    assert "coverage" not in result


async def test_search_sends_an_absolute_time_filter_in_utc(
    fake: FakeVss, deps: Deps
) -> None:
    result = await search_video(
        deps,
        "forklift",
        start="2026-08-04T10:00:00+02:00",
        end="2026-08-04T12:00:00Z",
    )

    assert posted_body(fake, "/search")["timeFilter"] == {
        "start": "2026-08-04T08:00:00.000Z",
        "end": "2026-08-04T12:00:00.000Z",
        "source": "absolute",
    }
    assert result["time_range"] == {
        "start": "2026-08-04T08:00:00.000Z",
        "end": "2026-08-04T12:00:00.000Z",
    }


async def test_a_naive_timestamp_is_read_as_utc(fake: FakeVss, deps: Deps) -> None:
    await search_video(
        deps, "forklift", start="2026-08-04", end="2026-08-05T00:00:00"
    )

    time_filter = posted_body(fake, "/search")["timeFilter"]
    assert time_filter["start"] == "2026-08-04T00:00:00.000Z"
    assert time_filter["end"] == "2026-08-05T00:00:00.000Z"


async def test_no_time_arguments_sends_no_time_filter(fake: FakeVss, deps: Deps) -> None:
    result = await search_video(deps, "forklift")

    assert "timeFilter" not in posted_body(fake, "/search")
    assert "time_range" not in result


@pytest.mark.parametrize(
    ("message", "kwargs"),
    [
        ("both start and end", {"start": "2026-08-04T00:00:00Z"}),
        ("both start and end", {"end": "2026-08-04T00:00:00Z"}),
        ("not an ISO-8601", {"start": "tuesday", "end": "2026-08-04T00:00:00Z"}),
        (
            "not be after end",
            {"start": "2026-08-05T00:00:00Z", "end": "2026-08-04T00:00:00Z"},
        ),
    ],
)
async def test_search_rejects_time_ranges_the_backend_would_drop(
    fake: FakeVss, deps: Deps, message: str, kwargs: dict
) -> None:
    """Pipeline Manager silently ignores these, returning unfiltered hits."""

    with pytest.raises(VssError, match=message):
        await search_video(deps, "forklift", **kwargs)

    assert "/search" not in request_paths(fake)


async def test_search_rejects_an_empty_query(deps: Deps) -> None:
    with pytest.raises(VssError, match="Provide a query"):
        await search_video(deps, "   ")


async def test_search_honours_the_limit(fake: FakeVss, deps: Deps) -> None:
    fake.videos = [make_video("v1", "a.mp4")]
    fake.states = [make_state("s1", "v1")]
    fake.hits = [make_hit("v1", 0.9 - i / 100, i * 10) for i in range(10)]

    result = await search_video(deps, "forklift", limit=3)

    assert result["count"] == 3


async def test_search_by_image_posts_an_image_not_a_query(
    fake: FakeVss, deps: Deps
) -> None:
    fake.videos = [make_video("v1", "a.mp4")]
    fake.states = [make_state("s1", "v1")]
    fake.hits = [make_hit("v1", 0.9, 10)]

    with make_temp_image() as image_path:
        result = await search_video(deps, image=image_path)

    posted = posted_body(fake, "/search")
    assert "image" in posted
    assert posted["image"].startswith("data:image/png;base64,")
    assert "query" not in posted
    assert "image" not in result
    assert result["count"] == 1


async def test_search_by_image_data_url_does_not_starve_the_byte_budget(
    fake: FakeVss, deps: Deps
) -> None:
    """Large image inputs should not truncate the search hits."""

    fake.videos = [make_video("v1", "a.mp4")]
    fake.states = [make_state("s1", "v1")]
    fake.hits = [make_hit("v1", 0.9, 10)]
    large_data_url = "data:image/jpeg;base64," + ("A" * 50_000)

    result = await search_video(deps, image=large_data_url)

    assert result["count"] == 1
    assert not result["truncated"]


async def test_search_by_image_forwards_a_data_url_unchanged(
    fake: FakeVss, deps: Deps
) -> None:
    fake.videos = [make_video("v1", "a.mp4")]
    fake.states = [make_state("s1", "v1")]
    fake.hits = [make_hit("v1", 0.9, 10)]
    data_url = "data:image/png;base64,aGVsbG8="

    result = await search_video(deps, image=data_url)

    assert posted_body(fake, "/search")["image"] == data_url
    assert "image" not in result


async def test_search_by_image_rejects_a_malformed_data_url(deps: Deps) -> None:
    with pytest.raises(VssError, match="Malformed data URL"):
        await search_video(deps, image="data:image/png,not-base64")


@pytest.mark.parametrize(
    "reference",
    [
        "http://192.168.1.10:12345/datastore/video-summary/search-images/"
        "3f0c1f1e-7c1b-4a8e-9a55-0d6f6c2b9e11.jpg",
        "/datastore/video-summary/search-images/3f0c1f1e-7c1b-4a8e-9a55-0d6f6c2b9e11.jpg",
        "3f0c1f1e-7c1b-4a8e-9a55-0d6f6c2b9e11.jpg",
    ],
)
async def test_search_by_image_forwards_an_uploaded_image_reference(
    reference: str,
) -> None:
    """Claim-check uploaded images by reference instead of base64 payload."""

    fake = FakeVss(
        videos=[make_video("v1", "a.mp4")],
        states=[make_state("s1", "v1")],
        hits=[make_hit("v1", 0.9, 10)],
    )
    deps = Deps(client=fake.client(), settings=make_settings())

    result = await search_video(deps, image=reference)

    assert posted_body(fake, "/search") == {"imageUrl": reference}
    assert result["count"] == 1


async def test_search_by_image_reads_a_local_file_named_like_an_upload(
    fake: FakeVss, deps: Deps
) -> None:
    fake.videos = [make_video("v1", "a.mp4")]
    fake.states = [make_state("s1", "v1")]
    fake.hits = [make_hit("v1", 0.9, 10)]

    with make_temp_image() as image_path, tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / "search-images" / "3f0c1f1e-7c1b-4a8e-9a55-0d6f6c2b9e11.png"
        local.parent.mkdir()
        local.write_bytes(Path(image_path).read_bytes())
        await search_video(deps, image=str(local))

    posted = posted_body(fake, "/search")
    assert "imageUrl" not in posted
    assert posted["image"].startswith("data:image/png;base64,")


async def test_search_rejects_both_query_and_image(deps: Deps) -> None:
    with make_temp_image() as image_path:
        with pytest.raises(VssError, match="not both"):
            await search_video(deps, "forklift", image=image_path)


async def test_search_rejects_neither_query_nor_image(deps: Deps) -> None:
    with pytest.raises(VssError, match="Provide a query"):
        await search_video(deps)


@pytest.mark.parametrize(
    "message",
    ["No file at", r"data:<mime-type>;base64,"],
)
async def test_search_by_image_missing_file_error_guides_the_caller(
    deps: Deps, message: str
) -> None:
    with pytest.raises(VssError, match=message):
        await search_video(deps, image="/nonexistent/still.png")


async def test_search_by_image_rejects_an_unsupported_suffix(deps: Deps) -> None:
    with pytest.raises(VssError, match="does not look like an image"):
        await search_video(deps, image=__file__)


# Search request shaping


async def test_named_hits_do_not_fetch_the_library(fake: FakeVss, deps: Deps) -> None:
    fake.videos = [make_video("v1", "a.mp4")]
    fake.hits = [make_hit("v1", 0.9, 10)]

    result = await search_video(deps, "x")

    assert result["results"][0]["video_name"] == "clip.mp4"
    assert library_fetches(fake) == 0


async def test_unnamed_hits_are_named_from_the_library(
    fake: FakeVss, deps: Deps
) -> None:
    fake.videos = [make_video("v1", "a.mp4")]
    fake.hits = [unnamed_hit("v1")]

    result = await search_video(deps, "x")

    assert result["results"][0]["video_name"] == "a.mp4"
    assert library_fetches(fake) == 1


async def test_a_tag_filter_reuses_the_listing_for_names(
    fake: FakeVss, deps: Deps
) -> None:
    fake.videos = [make_video("v1", "a.mp4", tags=["Camera 2"])]
    fake.hits = [unnamed_hit("v1")]

    result = await search_video(deps, "x", tags=["camera 2"])

    assert result["results"][0]["video_name"] == "a.mp4"
    assert library_fetches(fake) == 1


async def test_an_unknown_tag_lists_the_library_once(fake: FakeVss, deps: Deps) -> None:
    fake.videos = [make_video("v1", "a.mp4", tags=["Camera 2"])]

    result = await search_video(deps, "x", tags=["Camera 9"])

    assert result["available_tags"] == ["Camera 2"]
    assert library_fetches(fake) == 1


async def test_an_unknown_tag_does_not_echo_a_data_url(
    fake: FakeVss, deps: Deps
) -> None:
    fake.videos = [make_video("v1", "a.mp4", tags=["Camera 2"])]
    data_url = "data:image/png;base64," + "A" * 50_000

    result = await search_video(deps, image=data_url, tags=["Camera 9"])

    assert "image" not in result
    assert result["available_tags"] == ["Camera 2"]


# Ingest


async def test_index_uses_the_summary_path_in_unified_mode() -> None:
    """Unified mode indexes by summarizing, not frame embeddings."""

    fake = FakeVss(videos=[make_video("v1", "clip.mp4")])
    fake.state_on_create = make_state("s1", "v1")
    deps = Deps(
        client=fake.client(),
        settings=make_settings(),
        features=make_features(image_search_enabled=False),
    )

    result = await index_video(deps, "v1")

    assert result["strategy"] == "summary"
    assert result["indexed"]
    assert "/videos/search-embeddings/v1" not in request_paths(fake)


async def test_index_uses_the_embedding_endpoint_in_dual_mode(
    fake: FakeVss, deps: Deps
) -> None:
    """Dual mode prefers the independent frame-embedding index."""

    fake.videos = [make_video("v1", "clip.mp4")]

    result = await index_video(deps, "v1")

    assert result["strategy"] == "embeddings"
    assert "/videos/search-embeddings/v1" in request_paths(fake)


async def test_index_uses_the_embedding_endpoint_when_summary_is_off() -> None:
    fake = FakeVss(
        videos=[make_video("v1", "clip.mp4")],
        states=[make_state("old-summary", "v1")],
        features={"summary": "FEATURE_OFF", "search": "FEATURE_ON"},
    )
    deps = Deps(
        client=fake.client(),
        settings=make_settings(),
        features=make_features(summary=False),
    )

    result = await index_video(deps, "v1")

    assert result["strategy"] == "embeddings"
    assert "/videos/search-embeddings/v1" in request_paths(fake)


async def test_index_is_idempotent(fake: FakeVss, deps: Deps) -> None:
    fake.videos = [make_video("v1", "clip.mp4", indexed=True)]

    result = await index_video(deps, "v1")

    assert result["indexed"]
    assert not request_paths(fake, method="POST")


async def test_index_rejects_an_unknown_video(deps: Deps) -> None:
    with pytest.raises(VssError, match="No video with id"):
        await index_video(deps, "missing")


# Client errors


async def test_connection_failure_names_the_backend() -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = VssClient(
        BASE_URL,
        client=httpx.AsyncClient(base_url=BASE_URL, transport=httpx.MockTransport(explode)),
    )

    with pytest.raises(VssError, match="Could not reach VSS"):
        await client.get_features()


async def test_upstream_error_carries_a_hint() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"message": "data-prep exploded"})

    client = VssClient(
        BASE_URL,
        client=httpx.AsyncClient(base_url=BASE_URL, transport=httpx.MockTransport(fail)),
    )

    with pytest.raises(VssError) as caught:
        await client.get_features()

    message = str(caught.value)
    assert "502" in message
    assert "data-prep exploded" in message
    assert "dependency" in message


# VSS errors


def test_vss_error_carries_the_status_it_was_raised_from() -> None:
    error = VssError("VSS returned 404 for GET /videos/x.", status_code=404)

    assert error.status_code == 404


def test_vss_error_failure_with_no_response_has_no_status() -> None:
    assert VssError("Could not reach VSS.").status_code is None


# Tags


async def test_tag_counts_how_many_videos_carry_each(tagged_fake: FakeVss) -> None:
    tagged_fake.videos.append(make_video("v3", "c.mp4", tags=["Camera 2"]))

    listed = await list_tags(Deps(client=tagged_fake.client(), settings=make_settings()))

    assert listed["tags"][0] == {"tag": "Camera 2", "videos": 2}


@pytest.mark.parametrize("said", ["camera 2", "CAMERA 2", "camera-2", "camera2"])
def test_tag_match_ignores_case_and_punctuation(tagged_fake: FakeVss, said: str) -> None:
    """Operators say "camera 2"; the tag might be "Camera 2"."""

    matched, unmatched = match_tags([said], tag_counts(tagged_fake.videos))

    assert matched == ["Camera 2"]
    assert unmatched == []


def test_exact_tag_is_never_beaten_by_a_longer_one(tagged_fake: FakeVss) -> None:
    tagged_fake.videos.append(make_video("v3", "c.mp4", tags=["Camera 2 North"]))

    matched, _ = match_tags(["Camera 2"], tag_counts(tagged_fake.videos))

    assert matched == ["Camera 2"]


def test_a_tag_nobody_uses_is_reported(tagged_fake: FakeVss) -> None:
    matched, unmatched = match_tags(["Camera 9"], tag_counts(tagged_fake.videos))

    assert matched == []
    assert unmatched == ["Camera 9"]


async def test_a_matching_tag_narrows_the_search(tagged_fake: FakeVss) -> None:
    result = await search_video(
        Deps(client=tagged_fake.client(), settings=make_settings()),
        "a forklift",
        tags=["parking lot"],
    )

    posted = posted_body(tagged_fake, "/search")
    assert posted["tags"] == "Parking Lot"
    assert result["tags"] == ["Parking Lot"]


async def test_an_unknown_tag_says_so_instead_of_finding_nothing(
    tagged_fake: FakeVss,
) -> None:
    """VSS answers an unknown tag with an empty result set, not an error."""

    result = await search_video(
        Deps(client=tagged_fake.client(), settings=make_settings()),
        "a forklift",
        tags=["Camera 9"],
    )

    assert result["count"] == 0
    assert result["unknown_tags"] == ["Camera 9"]
    assert "Camera 2" in result["available_tags"]
    assert "/search" not in request_paths(tagged_fake)


async def test_one_good_tag_among_bad_ones_still_searches(tagged_fake: FakeVss) -> None:
    result = await search_video(
        Deps(client=tagged_fake.client(), settings=make_settings()),
        "a forklift",
        tags=["Camera 2", "Camera 9"],
    )

    assert result["tags"] == ["Camera 2"]
    assert result["unknown_tags"] == ["Camera 9"]
    assert result["count"] == 1


async def test_a_tag_filter_combines_with_a_time_window(tagged_fake: FakeVss) -> None:
    await search_video(
        Deps(client=tagged_fake.client(), settings=make_settings()),
        "a forklift",
        tags=["Camera 2"],
        start="2026-08-04T00:00:00Z",
        end="2026-08-04T02:00:00Z",
    )

    posted = posted_body(tagged_fake, "/search")
    assert posted["tags"] == "Camera 2"
    assert posted["timeFilter"]["source"] == "absolute"
    assert posted["query"] == "a forklift"


async def test_no_tags_searches_everything(tagged_fake: FakeVss) -> None:
    result = await search_video(
        Deps(client=tagged_fake.client(), settings=make_settings()),
        "a forklift",
    )

    posted = posted_body(tagged_fake, "/search")
    assert "tags" not in posted
    assert "unknown_tags" not in result


# Persisted search


async def test_search_is_persisted_like_a_ui_search(fake: FakeVss, deps: Deps) -> None:
    """The search goes to POST /search, not the one-off /search/query."""

    fake.videos = [make_video("v1", "a.mp4")]
    fake.hits = [make_hit("v1", 0.9, 10)]

    result = await search_video(deps, "forklift")

    assert posted_body(fake, "/search") == {"query": "forklift"}
    assert "/search/query" not in request_paths(fake)
    assert result["query_id"] == "q1"
    assert result["status"] == "idle"
    assert result["count"] == 1
    assert fake.searches["q1"]["query"] == "forklift"


async def test_search_still_running_returns_its_query_id(
    fake: FakeVss,
) -> None:
    """A slow search degrades to a handle, not a hang or an empty answer."""

    fake.search_status = "running"
    deps = Deps(client=fake.client(), settings=make_settings(default_wait_seconds=0.05))

    result = await search_video(deps, "forklift")

    assert result["status"] == "running"
    assert result["query_id"] == "q1"
    assert result["count"] == 0


async def test_search_reports_a_failed_query(fake: FakeVss, deps: Deps) -> None:
    fake.search_status = "error"
    fake.search_error = "No videos found in search database."

    with pytest.raises(VssError, match="No videos found"):
        await search_video(deps, "forklift")


async def test_search_waits_no_longer_than_requested(fake: FakeVss) -> None:
    fake.search_status = "running"
    deps = Deps(client=fake.client(), settings=make_settings(default_wait_seconds=30))

    result = await search_video(deps, "forklift", wait_seconds=0)

    assert result["status"] == "running"


async def test_get_search_returns_stored_hits(fake: FakeVss, deps: Deps) -> None:
    fake.videos = [make_video("v1", "a.mp4")]
    fake.hits = [make_hit("v1", 0.5, 10), make_hit("v1", 0.9, 20)]
    seed_searches(fake, 1)

    result = await get_search(deps, "q1")

    assert result["query_id"] == "q1"
    assert result["query"] == "forklift near dock 1"
    assert result["status"] == "idle"
    assert result["tags"] == ["Camera 2"]
    assert [hit["score"] for hit in result["results"]] == [0.9, 0.5]


async def test_get_search_rejects_an_unknown_id(deps: Deps) -> None:
    with pytest.raises(VssError, match="No search query with id"):
        await get_search(deps, "nope")


async def test_list_searches_is_newest_first_without_query_images(
    fake: FakeVss, deps: Deps
) -> None:
    seed_searches(fake, 3)
    fake.searches["q2"]["image"] = "data:image/png;base64," + "A" * 1000
    fake.searches["q2"]["query"] = ""

    result = await list_searches(deps, limit=2)

    assert result["total"] == 3
    assert [item["query_id"] for item in result["searches"]] == ["q3", "q2"]
    assert result["searches"][1]["image_search"] is True
    assert "query" not in result["searches"][1]
    assert "base64" not in json.dumps(result)


async def test_refetch_search_reruns_with_a_new_time_range(
    fake: FakeVss, deps: Deps
) -> None:
    fake.hits = [make_hit("v1", 0.9, 10)]
    seed_searches(fake, 1)
    fake.searches["q1"]["results"] = []

    result = await refetch_search(
        deps, "q1", start="2026-08-04T00:00:00Z", end="2026-08-05T00:00:00Z"
    )

    assert posted_body(fake, "/search/q1/refetch")["timeFilter"] == {
        "start": "2026-08-04T00:00:00.000Z",
        "end": "2026-08-05T00:00:00.000Z",
        "source": "absolute",
    }
    assert result["count"] == 1
    assert result["time_range"]["start"] == "2026-08-04T00:00:00.000Z"


async def test_refetch_search_checks_the_id_first(fake: FakeVss, deps: Deps) -> None:
    """Pipeline Manager answers an unknown id with a bare 500."""

    with pytest.raises(VssError, match="No search query with id"):
        await refetch_search(deps, "nope")

    assert not any(path.endswith("/refetch") for path in request_paths(fake))


async def test_watch_search_toggles_the_flag(fake: FakeVss, deps: Deps) -> None:
    seed_searches(fake, 1)

    watched = await watch_search(deps, "q1", True)
    unwatched = await watch_search(deps, "q1", False)

    assert watched["watch"] is True
    assert unwatched["watch"] is False
    assert posted_body(fake, "/search/q1/watch") == {"watch": True}


# Summary options


async def test_summary_defaults_match_the_vss_ui(fake: FakeVss, deps: Deps) -> None:
    fake.videos = [make_video("v1", "clip.mp4")]
    fake.state_on_create = make_state("s1", "v1", final="complete")
    fake.app_config = {
        "evamPipeline": "video_ingestion",
        "meta": {
            "evamPipelines": [
                {"name": "Object Detection", "value": "object_detection"},
                {"name": "Basic Ingestion", "value": "video_ingestion"},
            ],
            "defaultAudioModel": "tiny.en",
            "audioModels": [{"display_name": "Tiny", "model_id": "tiny.en"}],
        },
    }

    await summarize_video(deps, "v1")

    posted = posted_body(fake, "/summary")
    assert posted["sampling"] == {
        "chunkDuration": 8,
        "samplingFrame": 8,
        "frameOverlap": 0,
        "multiFrame": 8,
    }
    assert posted["evam"] == {"evamPipeline": "video_ingestion"}
    assert posted["audio"] == {"audioModel": "tiny.en", "useFullTranscriptSummary": False}
    assert posted["produceFinalSummary"] is True


async def test_summary_forwards_caller_options(fake: FakeVss, deps: Deps) -> None:
    fake.videos = [make_video("v1", "clip.mp4")]
    fake.state_on_create = make_state("s1", "v1", final="complete")
    fake.app_config = {
        "multiFrame": 12,
        "meta": {
            "evamPipelines": [{"name": "Basic", "value": "video_ingestion"}],
            "defaultAudioModel": "tiny.en",
            "audioModels": [
                {"model_id": "tiny.en"},
                {"model_id": "small.en"},
            ],
        },
    }

    await summarize_video(
        deps,
        "v1",
        chunk_duration=15,
        sampling_frames=6,
        frame_overlap=2,
        evam_pipeline="video_ingestion",
        audio_model="small.en",
        audio_full_transcript_summary=True,
    )

    posted = posted_body(fake, "/summary")
    assert posted["sampling"] == {
        "chunkDuration": 15,
        "samplingFrame": 6,
        "frameOverlap": 2,
        "multiFrame": 8,
    }
    assert posted["evam"] == {"evamPipeline": "video_ingestion"}
    assert posted["audio"] == {"audioModel": "small.en", "useFullTranscriptSummary": True}


async def test_full_transcript_summary_needs_a_final_summary(
    fake: FakeVss, deps: Deps
) -> None:
    fake.videos = [make_video("v1", "clip.mp4")]
    fake.state_on_create = make_state("s1", "v1")
    fake.app_config = {
        "meta": {
            "evamPipelines": [{"value": "object_detection"}],
            "defaultAudioModel": "tiny.en",
            "audioModels": [{"model_id": "tiny.en"}],
        }
    }

    await summarize_video(
        deps, "v1", final_summary=False, audio_full_transcript_summary=True
    )

    assert posted_body(fake, "/summary")["audio"]["useFullTranscriptSummary"] is False


async def test_summary_can_skip_audio(fake: FakeVss, deps: Deps) -> None:
    fake.videos = [make_video("v1", "clip.mp4")]
    fake.state_on_create = make_state("s1", "v1", final="complete")
    fake.app_config = {
        "meta": {
            "evamPipelines": [{"value": "object_detection"}],
            "defaultAudioModel": "tiny.en",
            "audioModels": [{"model_id": "tiny.en"}],
        }
    }

    await summarize_video(deps, "v1", audio=False)

    assert "audio" not in posted_body(fake, "/summary")


@pytest.mark.parametrize(
    ("message", "options"),
    [
        ("at most 8 frames", {"sampling_frames": 6, "frame_overlap": 3}),
        ("chunk_duration must be at least 1", {"chunk_duration": 0}),
        ("frame_overlap must be at least 0", {"frame_overlap": -1}),
        ("sampling_frames must be a whole number", {"sampling_frames": 2.5}),
        ("Unknown evam_pipeline", {"evam_pipeline": "nope"}),
        ("no audio model", {"audio_model": "tiny.en"}),
    ],
)
async def test_summary_rejects_options_vss_would_reject(
    fake: FakeVss, deps: Deps, message: str, options: dict
) -> None:
    fake.videos = [make_video("v1", "clip.mp4")]

    with pytest.raises(VssError, match=message):
        await summarize_video(deps, "v1", **options)

    assert "/summary" not in request_paths(fake)


async def test_timeline_includes_the_final_summary_the_run_produced(
    fake: FakeVss, deps: Deps
) -> None:
    state = make_state("s1", "v1", final="complete")
    state["systemConfig"] = {"produceFinalSummary": True}
    fake.states = [state]

    result = await get_video_timeline(deps, state_id="s1")

    assert result["summary"] == "Rolled up."


async def test_timeline_of_a_chunk_only_run_is_complete_without_a_summary(
    fake: FakeVss, deps: Deps
) -> None:
    state = make_state("s1", "v1", final="na")
    state["systemConfig"] = {"produceFinalSummary": False}
    fake.states = [state]

    result = await get_video_timeline(deps, state_id="s1")

    assert result["completed"]
    assert "summary" not in result


async def test_summary_based_indexing_stays_chunk_only(deps: Deps) -> None:
    fake = FakeVss(
        videos=[make_video("v1", "clip.mp4", indexed=False)],
        features={"summary": "FEATURE_ON", "search": "FEATURE_ON"},
    )
    fake.state_on_create = make_state("s1", "v1")
    fake.app_config = {
        "meta": {
            "evamPipelines": [{"value": "object_detection"}],
            "defaultAudioModel": "tiny.en",
            "audioModels": [{"model_id": "tiny.en"}],
        }
    }
    deps = Deps(
        client=fake.client(),
        settings=make_settings(index_strategy="summary"),
    )

    await index_video(deps, "v1")

    posted = posted_body(fake, "/summary")
    assert posted["produceFinalSummary"] is False
    assert "audio" not in posted
