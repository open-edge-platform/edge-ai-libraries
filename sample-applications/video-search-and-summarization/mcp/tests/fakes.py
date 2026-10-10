# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared offline fixtures: settings, canned rows and a fake Pipeline Manager.

The fake answers the same routes with the same shapes as the real service,
including its awkward parts: ``200``-with-``null`` for a missing state, the
double-nested search envelope, and a summary status that stops at ``na`` when
the final rollup is skipped. Nothing here opens a network connection.
"""

from __future__ import annotations

import base64
import contextlib
import json
import tempfile
from pathlib import Path
from typing import Any

import httpx
from fastmcp import FastMCP

from src.clients import VssClient
from src.core.config import Settings
from src.features import ALL_FEATURES, Features
from src.server import create_mcp

class NetworkAccessError(RuntimeError):
    """Raised by the ``conftest`` guard when a test opens a real connection.

    Deliberately not an ``OSError``: httpx would turn that into a connection
    error, which tests of the "VSS is unreachable" path would accept.
    """


BASE_URL = "http://vss.test/manager"
DATASTORE_URL = "http://vss.test/datastore"


def make_settings(**overrides: Any) -> Settings:
    """Return settings with fast polling so tests do not sleep."""

    defaults = dict(
        vss_base_url=BASE_URL,
        vss_datastore_url=DATASTORE_URL,
        request_timeout_seconds=5.0,
        poll_interval_seconds=0.001,
        default_wait_seconds=1.0,
        index_strategy="auto",
        log_level="CRITICAL",
        mcp_host="127.0.0.1",
        mcp_port=8000,
        mcp_path="/mcp",
        stateless_http=True,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def make_features(
    *, summary: bool = True, search: bool = True, image_search_enabled: bool = False
) -> Features:
    """Return a feature set as the startup probe would have resolved it."""

    return Features(
        summary=summary, search=search, image_search_enabled=image_search_enabled
    )


def make_video(
    video_id: str,
    filename: str,
    tags: list[str] | None = None,
    *,
    indexed: bool | None = None,
) -> dict:
    """Return a VideoEntity whose `name` column holds multer's random hex.

    ``indexed`` sets the row's ``searchEmbeddings`` flag; ``None`` leaves it
    unreported, as the backend does today.
    """

    row = {
        "dbId": 1,
        "videoId": video_id,
        "name": "a3f9c1e88b2d4a7f9e0c1b2a3d4e5f60",
        "url": f"{video_id}/source.mp4",
        "tags": tags or [],
        "createdAt": "2026-08-01T10:00:00.000Z",
        "updatedAt": "2026-08-01T10:00:00.000Z",
        "dataStore": {
            "bucket": "vss",
            "objectName": video_id,
            "fileName": filename,
        },
    }
    if indexed is not None:
        row["searchEmbeddings"] = indexed
    return row


def make_state(
    state_id: str,
    video_id: str,
    *,
    captions: int = 2,
    in_progress: int = 0,
    final: str = "na",
    chunking: str = "complete",
) -> dict:
    """Return a UIState with `captions` completed frame summaries."""

    frames = []
    summaries = []
    for batch in range(captions):
        ids = [str(batch * 8 + n + 1) for n in range(8)]
        for offset, frame_id in enumerate(ids):
            frames.append(
                {
                    "chunkId": str(batch),
                    "frameId": frame_id,
                    "videoTimeStamp": batch * 8.0 + offset,
                    # Real states carry this, and it is what the detection
                    # metadata path is derived from.
                    "url": (
                        f"/video-summary/{state_id}/frame/"
                        f"chunk_{batch + 1}_frame_{offset + 1}.jpeg"
                    ),
                }
            )
        summaries.append(
            {
                "summary": f"Chunk {batch}: a person walks past a forklift.",
                "frames": ids,
                "frameKey": "#".join(ids),
                "startFrame": ids[0],
                "endFrame": ids[-1],
                "status": "complete",
                "stateId": state_id,
            }
        )

    return {
        "stateId": state_id,
        "videoId": video_id,
        "title": "clip.mp4",
        "summary": "Rolled up." if final == "complete" else "",
        "chunks": [],
        "frames": frames,
        "frameSummaries": summaries,
        "systemConfig": {"framePrompt": "Describe the frame.", "multiFrame": 8},
        "userInputs": {},
        "videoSummaryStatus": final,
        "frameSummaryStatus": {
            "complete": captions,
            "inProgress": in_progress,
            "na": 0,
            "ready": 0,
        },
        "chunkingStatus": chunking,
        "videoChunkingStatus": chunking,
    }


def make_hit(video_id: str, score: float, start: float) -> dict:
    """Return an aggregated search hit."""

    return {
        "id": None,
        "type": "Document",
        "page_content": "Video segment",
        "frame_scores": [["1.0s", "0.5"]] * 12,
        "metadata": {
            "video_id": video_id,
            "video_url": f"http://minio/{video_id}/source.mp4",
            "seek_timestamp": start + 2,
            "segment_start": start,
            "segment_end": start + 8,
            "relevance_score": score,
            "score_breakdown": {f"m{i}": i for i in range(12)},
            "video_metadata": {"file_name": "clip.mp4"},
            "rank": 1,
        },
    }


@contextlib.contextmanager
def make_temp_image() -> Any:
    """Yield the path to a minimal, valid one-pixel PNG for image-search tests."""

    # The smallest possible PNG: a 1x1 transparent pixel. Content-sniffing is
    # not part of `encode_image_file`, but a real image is used anyway so this
    # fixture stays honest about what it stands in for.
    one_pixel_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgAAIAAAUAAen63NgAAAAASUVORK5CYII="
    )
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        handle.write(one_pixel_png)
        path = handle.name
    try:
        yield path
    finally:
        Path(path).unlink(missing_ok=True)


class FakeVss:
    """An in-process stand-in for Pipeline Manager."""

    def __init__(
        self,
        *,
        videos: list[dict] | None = None,
        states: list[dict] | None = None,
        features: dict[str, str] | None = None,
        hits: list[dict] | None = None,
    ) -> None:
        self.videos = videos if videos is not None else []
        self.states = states if states is not None else []
        self.features = features or {
            "summary": "FEATURE_ON",
            "search": "FEATURE_ON",
        }
        self.hits = hits or []
        self.requests: list[tuple[str, str, Any]] = []
        #: State appended on the next POST /summary, letting a test simulate a
        #: pipeline that finishes (or does not) after being started.
        self.state_on_create: dict | None = None
        #: Persisted search queries by id, as ``POST /search`` stores them.
        self.searches: dict[str, dict] = {}
        #: Status a new or re-run search query ends in; ``running`` simulates
        #: one still being computed, ``error`` one that failed.
        self.search_status = "idle"
        self.search_error: str | None = None
        #: ``/app/config`` overrides, e.g. audio models or batch size.
        self.app_config: dict[str, Any] = {}

    def transport(self) -> httpx.MockTransport:
        """Return a transport routing httpx calls into :meth:`handle`."""

        return httpx.MockTransport(self.handle)

    def client(self, **kwargs: Any) -> VssClient:
        """Return a VssClient wired to this fake."""

        return VssClient(
            BASE_URL,
            client=httpx.AsyncClient(base_url=BASE_URL, transport=self.transport()),
            **kwargs,
        )

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Route a request to a canned response."""

        path = request.url.path.replace("/manager", "", 1) or "/"
        body: Any = None
        if request.content:
            try:
                body = json.loads(request.content)
            except ValueError:
                body = request.content[:64]
        self.requests.append((request.method, path, body))

        if path == "/app/features":
            return httpx.Response(200, json=self.features)

        if path == "/app/config":
            config = {
                "multiFrame": 8,
                "frameOverlap": 0,
                "framePrompt": "Describe the frame.",
                "meta": {
                    "evamPipelines": [
                        {"name": "Object Detection", "value": "object_detection"},
                        {"name": "Basic Ingestion", "value": "video_ingestion"},
                    ],
                    "audioModels": [],
                },
            }
            config.update(self.app_config)
            return httpx.Response(200, json=config)

        if path == "/videos" and request.method == "GET":
            return httpx.Response(200, json={"videos": self.videos})

        if path.startswith("/videos/search-embeddings/"):
            return httpx.Response(201, json={"status": "success", "message": "ok"})

        if path.startswith("/videos/") and request.method == "GET":
            video_id = path.rsplit("/", 1)[-1]
            match = next(
                (v for v in self.videos if v["videoId"] == video_id), None
            )
            if not match:
                return httpx.Response(404, json={"message": "Video not found"})
            return httpx.Response(200, json={"video": match})

        if path == "/summary" and request.method == "POST":
            if self.state_on_create is not None:
                self.states.append(self.state_on_create)
                return httpx.Response(
                    201,
                    json={"summaryPipelineId": self.state_on_create["stateId"]},
                )
            return httpx.Response(201, json={"summaryPipelineId": "state-pending"})

        if path == "/summary/ui":
            return httpx.Response(200, json=self.states)

        if path.startswith("/summary/") and request.method == "GET":
            state_id = path.rsplit("/", 1)[-1]
            match = next(
                (s for s in self.states if s["stateId"] == state_id), None
            )
            # Pipeline Manager answers 200 with a null body for unknown ids.
            return httpx.Response(200, json=match)

        if path.startswith("/search"):
            return self._handle_search(request.method, path, body)

        return httpx.Response(404, json={"message": f"no route {path}"})

    def _handle_search(self, method: str, path: str, body: Any) -> httpx.Response:
        """``/search`` routes: persisted queries, as in ``SearchController``."""

        if path == "/search" and method == "POST":
            body = body or {}
            stored = {
                "queryId": f"q{len(self.searches) + 1}",
                "query": body.get("query") or "",
                "image": body.get("image") or body.get("imageUrl"),
                "watch": False,
                "tags": [t for t in (body.get("tags") or "").split(",") if t],
                "timeFilter": body.get("timeFilter"),
                "queryStatus": "running",
                "results": [],
                "createdAt": f"2026-01-01T00:00:{len(self.searches):02d}Z",
                "updatedAt": "2026-01-01T00:00:00Z",
            }
            response = dict(stored)
            self.searches[stored["queryId"]] = _search_result(self, stored)
            return httpx.Response(201, json=response)

        if path == "/search" and method == "GET":
            return httpx.Response(200, json=list(self.searches.values()))

        parts = path.strip("/").split("/")
        stored = self.searches.get(parts[1]) if len(parts) > 1 else None
        if len(parts) == 2 and method == "GET":
            # Like the real service: 200 with an empty body for an unknown id.
            return httpx.Response(200, json=stored)
        if stored is None:
            return httpx.Response(500, json={"message": "Internal server error"})
        if parts[2:] == ["refetch"] and method == "POST":
            if (body or {}).get("timeFilter"):
                stored["timeFilter"] = body["timeFilter"]
            return httpx.Response(201, json=_search_result(self, stored))
        if parts[2:] == ["watch"] and method == "PATCH":
            stored["watch"] = bool((body or {}).get("watch"))
            return httpx.Response(200)
        return httpx.Response(404, json={"message": f"no route {path}"})


def _search_result(fake: "FakeVss", stored: dict) -> dict:
    """Finish a persisted query the way Pipeline Manager's RUN_QUERY does."""

    stored["queryStatus"] = fake.search_status
    stored["results"] = list(fake.hits) if fake.search_status == "idle" else []
    stored["errorMessage"] = (
        fake.search_error if fake.search_status == "error" else None
    )
    return stored


def seed_searches(fake: "FakeVss", count: int) -> None:
    """Store ``count`` finished text queries, ``q1`` first, with ``fake.hits``."""

    for index in range(1, count + 1):
        fake.searches[f"q{index}"] = {
            "queryId": f"q{index}",
            "query": f"forklift near dock {index}",
            "image": None,
            "watch": False,
            "tags": ["Camera 2"],
            "timeFilter": None,
            "queryStatus": "idle",
            "results": list(fake.hits),
            "createdAt": f"2026-01-01T00:{index // 60:02d}:{index % 60:02d}Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        }


def make_mcp(
    features: Features = ALL_FEATURES,
    *,
    fake: FakeVss | None = None,
    **settings_overrides: Any,
) -> FastMCP:
    """Build the full server wired to ``fake`` (an empty one by default)."""

    return create_mcp(
        make_settings(**settings_overrides),
        features,
        client=(fake or FakeVss()).client(),
    )
