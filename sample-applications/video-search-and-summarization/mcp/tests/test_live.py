# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for live cameras: stream tools, live hits, and tracking with
vss_watch_search."""

from __future__ import annotations

import asyncio
import time

import pytest
from fastmcp import Client

from src.clients import VssError
from src.features import ALL_FEATURES, Features
from src.projections import slim_search_hit
from src.tools import Deps
from src.tools.discovery import get_deployment_info, list_tags
from src.tools.search import decode_cursor, encode_cursor, search_video, watch_search
from src.tools.streams import add_streams, list_streams, remove_streams, update_stream
from tests.fakes import (
    DATASTORE_URL,
    FakeVss,
    make_live_hit,
    make_mcp,
    make_settings,
    make_stream,
    make_video,
)

pytestmark = pytest.mark.anyio

EPOCH = 1791446440  # 2026-10-08T08:00:40Z


def _deps(fake: FakeVss, features: Features = ALL_FEATURES) -> Deps:
    return Deps(
        client=fake.client(),
        settings=make_settings(default_wait_seconds=0.05, poll_interval_seconds=0.01),
        features=features,
    )


def _posted(fake: FakeVss, method: str, path: str) -> list:
    return [body for m, p, body in fake.requests if m == method and p == path]


# Live hits


def test_live_hit_carries_its_camera_tag() -> None:
    """Live footage is indexed with the stream's tags; the hit must keep them,
    or agents only see an opaque stream id."""

    raw = make_live_hit("cc63056f", 1.0, EPOCH)
    raw["metadata"]["tags"] = "camera_1"
    raw["metadata"]["video_metadata"] = {"tags": ["camera_1"]}
    hit = slim_search_hit(raw, DATASTORE_URL)
    assert hit["tags"] == ["camera_1"]
    assert hit["stream_id"] == "cc63056f"


def test_a_live_hit_says_where_and_when_it_happened() -> None:
    hit = slim_search_hit(make_live_hit("cam1", 1.0, EPOCH), DATASTORE_URL)

    assert hit["source"] == "live"
    assert hit["stream_id"] == "cam1"
    assert hit["observed_at"] == "2026-10-08T08:00:44.500Z"
    assert hit["raw_score"] == 0.36
    assert hit["url"] == f"{DATASTORE_URL}/live-streams/cam1/segments/{EPOCH}.mp4"
    assert hit["frame"]["crop_bbox"] == "395,452,542,894"
    assert hit["frame"]["media_path"] == f"segments/{EPOCH}.mp4"


# Streams


async def test_listing_streams_never_shows_credentials() -> None:
    url = "rtsp://admin:secret@cam.local/live"
    fake = FakeVss(streams=[make_stream("s1", url, url=url)])

    result = await list_streams(_deps(fake))

    (stream,) = result["streams"]
    assert "secret" not in str(result)
    assert stream["stream_id"] == "s1"
    assert stream["state"] == "running"


async def test_adding_one_camera_posts_it_alone() -> None:
    fake = FakeVss()

    result = await add_streams(
        _deps(fake),
        [{"stream_url": "rtsp://cam.local/a", "name": "Dock", "tags": ["dock"]}],
    )

    (body,) = _posted(fake, "POST", "/streams")
    assert body == {"stream_url": "rtsp://cam.local/a", "stream_name": "Dock", "tags": ["dock"]}
    assert result["accepted"] == 1
    assert result["items"][0]["stream_id"] == "s1"


async def test_adding_several_cameras_reports_each() -> None:
    fake = FakeVss()

    result = await add_streams(
        _deps(fake),
        [{"stream_url": "rtsp://cam.local/a"}, {"stream_url": "rtsp://bad.local/b"}],
    )

    assert _posted(fake, "POST", "/streams/batch")
    assert (result["accepted"], result["rejected"]) == (1, 1)
    assert [item["accepted"] for item in result["items"]] == [True, False]


@pytest.mark.parametrize(
    "spec",
    [
        {"stream_url": "http://cam.local/a"},
        {"stream_url": "rtsp://cam.local/a", "frame_interval": 0},
        {"stream_url": "rtsp://cam.local/a", "sensor_id": "-bad"},
    ],
)
async def test_bad_camera_specs_are_refused_before_calling_vss(spec: dict) -> None:
    fake = FakeVss()

    with pytest.raises(VssError):
        await add_streams(_deps(fake), [spec])

    assert not _posted(fake, "POST", "/streams")


async def test_pausing_a_camera_patches_only_its_state() -> None:
    fake = FakeVss(streams=[make_stream("s1")])

    stream = await update_stream(_deps(fake), "s1", state="paused")

    assert _posted(fake, "PATCH", "/streams/s1") == [{"state": "paused"}]
    assert stream["state"] == "paused"


async def test_updating_an_unknown_camera_points_at_the_list() -> None:
    fake = FakeVss()

    with pytest.raises(VssError, match="No live stream with id 'nope'"):
        await update_stream(_deps(fake), "nope", state="paused")


async def test_an_update_must_change_something() -> None:
    fake = FakeVss(streams=[make_stream("s1")])

    with pytest.raises(VssError):
        await update_stream(_deps(fake), "s1")


async def test_removing_a_camera_never_purges_its_footage() -> None:
    fake = FakeVss(streams=[make_stream("s1")])

    result = await remove_streams(_deps(fake), ["s1"])

    assert result["removed"] == 1
    (request,) = [r for r in fake.requests if r[0] == "DELETE"]
    assert request[1:] == ("/streams", {"stream_ids": ["s1"]})
    assert not fake.streams
    assert not fake.purged


async def test_removing_several_cameras_reports_each_one() -> None:
    fake = FakeVss(streams=[make_stream("s1"), make_stream("s2")])

    result = await remove_streams(_deps(fake), ["s1", "nope", "s2"])

    assert result["removed"] == 2
    assert [item["removed"] for item in result["items"]] == [True, False, True]
    assert "No live stream" in result["items"][1]["message"]
    assert len([r for r in fake.requests if r[0] == "DELETE"]) == 1


async def test_removing_one_unknown_camera_is_an_error() -> None:
    fake = FakeVss(streams=[make_stream("s1")])

    with pytest.raises(VssError, match="Use vss_list_streams"):
        await remove_streams(_deps(fake), ["nope"])


@pytest.mark.parametrize(
    "bad_id",
    [
        "s2?purge_media=true&purge_embeddings=true",
        "s2/../../search/q1",
        "s2%2F..%2F..%2Fsearch%2Fq1",
        "..",
        "s2#x",
    ],
)
async def test_a_stream_id_cannot_reach_another_route_or_query(bad_id: str) -> None:
    fake = FakeVss(streams=[make_stream("s2")])

    with pytest.raises(VssError, match="not a valid VSS id"):
        await update_stream(_deps(fake), bad_id, state="paused")

    assert not fake.requests
    assert fake.streams[0]["state"] == "running"


async def test_stream_tools_are_offered_with_frame_embeddings_only() -> None:
    async with Client(make_mcp(Features(summary=True, search=True))) as client:
        unified = {tool.name for tool in await client.list_tools()}
    async with Client(make_mcp(ALL_FEATURES)) as client:
        full = {tool.name for tool in await client.list_tools()}

    assert "vss_add_stream" not in unified
    assert "vss_add_stream" in full


# Search


async def test_search_can_keep_only_some_cameras() -> None:
    fake = FakeVss(
        streams=[make_stream("cam1", "Lobby"), make_stream("cam2", "Dock")],
        hits=[make_live_hit("cam1", 1.0, EPOCH), make_live_hit("cam2", 0.9, EPOCH)],
    )

    result = await search_video(_deps(fake), "person", stream_ids=["cam2"])

    assert [hit["video_id"] for hit in result["results"]] == ["cam2"]
    assert result["results"][0]["video_name"] == "Dock"
    assert result["stream_ids"] == ["cam2"]


async def test_deployment_info_reports_live_and_watch_settings() -> None:
    fake = FakeVss()

    info = await get_deployment_info(_deps(fake))

    assert info["live_streams_enabled"] is True
    assert info["watch_refresh"] == {"enabled": True, "interval_seconds": 10.0}


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({"enabled": False, "intervalMs": 30000}, {"enabled": False, "interval_seconds": 30.0}),
        ({"enabled": True, "intervalMs": 5000}, {"enabled": True, "interval_seconds": 5.0}),
    ],
)
async def test_deployment_info_and_watch_agree_on_the_refresh_config(
    config: dict, expected: dict
) -> None:
    fake = FakeVss(hits=[make_live_hit("cam1", 1.0, EPOCH)])
    fake.refresh_config = config
    deps = _deps(fake)

    info = await get_deployment_info(deps)
    watched = await watch_search(deps, query="person")

    assert info["watch_refresh"] == expected
    # With auto-refresh on, the next poll waits by itself.
    assert watched["poll_after_seconds"] == (
        0.0 if expected["enabled"] else expected["interval_seconds"]
    )


async def test_deployment_info_omits_an_unreadable_refresh_config() -> None:
    fake = FakeVss()
    fake.refresh_config = None

    info = await get_deployment_info(_deps(fake))

    assert "watch_refresh" not in info


# Tracking


async def test_starting_a_track_watches_a_rolling_window() -> None:
    fake = FakeVss(
        streams=[make_stream("cam1")], hits=[make_live_hit("cam1", 1.0, EPOCH)]
    )

    result = await watch_search(
        _deps(fake), query="man in red jacket", window_minutes=5, duration_minutes=10
    )

    (body,) = _posted(fake, "POST", "/search")
    assert body["timeFilter"] == {"value": 5, "unit": "minutes", "source": "relative"}
    assert _posted(fake, "PATCH", "/search/q1/watch") == [{"watch": True}]
    assert result["watch"] is True and result["expired"] is False
    assert result["window_minutes"] == 5
    assert result["new_count"] == 1
    assert result["last_seen"][0]["video_id"] == "cam1"
    assert result["poll_after_seconds"] == 0.0
    assert 590 <= result["remaining_seconds"] <= 600
    newest, expires = decode_cursor(result["next_cursor"])
    assert newest == pytest.approx(EPOCH + 4.5)
    assert expires == pytest.approx(time.time() + 600, abs=5)


async def test_polling_returns_only_new_sightings() -> None:
    fake = FakeVss(
        streams=[make_stream("cam1"), make_stream("cam2")],
        hits=[make_live_hit("cam1", 1.0, EPOCH)],
    )
    deps = _deps(fake)
    started = await watch_search(deps, query="person")
    fake.searches["q1"]["results"] = [
        make_live_hit("cam1", 1.0, EPOCH),
        make_live_hit("cam2", 0.9, EPOCH + 30),
    ]

    polled = await watch_search(deps, "q1", cursor=started["next_cursor"])

    assert [hit["video_id"] for hit in polled["sightings"]] == ["cam2"]
    assert [seen["video_id"] for seen in polled["last_seen"]] == ["cam2", "cam1"]
    assert not _posted(fake, "POST", "/search/q1/refetch")


async def test_a_track_stops_itself_once_its_time_is_up() -> None:
    fake = FakeVss(hits=[make_live_hit("cam1", 1.0, EPOCH)])
    deps = _deps(fake)
    await watch_search(deps, query="person")

    result = await watch_search(
        deps, "q1", cursor=encode_cursor(EPOCH, time.time() - 1)
    )

    assert result["expired"] is True
    assert result["watch"] is False
    assert result["next_cursor"] is None
    assert _posted(fake, "PATCH", "/search/q1/watch")[-1] == {"watch": False}
    assert "q1" in fake.searches


async def test_stopping_keeps_the_search() -> None:
    fake = FakeVss()
    deps = _deps(fake)
    await watch_search(deps, query="person")

    result = await watch_search(deps, "q1", watch=False)

    assert result["watch"] is False
    assert fake.searches["q1"]["watch"] is False


async def test_tracking_from_a_hit_searches_by_its_crop() -> None:
    fake = FakeVss(streams=[make_stream("cam1")])
    frame = slim_search_hit(make_live_hit("cam1", 1.0, EPOCH), DATASTORE_URL)["frame"]

    result = await watch_search(_deps(fake), from_hit=frame)

    (params,) = fake.frame_params
    assert params["variant"] == "crop"
    assert params["crop_bbox"] == "395,452,542,894"
    (body,) = _posted(fake, "POST", "/search")
    assert body["image"].startswith("data:image/jpeg;base64,")
    assert result["image_search"] is True


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"query": "a", "image": "b"},
        {"query": "a", "window_minutes": 0},
        {"query": "a", "duration_minutes": -1},
        {"query_id": "q1", "query": "a"},
        {"query_id": "q1", "cursor": "nonsense"},
        {"query_id": "q1", "wait_seconds": -1},
        {"query_id": "q1", "wait_seconds": 1000},
    ],
)
async def test_bad_track_arguments_are_refused(kwargs: dict) -> None:
    fake = FakeVss()
    fake.searches["q1"] = {"queryId": "q1", "watch": False, "results": []}

    with pytest.raises(VssError):
        await watch_search(_deps(fake), **kwargs)


async def test_without_auto_refresh_a_poll_says_so_without_waiting() -> None:
    fake = FakeVss(hits=[make_live_hit("cam1", 1.0, EPOCH)])
    fake.refresh_config = {"enabled": False, "intervalMs": 10000}
    deps = _deps(fake)
    started = await watch_search(deps, query="person")

    began = time.monotonic()
    result = await watch_search(deps, "q1", cursor=started["next_cursor"], wait_seconds=5)

    assert time.monotonic() - began < 0.05
    assert not _posted(fake, "POST", "/search/q1/refetch")
    assert "auto-refresh is disabled" in result["error"]
    assert result["poll_after_seconds"] == 10.0


async def test_a_poll_waits_for_a_new_sighting() -> None:
    fake = FakeVss(
        streams=[make_stream("cam1"), make_stream("cam2")],
        hits=[make_live_hit("cam1", 1.0, EPOCH)],
    )
    deps = Deps(
        client=fake.client(),
        settings=make_settings(default_wait_seconds=5, poll_interval_seconds=0.01),
        features=ALL_FEATURES,
    )
    started = await watch_search(deps, query="person")

    async def refresh_later() -> None:
        await asyncio.sleep(0.05)
        fake.searches["q1"]["results"] = [
            make_live_hit("cam1", 1.0, EPOCH),
            make_live_hit("cam2", 0.9, EPOCH + 30),
        ]

    refresher = asyncio.create_task(refresh_later())
    began = time.monotonic()
    polled = await watch_search(deps, "q1", cursor=started["next_cursor"])
    await refresher

    assert 0.05 <= time.monotonic() - began < 2
    assert [hit["video_id"] for hit in polled["sightings"]] == ["cam2"]


async def test_a_quiet_poll_returns_after_its_wait() -> None:
    fake = FakeVss(hits=[make_live_hit("cam1", 1.0, EPOCH)])
    deps = _deps(fake)
    started = await watch_search(deps, query="person")

    began = time.monotonic()
    polled = await watch_search(deps, "q1", cursor=started["next_cursor"])

    assert time.monotonic() - began >= 0.05
    assert polled["new_count"] == 0 and polled["watch"] is True
    assert [seen["video_id"] for seen in polled["last_seen"]] == ["cam1"]


async def test_a_poll_never_waits_past_the_expiry() -> None:
    fake = FakeVss(hits=[make_live_hit("cam1", 1.0, EPOCH)])
    deps = Deps(
        client=fake.client(),
        settings=make_settings(default_wait_seconds=5, poll_interval_seconds=0.01),
        features=ALL_FEATURES,
    )
    await watch_search(deps, query="person")

    began = time.monotonic()
    polled = await watch_search(
        deps, "q1", cursor=encode_cursor(EPOCH + 10, time.time() + 0.1)
    )

    assert time.monotonic() - began < 1
    assert polled["new_count"] == 0


async def test_uploaded_videos_count_as_sightings_too() -> None:
    """A newly indexed video with no wall-clock time still shows on start."""

    from tests.fakes import make_hit

    fake = FakeVss(videos=[make_video("v1", "a.mp4")], hits=[make_hit("v1", 0.9, 0)])

    result = await watch_search(_deps(fake), query="person")

    assert [hit["video_id"] for hit in result["sightings"]] == ["v1"]


# Tags


async def test_list_tags_includes_live_camera_tags() -> None:
    """A tag only a live camera carries is still searchable, so it is listed."""

    fake = FakeVss(
        videos=[make_video("v1", "a.mp4", tags=["lobby"])],
        streams=[
            make_stream("s1", tags=["dock"]),
            make_stream("s2", tags=["dock", "lobby"]),
        ],
    )

    listed = await list_tags(_deps(fake))

    assert listed["tags"] == ["dock", "lobby"]


async def test_search_accepts_a_tag_only_a_live_camera_carries() -> None:
    fake = FakeVss(streams=[make_stream("s1", tags=["dock"])])

    result = await search_video(_deps(fake), "a forklift", tags=["Dock"])

    assert result["tags"] == ["dock"]
    assert "unknown_tags" not in result
