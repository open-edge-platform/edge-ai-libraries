# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tool result types."""

from __future__ import annotations

from typing import Literal

from typing_extensions import NotRequired, TypedDict


class Capped(TypedDict):
    """A result whose list was trimmed to fit the response size budget."""

    truncated: bool
    omitted: int


class Video(TypedDict):
    """A video. indexed is null when the backend does not report it, and
    absent entirely in summary-only deployments, which have no search index."""

    video_id: str
    name: str | None
    tags: list[str]
    created_at: str | None
    indexed: NotRequired[bool | None]


class VideoList(Capped):
    """Videos newest first; total counts every match before limit."""

    total: int
    videos: list[Video]


class TagList(Capped):
    """Tags on videos and live cameras, sorted."""

    count: int
    tags: list[str]


class Candidate(Video):
    match: NotRequired[Literal["exact_id", "exact_name", "substring", "fuzzy"]]


class Resolution(Capped):
    """Candidates best first; unambiguous is true for exactly one."""

    unambiguous: bool
    candidates: list[Candidate]


class Upload(TypedDict):
    """Where to POST a video file; the response carries its videoId."""

    url: str
    method: Literal["POST"]
    content_type: Literal["multipart/form-data"]
    file_field: str
    tags_field: str


class WatchRefresh(TypedDict):
    enabled: bool
    interval_seconds: float


class DeploymentInfo(TypedDict):
    """live_streams_enabled: RTSP cameras can be added (search/dual mode).
    watch_refresh: how often VSS re-runs watched searches; absent when
    search is off or the setting could not be read."""

    summary_enabled: bool
    search_enabled: bool
    live_streams_enabled: NotRequired[bool]
    watch_refresh: NotRequired[WatchRefresh]
    videos_total: int
    videos_indexed: NotRequired[int]
    videos_index_unknown: NotRequired[int]
    server_time_utc: str
    upload: Upload


class IndexResult(TypedDict):
    """indexed is false while a summary-based index is still running."""

    video_id: str
    indexed: bool
    strategy: Literal["summary", "embeddings"] | None
    state_id: str | None


class TimelineEntry(TypedDict):
    start_s: float | None
    end_s: float | None
    caption: str


class _SummaryRun(TypedDict):
    video_id: str | None
    state_id: str | None
    title: str | None
    completed: bool
    captioned: int
    total_chunks: int
    summary: NotRequired[str]
    audio_summary: NotRequired[str]


class VideoSummary(_SummaryRun):
    """A summary run. summary is the final summary, in full, once completed;
    timeline is present only when no final summary was requested."""

    timeline: NotRequired[list[TimelineEntry]]


class Timeline(_SummaryRun):
    """Chunk captions of a summary run, in full, ordered by start time."""

    timeline: list[TimelineEntry]


class FrameLocator(TypedDict):
    """Where the hit's peak-scoring frame is; pass these fields unchanged to
    vss_get_media_frame. crop_bbox is present when the match was a detected
    object."""

    video_id: str
    timestamp: float
    bucket_name: NotRequired[str]
    media_path: NotRequired[str]
    crop_bbox: NotRequired[str]


class Hit(TypedDict):
    """A matching moment; times are seconds into the video at url. label is
    the detected object that matched, when the match was one.

    source is "live" for a camera hit, whose stream_id names the camera;
    url then plays the 10 s segment holding it. observed_at (ISO-8601 UTC)
    places the matched frame on a timeline: time_source "live" means it is
    the camera's capture time, "upload" means the video's upload time plus
    the frame's offset (not when the footage was recorded). score is relative to the
    best hit of the same search (the best is always 1.0); raw_score is the
    absolute similarity, comparable across searches and polls."""

    video_id: str
    video_name: NotRequired[str]
    source: NotRequired[Literal["live", "video"]]
    stream_id: NotRequired[str]
    observed_at: NotRequired[str]
    time_source: NotRequired[Literal["live", "upload"]]
    start_s: NotRequired[float]
    end_s: NotRequired[float]
    seek_s: NotRequired[float]
    score: NotRequired[float]
    raw_score: NotRequired[float]
    url: NotRequired[str]
    frame: NotRequired[FrameLocator]
    label: NotRequired[str]


class MediaFrame(TypedDict):
    """Metadata of a frame returned by vss_get_media_frame. The pixels are
    in the result's image content; url serves the same JPEG over HTTP, for
    a user's browser or a client that does not pass images to the model."""

    video_id: str
    requested_timestamp: float
    actual_timestamp: NotRequired[float | None]
    media_path: NotRequired[str | None]
    variant: str
    cropped: bool
    width: int
    height: int
    mime: str
    url: str


class TimeRange(TypedDict):
    start: str
    end: str


class SearchResult(TypedDict):
    """Hits best first, or by observed_at when sort is "newest"/"oldest".
    With only unknown_tags, nothing was searched.

    query_id names the query VSS persisted; status is "running" while its
    results are still being computed, "idle" once done and "error" if it
    failed."""

    count: int
    results: list[Hit]
    query_id: NotRequired[str]
    status: NotRequired[Literal["idle", "running", "error"]]
    error: NotRequired[str]
    tags: NotRequired[list[str]]
    unknown_tags: NotRequired[list[str]]
    available_tags: NotRequired[list[str]]
    stream_ids: NotRequired[list[str]]
    time_range: NotRequired[TimeRange]
    min_peak_score: NotRequired[float]
    sort: NotRequired[Literal["newest", "oldest"]]


class StoredSearch(SearchResult):
    """A persisted search query and its latest results. last_refreshed is
    when VSS last re-ran it automatically, for a watched search."""

    query: NotRequired[str]
    image_search: NotRequired[bool]
    watch: NotRequired[bool]
    created_at: NotRequired[str]
    updated_at: NotRequired[str]
    last_refreshed: NotRequired[str]


class SearchSummary(TypedDict):
    """One persisted search query, without its hits."""

    query_id: str
    query: NotRequired[str]
    image_search: bool
    tags: list[str]
    status: str | None
    watch: bool
    result_count: int
    created_at: NotRequired[str]
    updated_at: NotRequired[str]
    last_refreshed: NotRequired[str]
    error: NotRequired[str]


class SearchList(Capped):
    """Persisted search queries, newest first; total counts all of them."""

    total: int
    count: int
    searches: list[SearchSummary]


class StreamStats(TypedDict):
    frames_processed: NotRequired[int]
    embeddings_created: NotRequired[int]
    segments_stored: NotRequired[int]
    reconnect_count: NotRequired[int]
    uptime_s: NotRequired[float]
    last_frame_at: NotRequired[str]


class Stream(TypedDict):
    """A live RTSP camera. url never carries credentials. state is one of
    pending, starting, running, paused, reconnecting, error, stopped."""

    stream_id: str
    name: NotRequired[str]
    url: NotRequired[str]
    state: NotRequired[str]
    description: NotRequired[str]
    sensor_id: NotRequired[str]
    tags: list[str]
    frame_interval: NotRequired[int]
    object_detection: NotRequired[bool]
    stats: StreamStats
    error: NotRequired[str]
    created_at: NotRequired[str]


class StreamList(Capped):
    """Registered cameras; total counts every match."""

    total: int
    count: int
    streams: list[Stream]


class StreamAddItem(TypedDict):
    """The outcome for one requested camera."""

    stream_url: str
    accepted: bool
    stream_id: NotRequired[str]
    message: NotRequired[str]


class StreamAddResult(TypedDict):
    """Cameras registered; each one starts ingesting in the background."""

    accepted: int
    rejected: int
    items: list[StreamAddItem]
    streams: list[Stream]


class StreamRemoveItem(TypedDict):
    stream_id: str
    removed: bool
    message: NotRequired[str]


class StreamRemoveResult(TypedDict):
    """Cameras stopped and deregistered. Their recorded segments and
    embeddings are kept, so past hits stay searchable and playable."""

    removed: int
    items: list[StreamRemoveItem]


class LastSeen(TypedDict):
    """The newest sighting on one camera or video."""

    video_id: str
    name: NotRequired[str]
    source: Literal["live", "video"]
    observed_at: NotRequired[str]
    raw_score: NotRequired[float]
    url: NotRequired[str]


class WatchResult(TypedDict):
    """A watched search, as a tracker.

    sightings are the hits new since the cursor passed in (all current hits
    when none was), newest first. Pass next_cursor back unchanged on the
    next call. expired is true once duration_minutes has passed; the search
    is then no longer watched."""

    query_id: str
    watch: bool
    status: str | None
    query: NotRequired[str]
    image_search: bool
    window_minutes: NotRequired[int]
    min_peak_score: NotRequired[float]
    stream_ids: NotRequired[list[str]]
    last_refreshed: NotRequired[str]
    server_time_utc: str
    expires_at: NotRequired[str]
    remaining_seconds: NotRequired[int]
    expired: bool
    error: NotRequired[str]
    new_count: int
    sightings: list[Hit]
    last_seen: list[LastSeen]
    next_cursor: str | None
    poll_after_seconds: float
