# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for the assembled MCP server and its tool surface."""

from __future__ import annotations

import json
import re

import httpx
import jsonschema
import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from src.clients import VssError
from src.features import ALL_FEATURES, Features
from src.projections import MAX_RESULT_BYTES
from src.server import build_mcp, make_client
from src.tools import Deps, register_all
from tests.fakes import (
    FakeVss,
    NetworkAccessError,
    make_hit,
    make_mcp,
    make_settings,
    make_state,
    seed_searches,
    make_video,
)

pytestmark = pytest.mark.anyio

#: Tools that answer questions about the library itself, which every
#: deployment can serve however it is configured.
LIBRARY_TOOLS = {
    "vss_get_deployment_info",
    "vss_list_videos",
    "vss_resolve_video",
    "vss_list_tags",
}

#: Registered only where the deployment has the search feature. Indexing is
#: here because indexing means "make findable by search".
SEARCH_TOOLS = {
    "vss_index_video",
    "vss_search_video",
    "vss_get_search",
    "vss_list_searches",
    "vss_refetch_search",
    "vss_watch_search",
}

#: Registered only where the deployment has the summary feature.
SUMMARY_TOOLS = {
    "vss_summarize_video",
    "vss_get_video_timeline",
}

EXPECTED_TOOLS = LIBRARY_TOOLS | SEARCH_TOOLS | SUMMARY_TOOLS

#: Tools that start backend work or change stored state; everything else only
#: reads. A search is persisted in VSS's search history, so it writes too.
WORK_TOOLS = {
    "vss_index_video",
    "vss_summarize_video",
    "vss_search_video",
    "vss_refetch_search",
    "vss_watch_search",
}

#: Any tool name a prompt, a resource description or the instructions might
#: mention. Deliberately not anchored to the known names: the point is to find
#: the ones nobody registered.
_TOOL_TOKEN = re.compile(r"vss_[a-z_]+")

#: Every deployment shape the surface is built for.
FEATURE_SHAPES = (
    Features(summary=True, search=True),
    Features(summary=True, search=False),
    Features(summary=False, search=True),
    Features(summary=False, search=False),
)


async def _tool_names(features: Features = ALL_FEATURES, **overrides) -> set[str]:
    return {tool.name for tool in await make_mcp(features, **overrides).list_tools()}


async def _client_tool_names(mcp: FastMCP) -> set[str]:
    async with Client(mcp) as client:
        return {tool.name for tool in await client.list_tools()}


def _protocol_mcp(fake: FakeVss) -> FastMCP:
    """Build a server whose tools talk to ``fake``."""

    mcp = FastMCP(name="vss-test", instructions="test")
    register_all(mcp, Deps(client=fake.client(), settings=make_settings()))
    return mcp


def _assert_all_registered(text: str, registered: set[str], where: str) -> None:
    """Fail naming the offending source and token, not just the count."""

    unknown = sorted(set(_TOOL_TOKEN.findall(text)) - registered)
    assert not unknown, (
        f"{where} names {', '.join(unknown)}, which no deployment of this "
        f"shape registers. Either register the tool or stop naming it -- a "
        f"workflow whose step does not exist is answered by invention. "
        f"Registered here: {', '.join(sorted(registered))}."
    )


def _contains_network_refusal(caught: pytest.ExceptionInfo[BaseException]) -> bool:
    """anyio may wrap the network guard error in an ExceptionGroup."""

    if hasattr(caught.value, "exceptions"):
        return caught.group_contains(NetworkAccessError)
    return caught.errisinstance(NetworkAccessError)


# Tool surface


async def test_registers_the_expected_tools() -> None:
    assert await _tool_names() == EXPECTED_TOOLS


async def test_nothing_on_the_surface_destroys_anything() -> None:
    """The surface reads and creates; it never deletes."""

    names = await _tool_names()

    assert not {name for name in names if "delete" in name or "remove" in name}


async def test_annotations_tell_clients_which_tools_only_read() -> None:
    """Clients auto-approve read-only tools and confirm the rest."""

    for tool in await make_mcp(ALL_FEATURES).list_tools():
        hints = tool.annotations
        assert hints.read_only_hint is (tool.name not in WORK_TOOLS), tool.name
        assert hints.open_world_hint is False, tool.name
        assert not hints.destructive_hint, tool.name


@pytest.mark.parametrize(
    "retired",
    [
        "delete_tag",
        "get_tags",
        "create_video_search_embeddings",
        "get_all_videos",
        "run_search_query",
    ],
)
async def test_no_route_shaped_tools_survive_from_the_proxy(retired: str) -> None:
    """The old generated surface leaked implementation detail and a delete."""

    assert retired not in await _tool_names()


async def test_every_tool_documents_itself() -> None:
    """Descriptions are how a model picks a tool; an empty one is a defect."""

    for tool in await make_mcp(ALL_FEATURES).list_tools():
        assert (tool.description or "").strip(), f"{tool.name} has no description"


async def test_server_carries_usage_instructions() -> None:
    assert "indexed" in (make_mcp(ALL_FEATURES).instructions or "").lower()


@pytest.mark.parametrize("features", FEATURE_SHAPES, ids=lambda f: f.describe())
async def test_url_handling_instructions_reach_clients(features: Features) -> None:
    instructions = make_mcp(features).instructions or ""

    assert "exactly as returned" in instructions
    assert "MEDIA:" not in instructions


async def test_every_tool_declares_a_closed_output_schema() -> None:
    """Clients validate structuredContent against this; no free-form bags."""

    async with Client(make_mcp(ALL_FEATURES)) as client:
        tools = await client.list_tools()

    for tool in tools:
        schema = tool.output_schema or {}
        assert schema.get("type") == "object", tool.name
        assert schema.get("properties"), tool.name
        assert schema.get("required"), tool.name
        assert "x-fastmcp-wrap-result" not in schema, tool.name


# Feature gating


@pytest.mark.parametrize(
    ("features", "expected"),
    [
        pytest.param(
            Features(summary=True, search=False),
            LIBRARY_TOOLS | SUMMARY_TOOLS,
            id="summary-only",
        ),
        pytest.param(
            Features(summary=False, search=True),
            LIBRARY_TOOLS | SEARCH_TOOLS,
            id="search-only",
        ),
        pytest.param(
            Features(summary=False, search=False),
            LIBRARY_TOOLS,
            id="library-only",
        ),
    ],
)
async def test_feature_gated_deployments_offer_only_supported_tools(
    features: Features, expected: set[str]
) -> None:
    names = await _tool_names(features)

    assert names == expected
    if not features.search:
        assert "vss_search_video" not in names
        assert not names & SEARCH_TOOLS
    if not features.summary:
        assert "vss_summarize_video" not in names
        assert "vss_get_video_timeline" not in names


@pytest.mark.parametrize(
    ("summary", "search"),
    [(True, False), (False, True), (False, False)],
    ids=["summary-only", "search-only", "library-only"],
)
async def test_deployment_info_survives_every_shape(summary: bool, search: bool) -> None:
    """It is how a client finds out why a tool is missing."""

    names = await _tool_names(Features(summary=summary, search=search))

    assert "vss_get_deployment_info" in names


async def test_prompts_and_resources_follow_the_features_too() -> None:
    """A prompt naming an unregistered tool is a workflow that cannot run."""

    mcp = make_mcp(Features(summary=True, search=False))

    uris = {str(resource.uri) for resource in await mcp.list_resources()}
    prompts = {prompt.name for prompt in await mcp.list_prompts()}

    assert "vss://watches" not in uris
    assert "vss://search-patterns" not in uris
    assert "vss://videos" in uris
    assert prompts == {"summarize_video"}


async def test_instructions_do_not_describe_missing_capabilities() -> None:
    """Instructions are context; describing an absent tool wastes it."""

    summary_only = make_mcp(Features(summary=True, search=False)).instructions or ""

    assert "search_video" not in summary_only
    assert "summarize_video" in summary_only
    assert "Enabled in this deployment: summary." in summary_only


# Names read by clients


@pytest.mark.parametrize("features", FEATURE_SHAPES, ids=lambda f: f.describe())
async def test_no_prompt_names_an_unregistered_tool(features: Features) -> None:
    mcp = make_mcp(features)
    registered = {tool.name for tool in await mcp.list_tools()}

    for prompt in await mcp.list_prompts():
        rendered = await prompt.render(
            {argument.name: "PLACEHOLDER" for argument in prompt.arguments or []}
        )
        body = "\n".join(
            getattr(message.content, "text", "") for message in rendered.messages
        )
        _assert_all_registered(body, registered, f"Prompt {prompt.name!r}")


@pytest.mark.parametrize("features", FEATURE_SHAPES, ids=lambda f: f.describe())
async def test_no_resource_description_names_an_unregistered_tool(
    features: Features,
) -> None:
    """Descriptions are attached before the first message, unprompted."""

    mcp = make_mcp(features)
    registered = {tool.name for tool in await mcp.list_tools()}

    for resource in await mcp.list_resources():
        _assert_all_registered(
            f"{resource.name or ''} {resource.description or ''}",
            registered,
            f"Resource {str(resource.uri)!r}",
        )


@pytest.mark.parametrize("features", FEATURE_SHAPES, ids=lambda f: f.describe())
async def test_the_instructions_name_no_unregistered_tool(features: Features) -> None:
    mcp = make_mcp(features)
    registered = {tool.name for tool in await mcp.list_tools()}

    _assert_all_registered(mcp.instructions or "", registered, "The server instructions")


# Protocol round trips


async def test_tool_schemas_are_serializable() -> None:
    """Schemas are read over the protocol, as a real harness would."""

    async with Client(make_mcp(ALL_FEATURES)) as client:
        tools = await client.list_tools()

    assert tools
    for tool in tools:
        json.dumps(tool.input_schema)


async def test_search_round_trips_through_the_protocol() -> None:
    fake = FakeVss(
        videos=[make_video("v1", "clip.mp4")],
        states=[make_state("s1", "v1")],
        hits=[make_hit("v1", 0.93, 40)],
    )

    async with Client(_protocol_mcp(fake)) as client:
        result = await client.call_tool(
            "vss_search_video",
            {
                "query": "man in green pants",
                "start": "2026-08-04T00:00:00Z",
                "end": "2026-08-06T00:00:00Z",
            },
        )

    payload = result.structured_content
    assert payload["count"] == 1
    assert payload["results"][0]["video_id"] == "v1"
    assert payload["time_range"] == {
        "start": "2026-08-04T00:00:00.000Z",
        "end": "2026-08-06T00:00:00.000Z",
    }
    assert json.loads(result.content[0].text) == payload


async def test_summarize_round_trips_and_returns_a_timeline() -> None:
    fake = FakeVss(videos=[make_video("v1", "clip.mp4")])
    fake.state_on_create = make_state("s1", "v1", final="na")

    async with Client(_protocol_mcp(fake)) as client:
        result = await client.call_tool(
            "vss_summarize_video", {"video_id": "v1", "final_summary": False}
        )

    assert result.structured_content["completed"]
    assert len(result.structured_content["timeline"]) == 2


async def test_summarize_reports_progress_to_the_client() -> None:
    fake = FakeVss(videos=[make_video("v1", "clip.mp4")])
    fake.state_on_create = make_state("s1", "v1", final="complete")
    updates: list[tuple[float, float | None, str | None]] = []

    async def on_progress(progress, total, message) -> None:
        updates.append((progress, total, message))

    async with Client(_protocol_mcp(fake), progress_handler=on_progress) as client:
        await client.call_tool("vss_summarize_video", {"video_id": "v1"})

    assert updates
    progress, total, message = updates[-1]
    assert progress == total
    assert "Captioned" in message


async def test_search_returns_clips_as_resource_links() -> None:
    video_id = "5268a11c-c049-4c01-a614-b723f2cb3de2"
    hits = [make_hit(video_id, 0.9, i * 10) for i in range(25)]
    for index, hit in enumerate(hits):
        hit["videoPlaybackUrl"] = (
            f"/video-summary/{video_id}/source.mp4"
            f"?segment={index}&camera=East%20Gate#t=12.5"
        )
    fake = FakeVss(
        videos=[make_video(video_id, "East gate camera.mp4")],
        hits=hits,
    )

    async with Client(_protocol_mcp(fake)) as client:
        result = await client.call_tool(
            "vss_search_video", {"query": "person", "limit": 25}
        )

    text, *links = result.content
    payload = result.structured_content
    assert json.loads(text.text) == payload
    assert len(text.text.encode("utf-8")) <= MAX_RESULT_BYTES
    assert payload["count"] == len(payload["results"])
    assert payload["count"] + payload["omitted"] == 25
    assert [str(link.uri) for link in links] == [
        hit["url"] for hit in payload["results"]
    ]
    for link, hit in zip(links, payload["results"]):
        assert link.type == "resource_link"
        assert link.name == hit["video_name"]
        assert str(link.uri).endswith("East%20Gate#t=12.5")


async def test_backend_errors_surface_as_tool_errors() -> None:
    """A failure must reach the model as a message, not a stack trace."""

    fake = FakeVss(videos=[])

    async with Client(_protocol_mcp(fake)) as client:
        with pytest.raises(ToolError, match="No video with id"):
            await client.call_tool("vss_summarize_video", {"video_id": "missing"})


async def test_unexpected_failures_do_not_leak_internals() -> None:
    fake = FakeVss(videos=[None])

    async with Client(make_mcp(ALL_FEATURES, fake=fake)) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool("vss_list_videos", {})

    assert "NoneType" not in str(caught.value)


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("vss_list_videos", {}),
        ("vss_search_video", {"query": "forklift", "limit": 25}),
        ("vss_get_search", {"query_id": "q1", "limit": 25}),
        ("vss_list_searches", {"limit": 100}),
        ("vss_get_video_timeline", {"state_id": "s0"}),
        ("vss_resolve_video", {"hint": "clip"}),
    ],
)
async def test_every_tool_result_fits_the_byte_budget(name: str, args: dict) -> None:
    """The acceptance test that matters: no tool may flood a context window."""

    fake = FakeVss(
        videos=[make_video(f"v{i}", f"clip-{i}.mp4") for i in range(60)],
        states=[make_state(f"s{i}", f"v{i}", captions=40) for i in range(60)],
        hits=[make_hit("v1", 0.9, i * 10) for i in range(40)],
    )
    seed_searches(fake, 120)

    async with Client(_protocol_mcp(fake)) as client:
        result = await client.call_tool(name, args)

    size = len(json.dumps(result.structured_content).encode())
    assert size <= MAX_RESULT_BYTES, f"{name} -> {size}B"


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("vss_get_deployment_info", {}),
        ("vss_list_videos", {}),
        ("vss_list_tags", {}),
        ("vss_resolve_video", {"hint": "clip"}),
        ("vss_index_video", {"video_id": "v1"}),
        ("vss_index_video", {"video_id": "v2"}),
        ("vss_summarize_video", {"video_id": "v2"}),
        ("vss_get_video_timeline", {"video_id": "v1"}),
        ("vss_search_video", {"query": "forklift"}),
        ("vss_search_video", {"query": "forklift", "tags": ["Camera 9"]}),
        ("vss_get_search", {"query_id": "q1"}),
        ("vss_list_searches", {}),
        ("vss_refetch_search", {"query_id": "q1"}),
        ("vss_watch_search", {"query_id": "q1"}),
    ],
)
async def test_every_tool_result_matches_its_output_schema(name: str, args: dict) -> None:
    fake = FakeVss(
        videos=[
            make_video("v1", "clip.mp4", ["Camera 2"], indexed=True),
            make_video("v2", "other.mp4"),
        ],
        states=[make_state("s1", "v1")],
        hits=[make_hit("v1", 0.9, 10)],
    )
    fake.state_on_create = make_state("s2", "v2", final="complete")
    seed_searches(fake, 1)

    async with Client(_protocol_mcp(fake)) as client:
        schemas = {t.name: t.output_schema for t in await client.list_tools()}
        result = await client.call_tool_mcp(name, args)

    assert result.is_error is False
    jsonschema.validate(result.structured_content, schemas[name])
    assert json.loads(result.content[0].text) == result.structured_content


# Build path and hermeticity


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        pytest.param(
            {"summary": "FEATURE_ON", "search": "FEATURE_ON"},
            EXPECTED_TOOLS,
            id="all-features",
        ),
        pytest.param(
            {"summary": "FEATURE_ON", "search": "FEATURE_OFF"},
            LIBRARY_TOOLS | SUMMARY_TOOLS,
            id="summary-only",
        ),
        pytest.param(
            {"summary": "FEATURE_OFF", "search": "FEATURE_ON"},
            LIBRARY_TOOLS | SEARCH_TOOLS,
            id="search-only",
        ),
    ],
)
async def test_registers_what_the_deployment_reports(
    flags: dict[str, str], expected: set[str]
) -> None:
    fake = FakeVss(features=flags)
    mcp = await build_mcp(make_settings(), client=fake.client())

    assert await _client_tool_names(mcp) == expected
    assert fake.requests[0][:2] == ("GET", "/app/features")


async def test_tools_use_the_injected_client() -> None:
    fake = FakeVss(videos=[make_video("v1", "clip.mp4")])
    mcp = await build_mcp(make_settings(), client=fake.client())

    async with Client(mcp) as client:
        result = await client.call_tool("vss_list_videos", {})

    assert result.structured_content["videos"][0]["video_id"] == "v1"
    assert ("GET", "/videos", None) in fake.requests


async def test_an_unreachable_deployment_is_fatal() -> None:
    fake = FakeVss()
    fake.handle = lambda request: httpx.Response(503, json={"message": "down"})

    with pytest.raises(VssError):
        await build_mcp(make_settings(), client=fake.client())


def test_make_client_follows_settings() -> None:
    client = make_client(
        make_settings(vss_base_url="http://h:1/manager/", request_timeout_seconds=7.0)
    )

    assert client._base_url == "http://h:1/manager"
    assert client._timeout == 7.0


async def test_a_real_client_cannot_reach_the_network() -> None:
    client = make_client(make_settings(vss_base_url="http://127.0.0.1:9/manager"))

    with pytest.raises(BaseException) as caught:
        await client.get_features()

    assert _contains_network_refusal(caught), f"network was not blocked: {caught.value!r}"
