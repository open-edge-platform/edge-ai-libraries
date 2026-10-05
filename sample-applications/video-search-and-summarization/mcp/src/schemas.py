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


class TagCount(TypedDict):
    tag: str
    videos: int


class TagList(Capped):
    """Tags in use, most used first."""

    count: int
    tags: list[TagCount]


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


class DeploymentInfo(TypedDict):
    summary_enabled: bool
    search_enabled: bool
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


class Timeline(Capped):
    """Chunk captions of a summary run, ordered by start time."""

    video_id: str | None
    state_id: str | None
    title: str | None
    completed: bool
    captioned: int
    total_chunks: int
    timeline: list[TimelineEntry]
    summary: NotRequired[str]
    audio_summary: NotRequired[str]


class Hit(TypedDict):
    """A matching moment; times are seconds into the video at url."""

    video_id: str
    video_name: NotRequired[str]
    start_s: NotRequired[float]
    end_s: NotRequired[float]
    seek_s: NotRequired[float]
    score: NotRequired[float]
    url: NotRequired[str]


class TimeRange(TypedDict):
    start: str
    end: str


class SearchResult(Capped):
    """Hits best first. With only unknown_tags, nothing was searched.

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
    time_range: NotRequired[TimeRange]


class StoredSearch(SearchResult):
    """A persisted search query and its latest results."""

    query: NotRequired[str]
    image_search: NotRequired[bool]
    watch: NotRequired[bool]
    created_at: NotRequired[str]
    updated_at: NotRequired[str]


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
    error: NotRequired[str]


class SearchList(Capped):
    """Persisted search queries, newest first; total counts all of them."""

    total: int
    count: int
    searches: list[SearchSummary]
