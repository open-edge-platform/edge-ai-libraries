# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared offline fixtures: settings, canned rows and a fake Pipeline Manager.

The fake answers the same routes with the same shapes as the real service,
including its awkward parts: ``200`` with an empty body for a missing state or
search, a silent no-op when watching an unknown search, and a summary status
that stops at ``na`` when the final rollup is skipped. It rejects what the real
service's validation rejects, so a test cannot pass on a request VSS would
refuse. Nothing here opens a network connection.
"""

from __future__ import annotations

import json
import re
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

#: ``GET /frames``'s crop box, as ``FrameQueryDto`` validates it.
_CROP_BBOX_RE = re.compile(r"^\d+,\d+,\d+,\d+$")

#: ``user:pass@`` in a stream URL; dataprep returns ``***@`` in its place.
_CREDENTIALS_RE = re.compile(r"(?i)\b(rtsps?://)[^/@\s]+@")

#: Fields ``PATCH /streams/{id}`` accepts (``LiveStreamUpdateDto``); the
#: controller's ``forbidNonWhitelisted`` turns any other into a 400.
_STREAM_UPDATE_FIELDS = {
    "stream_name",
    "description",
    "frame_interval",
    "enable_object_detection",
    "detection_confidence",
    "tags",
    "state",
}


def _bad_request(message: str) -> httpx.Response:
    return httpx.Response(400, json={"statusCode": 400, "message": message})


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


def make_live_hit(
    stream_id: str, score: float, epoch: int, offset: float = 4.5, raw: float = 0.36
) -> dict:
    """Return a hit on a live camera, shaped as observed on a real system:
    gateway-relative segment URL, string ``crop_bbox``, absolute raw score."""

    return {
        "id": None,
        "type": "Document",
        "page_content": "Video segment",
        "metadata": {
            "video_id": stream_id,
            "video_url": f"/live-streams/{stream_id}/segments/{epoch}.mp4",
            "seek_timestamp": offset,
            "segment_start": 0.0,
            "segment_end": 10.0,
            "relevance_score": score,
            "score_breakdown": {"raw_score": raw},
            "best_frame_info": {
                "is_live": True,
                "video_id": stream_id,
                "media_path": f"segments/{epoch}.mp4",
                "timestamp": offset,
                "crop_bbox": "395,452,542,894",
                "detected_label": "person",
                "is_detected_crop": True,
                "bucket_name": "live-streams",
            },
        },
    }


def make_stream(
    stream_id: str,
    name: str = "Lobby",
    *,
    state: str = "running",
    url: str = "rtsp://cam.local:8554/lobby",
    tags: list[str] | None = None,
) -> dict:
    """Return a stream as ``GET /streams`` lists it."""

    return {
        "stream_id": stream_id,
        "stream_name": name,
        "stream_url": url,
        "state": state,
        "tags": tags or [],
        "frame_interval": 15,
        "enable_object_detection": True,
        "detection_confidence": 0.5,
        "stats": {
            "frames_processed": 10,
            "embeddings_created": 4,
            "segments_stored": 2,
            "frames_stored": 10,
            "reconnect_count": 0,
        },
        "created_ts": 1767225600.0,  # 2026-01-01T00:00:00Z
        "updated_ts": 1767225600.0,
    }


#: Stand-in JPEG payload for ``GET /frames``; only its passthrough matters.
FRAME_JPEG_BASE64 = "/9j/4AAQSkZJRg=="


class FakeVss:
    """An in-process stand-in for Pipeline Manager."""

    def __init__(
        self,
        *,
        videos: list[dict] | None = None,
        states: list[dict] | None = None,
        features: dict[str, str] | None = None,
        hits: list[dict] | None = None,
        streams: list[dict] | None = None,
    ) -> None:
        self.videos = videos if videos is not None else []
        self.states = states if states is not None else []
        self.features = features or {
            "summary": "FEATURE_ON",
            "search": "FEATURE_ON",
        }
        self.hits = hits or []
        self.streams = streams if streams is not None else []
        #: ``GET /search/refresh-config`` body; ``None`` makes the route fail.
        self.refresh_config: dict[str, Any] | None = {
            "enabled": True,
            "intervalMs": 10000,
        }
        self.requests: list[tuple[str, str, Any]] = []
        #: Raw-state ``createdAt`` per state id, as ``GET /summary/{id}/raw``
        #: reports it; the UI states carry no timestamp.
        self.state_created_at: dict[str, str] = {}
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
        #: Query parameters of every ``GET /frames`` call, in order.
        self.frame_params: list[dict[str, str]] = []
        #: Stream ids deleted with ``purge_media`` or ``purge_embeddings`` set.
        self.purged: list[str] = []

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
                "evamPipeline": "object_detection",
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

        if path == "/tags" and request.method == "GET":
            # Pipeline Manager's tag table: upload tags plus the tags it
            # registers from polling the live streams.
            tags = [
                tag
                for item in (*self.videos, *self.streams)
                for tag in item.get("tags") or []
            ]
            return httpx.Response(200, json=list(dict.fromkeys(tags)))

        if path.startswith("/videos/search-embeddings/"):
            video_id = path.rsplit("/", 1)[-1]
            if not any(v["videoId"] == video_id for v in self.videos):
                return httpx.Response(404, json={"message": "Video not found"})
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

        if path.startswith("/summary/") and path.endswith("/raw"):
            state_id = path.split("/")[-2]
            match = next(
                (s for s in self.states if s["stateId"] == state_id), None
            )
            if match is None:
                return httpx.Response(200, json=None)
            created = self.state_created_at.get(state_id)
            return httpx.Response(
                200, json={**match, **({"createdAt": created} if created else {})}
            )

        if path.startswith("/summary/") and request.method == "GET":
            state_id = path.rsplit("/", 1)[-1]
            match = next(
                (s for s in self.states if s["stateId"] == state_id), None
            )
            # Pipeline Manager answers 200 with a null body for unknown ids.
            return httpx.Response(200, json=match)

        if path == "/search/refresh-config":
            if self.refresh_config is None:
                return httpx.Response(500, json={"message": "Internal server error"})
            return httpx.Response(200, json=self.refresh_config)

        if path.startswith("/search"):
            return self._handle_search(request.method, path, body)

        if path.startswith("/streams"):
            return self._handle_streams(request, path, body)

        if path == "/frames" and request.method == "GET":
            return self._handle_frame(dict(request.url.params))

        return httpx.Response(404, json={"message": f"no route {path}"})

    def _handle_frame(self, params: dict[str, str]) -> httpx.Response:
        """``GET /frames``: one frame, as dataprep's JSON variant returns it."""

        self.frame_params.append(params)
        invalid = _invalid_frame_query(params)
        if invalid:
            return _bad_request(invalid)
        known = {v["videoId"] for v in self.videos} | {
            s["stream_id"] for s in self.streams
        }
        if params.get("video_id") not in known:
            return httpx.Response(404, json={"message": "Media or frame not found."})
        cropped = params.get("variant") == "crop"
        return httpx.Response(
            200,
            json={
                "mime": "image/jpeg",
                "image_base64": FRAME_JPEG_BASE64,
                "frame": {
                    "video_id": params["video_id"],
                    "bucket_name": params.get("bucket_name") or "video-summary",
                    "media_path": params.get("media_path"),
                    "requested_timestamp": float(params["timestamp"]),
                    "actual_timestamp": float(params["timestamp"]),
                    "variant": params.get("variant") or "full",
                    "width": 240 if cropped else 1280,
                    "height": 340 if cropped else 720,
                    "cropped": cropped,
                },
            },
        )

    def _handle_streams(
        self, request: httpx.Request, path: str, body: Any
    ) -> httpx.Response:
        """``/streams`` routes, as in ``StreamsController``."""

        method = request.method
        if path == "/streams" and method == "GET":
            unknown = set(request.url.params) - {"state", "tags"}
            if unknown:
                return _bad_request(f"property {min(unknown)} should not exist")
            state = request.url.params.get("state")
            tags = request.url.params.get_list("tags")
            listed = [
                s
                for s in self.streams
                if (not state or s["state"] == state)
                and all(t in s["tags"] for t in tags)
            ]
            return httpx.Response(
                200,
                json={
                    "message": f"{len(listed)} live stream(s).",
                    "count": len(listed),
                    "streams": [_stream_info(s) for s in listed],
                },
            )
        if path == "/streams" and method == "POST":
            stream = self._new_stream(body or {})
            return httpx.Response(
                202, json={"message": "Live stream registered.", "stream": _stream_info(stream)}
            )
        if path == "/streams/batch" and method == "POST":
            items = []
            for item in (body or {}).get("items") or []:
                if "bad" in item.get("stream_url", ""):
                    items.append(
                        {
                            "identifier": _redact(item["stream_url"]),
                            "status": "error",
                            "message": "unreachable",
                        }
                    )
                    continue
                stream = self._new_stream(item)
                items.append(
                    {
                        "identifier": _redact(item["stream_url"]),
                        "stream_id": stream["stream_id"],
                        "status": "success",
                        "message": "Registered.",
                    }
                )
            accepted = sum(i["status"] == "success" for i in items)
            return httpx.Response(
                202,
                json={
                    "message": (
                        f"{accepted} live stream(s) registered, "
                        f"{len(items) - accepted} rejected."
                    ),
                    "accepted": accepted,
                    "rejected": len(items) - accepted,
                    "items": items,
                },
            )
        purge = _purge_flags(request.url.params)
        if path == "/streams" and method == "DELETE":
            items = []
            for stream_id in (body or {}).get("stream_ids") or []:
                if self._delete_stream(stream_id, purge) is None:
                    items.append(
                        {
                            "identifier": stream_id,
                            "stream_id": stream_id,
                            "status": "error",
                            "message": "No live stream registered with this id.",
                        }
                    )
                    continue
                items.append(
                    {
                        "identifier": stream_id,
                        "stream_id": stream_id,
                        "status": "success",
                        "message": "Stopped and deregistered.",
                    }
                )
            accepted = sum(i["status"] == "success" for i in items)
            return httpx.Response(
                200,
                json={
                    "message": (
                        f"{accepted} live stream(s) deleted, "
                        f"{len(items) - accepted} failed."
                    ),
                    "accepted": accepted,
                    "rejected": len(items) - accepted,
                    "items": items,
                },
            )
        stream_id = path.strip("/").split("/")[1]
        stream = next((s for s in self.streams if s["stream_id"] == stream_id), None)
        if stream is None:
            return httpx.Response(404, json={"message": "Stream not found"})
        if method == "GET":
            return httpx.Response(
                200, json={"message": "Live stream.", "stream": _stream_info(stream)}
            )
        if method == "PATCH":
            body = body or {}
            unknown = set(body) - _STREAM_UPDATE_FIELDS
            if unknown:
                return _bad_request(f"property {min(unknown)} should not exist")
            if "state" in body and body["state"] not in ("running", "paused"):
                return _bad_request("state must be one of: running, paused")
            stream.update(body)
            return httpx.Response(
                200,
                json={"message": "Live stream updated.", "stream": _stream_info(stream)},
            )
        if method == "DELETE":
            self._delete_stream(stream_id, purge)
            return httpx.Response(
                200,
                json={
                    "message": "Live stream deleted.",
                    "stream_id": stream_id,
                    "embeddings_purged": 0,
                    "media_purged": 0,
                },
            )
        return httpx.Response(404, json={"message": f"no route {path}"})

    def _delete_stream(self, stream_id: str, purge: bool) -> dict | None:
        stream = next((s for s in self.streams if s["stream_id"] == stream_id), None)
        if stream is not None:
            self.streams.remove(stream)
            if purge:
                self.purged.append(stream_id)
        return stream

    def _new_stream(self, body: dict) -> dict:
        stream = make_stream(
            f"s{len(self.streams) + 1}",
            body.get("stream_name") or "",
            state="pending",
            url=body["stream_url"],
            tags=body.get("tags"),
        )
        self.streams.append(stream)
        return stream

    def _handle_search(self, method: str, path: str, body: Any) -> httpx.Response:
        """``/search`` routes: persisted queries, as in ``SearchController``."""

        if path == "/search" and method == "POST":
            body = body or {}
            invalid = _invalid_search_body(body)
            if invalid:
                return _bad_request(invalid)
            stored = {
                "queryId": f"q{len(self.searches) + 1}",
                "query": body.get("query") or "",
                "image": body.get("image") or body.get("imageUrl"),
                "watch": False,
                "tags": [t for t in (body.get("tags") or "").split(",") if t],
                "timeFilter": body.get("timeFilter"),
                "minPeakScore": body.get("minPeakScore", 0),
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
        if parts[2:] == ["watch"] and method == "PATCH":
            # Like the real service: an unknown id is a silent no-op.
            if stored is not None:
                stored["watch"] = bool((body or {}).get("watch"))
            return httpx.Response(200)
        if stored is None:
            return httpx.Response(404, json={"message": "Search query not found"})
        if parts[2:] == ["refetch"] and method == "POST":
            if (body or {}).get("timeFilter"):
                stored["timeFilter"] = body["timeFilter"]
            if "minPeakScore" in (body or {}):
                stored["minPeakScore"] = body["minPeakScore"]
            return httpx.Response(201, json=_search_result(self, stored))
        return httpx.Response(404, json={"message": f"no route {path}"})


def _redact(url: str) -> str:
    return _CREDENTIALS_RE.sub(r"\1***@", url)


def _stream_info(stream: dict) -> dict:
    """A stream as dataprep's ``to_info`` returns it: credentials redacted."""

    return {**stream, "stream_url": _redact(stream["stream_url"])}


def _purge_flags(params: httpx.QueryParams) -> bool:
    """Whether a delete asked to purge, as ``LiveStreamPurgeQueryDto`` reads it."""

    return any(
        params.get(key, "").lower() in ("true", "1")
        for key in ("purge_media", "purge_embeddings")
    )


def _invalid_frame_query(params: dict[str, str]) -> str | None:
    """Why ``FrameQueryDto`` would reject ``params``, or ``None``."""

    allowed = {
        "video_id", "timestamp", "bucket_name", "media_path",
        "variant", "crop_bbox", "format", "quality",
    }
    unknown = set(params) - allowed
    if unknown:
        return f"property {min(unknown)} should not exist"
    if not params.get("video_id"):
        return "video_id should not be empty"
    try:
        if float(params.get("timestamp", "")) < 0:
            return "timestamp must not be less than 0"
    except ValueError:
        return "timestamp must be a number"
    if params.get("variant", "full") not in ("full", "crop"):
        return "variant must be one of: full, crop"
    if "crop_bbox" in params and not _CROP_BBOX_RE.match(params["crop_bbox"]):
        return "crop_bbox must be four integers in the form x1,y1,x2,y2"
    if "quality" in params and not (
        params["quality"].isdigit() and 1 <= int(params["quality"]) <= 100
    ):
        return "quality must not be greater than 100"
    return None


def _invalid_search_body(body: dict) -> str | None:
    """Why ``POST /search`` would reject ``body``, or ``None``."""

    has_text = bool(str(body.get("query") or "").strip())
    has_image = bool(body.get("image")) or bool(body.get("imageUrl"))
    if body.get("image") and body.get("imageUrl"):
        return "Provide either an image or an imageUrl, not both."
    if has_text and has_image:
        return "Provide either a text query or an image, not both."
    if not has_text and not has_image:
        return "Search query cannot be empty."
    return None


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
