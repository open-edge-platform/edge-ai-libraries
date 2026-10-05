# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for MCP resources and prompts."""

from __future__ import annotations

import json
from datetime import datetime

import httpx
import pytest
from fastmcp import Client
from mcp.shared.exceptions import MCPError

from src.features import ALL_FEATURES, Features
from tests.fakes import FakeVss, make_mcp, make_settings, make_video

pytestmark = pytest.mark.anyio


async def _read_json(client: Client, uri: str) -> dict:
    content = await client.read_resource(uri)
    return json.loads(content[0].text)


async def _render_prompt(features: Features, name: str, arguments: dict) -> str:
    async with Client(make_mcp(features)) as client:
        rendered = await client.get_prompt(name, arguments)
    return rendered.messages[0].content.text


async def test_the_expected_resources_are_offered() -> None:
    async with Client(make_mcp(ALL_FEATURES)) as client:
        uris = {str(resource.uri) for resource in await client.list_resources()}

    assert uris == {
        "vss://deployment",
        "vss://videos",
        "vss://tags",
        "vss://search-patterns",
    }


async def test_a_resource_describes_why_it_exists() -> None:
    """The description is what a client shows before attaching it."""

    async with Client(make_mcp(ALL_FEATURES)) as client:
        resources = {
            str(resource.uri): resource for resource in await client.list_resources()
        }

    assert "indexed" in resources["vss://videos"].description
    assert "unknown tag" in resources["vss://tags"].description


async def test_search_patterns_need_no_backend() -> None:
    """It describes the system, so it is as true of an empty library."""

    async with Client(make_mcp(ALL_FEATURES)) as client:
        patterns = await _read_json(client, "vss://search-patterns")

    assert patterns["works_well"]
    badly = " ".join(patterns["works_badly"]).lower()
    assert all(trap in badly for trap in ("negation", "counting", "text"))


async def test_an_unreachable_backend_is_a_resource_error() -> None:
    """Failures use the protocol's error channel, carrying the reason."""

    fake = FakeVss()
    fake.handle = lambda request: httpx.Response(503, json={"message": "down"})

    async with Client(make_mcp(ALL_FEATURES, fake=fake)) as client:
        with pytest.raises(MCPError) as caught:
            await client.read_resource("vss://videos")

    assert "VSS returned 503 for GET /videos. down" in str(caught.value)


@pytest.mark.parametrize(
    ("uri", "tool"),
    [("vss://videos", "vss_list_videos"), ("vss://tags", "vss_list_tags")],
)
async def test_resources_mirror_their_tools(uri: str, tool: str) -> None:
    fake = FakeVss(videos=[make_video("v1", "a.mp4", ["Camera 2"])])

    async with Client(make_mcp(ALL_FEATURES, fake=fake)) as client:
        body = await _read_json(client, uri)
        result = await client.call_tool(tool, {})

    assert body.pop("refresh_with") == tool
    body.pop("as_of")
    assert body == result.structured_content


@pytest.mark.parametrize(
    ("uri", "tool"),
    [
        ("vss://deployment", "vss_get_deployment_info"),
        ("vss://videos", "vss_list_videos"),
        ("vss://tags", "vss_list_tags"),
    ],
)
async def test_live_resources_are_dated_snapshots(uri: str, tool: str) -> None:
    """A client keeps the text it read; the body must say how old it is."""

    fake = FakeVss(videos=[make_video("v1", "a.mp4", ["Camera 2"])])

    async with Client(make_mcp(ALL_FEATURES, fake=fake)) as client:
        listed = {str(r.uri): r for r in await client.list_resources()}
        body = await _read_json(client, uri)

    datetime.strptime(body["as_of"], "%Y-%m-%dT%H:%M:%SZ")
    assert body["refresh_with"] == tool
    assert "snapshot" in listed[uri].description
    assert tool in listed[uri].description


async def test_the_deployment_resource_carries_no_frozen_clock() -> None:
    """Time ranges computed from a stale attached clock are silently wrong."""

    fake = FakeVss(videos=[make_video("v1", "a.mp4", ["Camera 2"])])

    async with Client(make_mcp(ALL_FEATURES, fake=fake)) as client:
        body = await _read_json(client, "vss://deployment")
        result = await client.call_tool("vss_get_deployment_info", {})

    assert "server_time_utc" not in body
    assert "server_time_utc" in result.structured_content
    assert body["videos_total"] == result.structured_content["videos_total"]


async def test_search_patterns_is_not_dated() -> None:
    """It describes the system, not the library, so it cannot go stale."""

    async with Client(make_mcp(ALL_FEATURES)) as client:
        body = await _read_json(client, "vss://search-patterns")

    assert "as_of" not in body


@pytest.mark.parametrize(
    ("features", "expected"),
    [
        (ALL_FEATURES, {"search_videos", "upload_and_index_videos", "summarize_video"}),
        (Features(summary=False, search=True), {"search_videos", "upload_and_index_videos"}),
        (Features(summary=True, search=False), {"summarize_video"}),
        (Features(summary=False, search=False), set()),
    ],
    ids=["all-features", "search-only", "summary-only", "library-only"],
)
async def test_the_expected_prompts_are_offered(
    features: Features, expected: set[str]
) -> None:
    async with Client(make_mcp(features)) as client:
        names = {prompt.name for prompt in await client.list_prompts()}

    assert names == expected


async def test_a_search_prompt_separates_the_constraints() -> None:
    """Place and time in the query is the most common way to get nothing."""

    text = await _render_prompt(
        ALL_FEATURES,
        "search_videos",
        {"looking_for": "a spill", "where": "Camera 2", "when": "the last 2 hours"},
    )

    assert "a spill" in text
    assert "vss_list_tags" in text
    assert "server_time_utc" in text
    assert "ISO-8601" in text
    assert "vss_search_video" in text
    assert text.index("vss_list_tags") < text.index("vss_search_video")
    assert text.index("server_time_utc") < text.index("vss_search_video")


async def test_a_search_prompt_omits_filters_nobody_asked_for() -> None:
    text = await _render_prompt(ALL_FEATURES, "search_videos", {"looking_for": "a spill"})

    assert "vss_list_tags" not in text
    assert "server_time_utc" not in text
    assert text.splitlines()[2].startswith("1. Search")


async def test_the_index_prompt_uploads_over_http_then_indexes() -> None:
    text = await _render_prompt(
        ALL_FEATURES,
        "upload_and_index_videos",
        {"files": "a.mp4, b.mp4", "tags": "Camera 2"},
    )

    settings = make_settings()
    assert f"curl -s -X POST {settings.vss_base_url}/videos" in text
    assert "video=@" in text
    assert "tags=Camera 2" in text
    assert "videoId" in text
    assert "not an MCP tool" in text
    assert "one call per video" in text
    assert text.index("curl") < text.index("vss_index_video")
    assert "vss_index_videos" not in text


async def test_the_index_prompt_quotes_tags_for_the_shell() -> None:
    text = await _render_prompt(
        ALL_FEATURES, "upload_and_index_videos", {"tags": "it's; rm -rf ~"}
    )

    assert "-F 'tags=it'\"'\"'s; rm -rf ~'" in text


async def test_the_index_prompt_omits_tags_nobody_asked_for() -> None:
    text = await _render_prompt(ALL_FEATURES, "upload_and_index_videos", {})

    assert "-F 'tags=" not in text


async def test_the_summary_prompt_resolves_uploads_then_summarizes() -> None:
    text = await _render_prompt(
        ALL_FEATURES, "summarize_video", {"video": "dock camera", "focus": "forklifts"}
    )

    order = ["vss_resolve_video", "curl", "vss_summarize_video", "vss_get_video_timeline"]
    positions = [text.index(token) for token in order]
    assert positions == sorted(positions)
    assert "focus='forklifts'" in text
    assert "Keep the default final_summary=true" in text
    assert "state_id" in text


async def test_the_summary_prompt_skips_the_narrative_only_on_request() -> None:
    text = await _render_prompt(
        ALL_FEATURES, "summarize_video", {"video": "v1", "overall": "no"}
    )

    assert "final_summary=false" in text
    assert "focus=" not in text


async def test_the_summary_prompt_works_without_search() -> None:
    text = await _render_prompt(
        Features(summary=True, search=False), "summarize_video", {"video": "v1"}
    )

    assert "vss_index_video" not in text
    assert "vss_search_video" not in text
