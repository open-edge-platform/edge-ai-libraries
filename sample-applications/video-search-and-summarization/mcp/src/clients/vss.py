# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Typed HTTP client for the VSS Pipeline Manager REST API."""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx
from fastmcp.exceptions import ToolError

logger = logging.getLogger(__name__)

#: Image suffixes accepted by :func:`encode_image_file` -- the same types the
#: UI's file picker accepts -- mapped to the MIME type of the data URL.
IMAGE_SUFFIXES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

#: A query image uploaded with ``POST /search/images``: its bare ``imageId``,
#: or its ``imagePath`` (anything ending in ``search-images/<imageId>``).
_IMAGE_ID = (
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
    r"\.(?:jpg|png|webp)"
)
_IMAGE_ID_RE = re.compile(rf"^{_IMAGE_ID}$")
_IMAGE_PATH_RE = re.compile(rf"(?:^|/)search-images/{_IMAGE_ID}$")

_FAILURE_HINTS = {
    404: "The item does not exist, or the feature is disabled in this deployment.",
    408: "The upstream stage timed out. Retry, or check that the embedding service is up.",
    422: "VSS rejected the input as unprocessable.",
    502: "A dependency of VSS failed. Check the data-prep and embedding services.",
}


class VssError(ToolError):
    """An error from the VSS backend, phrased for an agent to act on.

    A :class:`ToolError`, so FastMCP returns it as an ``isError`` result with
    the message intact -- even with error masking on -- and logs no traceback.

    ``status_code`` is the HTTP status behind it, when there was one, so a
    caller can recognise "not found" without matching on prose.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def encode_image_file(path: str) -> str:
    """Read a local image file and return it as a ``data:`` URL.

    Raises:
        VssError: If the file is missing or not a recognised image type.
    """

    source = Path(path).expanduser()
    if not source.is_file():
        raise VssError(
            f"No file at {source}. The path must be readable by the MCP "
            "server, which may be a different filesystem from the client -- "
            "this is expected for a browser or chat-UI attachment, which "
            "lives on the client's machine, not the server's. If you cannot "
            "give a path the MCP server can read, read the file's bytes "
            "yourself, base64-encode them, and call this tool again with "
            "image='data:<mime-type>;base64,<data>' (e.g. "
            "'data:image/png;base64,iVBORw0KG...') instead of a path."
        )

    mime = IMAGE_SUFFIXES.get(source.suffix.lower())
    if not mime:
        raise VssError(
            f"{source.name} does not look like an image "
            f"(expected one of {sorted(IMAGE_SUFFIXES)})."
        )

    encoded = base64.b64encode(source.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def is_image_reference(image: str) -> bool:
    """Whether ``image`` is a claim-check reference to a stored query image.

    That is an ``http(s)`` URL, or an ``imageId``/``imagePath`` returned by
    ``POST /search/images`` that is not a readable local file. A reference is
    forwarded to Pipeline Manager as ``imageUrl``; Pipeline Manager loads the
    bytes from its own object store (and rejects any URL outside it), so this
    server never downloads anything itself.
    """

    if image.lower().startswith(("http://", "https://")):
        return True
    if _IMAGE_ID_RE.match(image) or _IMAGE_PATH_RE.search(image):
        return not Path(image).expanduser().is_file()
    return False


def resolve_image_input(image: str) -> str:
    """Return ``image`` as a data URL: forwarded verbatim if it already is one,
    otherwise read from disk as a path.

    Raises:
        VssError: On a malformed data URL, or an unusable path.
    """

    if image.startswith("data:"):
        if ";base64," not in image:
            raise VssError(
                "Malformed data URL: expected "
                "'data:<mime-type>;base64,<data>'."
            )
        return image
    return encode_image_file(image)


class VssClient:
    """Async client for Pipeline Manager.

    Args:
        base_url: Pipeline Manager base URL, e.g. ``http://host:12345/manager``.
        timeout_seconds: Per-request timeout.
        client: Pre-built HTTP client, for tests.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url, timeout=timeout_seconds
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Issue a request and return the decoded JSON (or raw text) body.

        Raises:
            VssError: On timeout, connection failure, or a non-2xx status.
        """

        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise VssError(
                f"VSS did not respond within {self._timeout:.0f}s for "
                f"{method} {path}. The service may be busy loading a model."
            ) from exc
        except httpx.RequestError as exc:
            raise VssError(
                f"Could not reach VSS at {self._base_url} ({exc.__class__.__name__}). "
                "Check that the deployment is running and VSS_IP is correct."
            ) from exc

        if response.status_code >= 400:
            raise VssError(
                self._describe_failure(response, method, path),
                status_code=response.status_code,
            )

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    @staticmethod
    def _describe_failure(response: httpx.Response, method: str, path: str) -> str:
        """Turn an error response into a sentence that suggests a next step."""

        detail = ""
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = str(body.get("message") or body.get("detail") or "")
        except ValueError:
            detail = response.text[:200]

        parts = [
            f"VSS returned {response.status_code} for {method} {path}.",
            detail,
            _FAILURE_HINTS.get(response.status_code, ""),
        ]
        return " ".join(part for part in parts if part)

    # -- Deployment ------------------------------------------------------

    async def get_features(self) -> dict[str, Any]:
        """Return the raw ``GET /app/features`` payload."""

        return await self._request("GET", "/app/features") or {}

    async def get_app_config(self) -> dict[str, Any]:
        """Return the system configuration, including sampling limits."""

        return await self._request("GET", "/app/config") or {}

    async def list_videos(self) -> list[dict[str, Any]]:
        """Return every video row known to VSS."""

        payload = await self._request("GET", "/videos") or {}
        return payload.get("videos") or []

    async def get_video(self, video_id: str) -> dict[str, Any] | None:
        """Return one video row, or ``None`` when it does not exist."""

        try:
            payload = await self._request("GET", f"/videos/{video_id}") or {}
        except VssError as exc:
            if exc.status_code == 404:
                return None
            raise
        return payload.get("video")

    async def create_search_embeddings(self, video_id: str) -> None:
        """Generate frame embeddings for a video.

        Blocking: the endpoint holds the connection until data-prep finishes.

        Raises:
            VssError: If the upstream reports anything but ``success``.
        """

        payload = await self._request(
            "POST", f"/videos/search-embeddings/{video_id}", json={}
        )
        if (payload or {}).get("status") != "success":
            raise VssError(
                f"Embedding generation did not succeed for {video_id}: {payload!r}"
            )

    # -- Summaries -------------------------------------------------------

    async def create_summary(self, body: dict[str, Any]) -> str:
        """Start a summary pipeline and return its state id."""

        payload = await self._request("POST", "/summary", json=body)
        state_id = (payload or {}).get("summaryPipelineId")
        if not state_id:
            raise VssError(f"Summary request returned no pipeline id: {payload!r}")
        return state_id

    async def get_ui_state(self, state_id: str) -> dict[str, Any] | None:
        """Return the pipeline state for ``state_id``, or ``None`` if unknown."""

        payload = await self._request("GET", f"/summary/{state_id}")
        return payload if isinstance(payload, dict) and payload else None

    async def list_ui_states(self) -> list[dict[str, Any]]:
        """Return every pipeline state, with nulls filtered out."""

        payload = await self._request("GET", "/summary/ui") or []
        return [item for item in payload if isinstance(item, dict) and item]

    async def poll_state(
        self,
        state_id: str,
        is_done: Callable[[dict[str, Any]], bool],
        *,
        wait_seconds: float,
        poll_interval_seconds: float,
        on_state: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> tuple[dict[str, Any] | None, bool]:
        """Poll a pipeline state until ``is_done`` holds or the budget expires.

        The budget is mandatory: Pipeline Manager has no failure terminal
        state, so a crashed pipeline would otherwise be polled forever.

        ``on_state`` is awaited with every state observed, e.g. to report
        progress.

        Returns:
            ``(state, completed)``; ``state`` is the last one observed.
        """

        deadline = time.monotonic() + wait_seconds
        while True:
            state = await self.get_ui_state(state_id)
            if state and on_state:
                await on_state(state)
            if state and is_done(state):
                return state, True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return state, False
            await asyncio.sleep(min(poll_interval_seconds, remaining))

    # -- Search ----------------------------------------------------------

    async def create_search(
        self,
        query: str | None = None,
        *,
        image: str | None = None,
        image_url: str | None = None,
        tags: list[str] | None = None,
        time_filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a search query that VSS persists, as the UI does, and return
        it. Results arrive asynchronously; poll with :meth:`poll_search`.

        Search is by text, by ``image`` (a data URL), or by ``image_url`` (a
        reference to an image uploaded with ``POST /search/images``). The
        backend rejects more than one at once, so only one is sent.

        Raises:
            VssError: If VSS returns no query id.
        """

        body: dict[str, Any]
        if image_url:
            body = {"imageUrl": image_url}
        elif image:
            body = {"image": image}
        else:
            body = {"query": query}
        if tags:
            body["tags"] = ",".join(tags)
        if time_filter:
            body["timeFilter"] = time_filter
        payload = await self._request("POST", "/search", json=body)
        if not isinstance(payload, dict) or not payload.get("queryId"):
            raise VssError(f"Search request returned no query id: {payload!r}")
        return payload

    async def get_search(self, query_id: str) -> dict[str, Any] | None:
        """Return a persisted search query, or ``None`` if unknown."""

        payload = await self._request("GET", f"/search/{query_id}")
        return payload if isinstance(payload, dict) and payload else None

    async def list_searches(self) -> list[dict[str, Any]]:
        """Return every persisted search query."""

        payload = await self._request("GET", "/search") or []
        return [item for item in payload if isinstance(item, dict) and item]

    async def refetch_search(
        self, query_id: str, time_filter: dict[str, Any] | None = None
    ) -> None:
        """Re-run a persisted search query. Blocks until it has run."""

        body = {"timeFilter": time_filter} if time_filter else {}
        await self._request("POST", f"/search/{query_id}/refetch", json=body)

    async def set_search_watch(self, query_id: str, watch: bool) -> None:
        """Watch or unwatch a persisted search query."""

        await self._request(
            "PATCH", f"/search/{query_id}/watch", json={"watch": watch}
        )

    async def poll_search(
        self,
        query_id: str,
        *,
        wait_seconds: float,
        poll_interval_seconds: float,
    ) -> tuple[dict[str, Any] | None, bool]:
        """Poll a persisted search until it leaves ``running`` or the budget
        expires.

        Returns:
            ``(query, completed)``; ``query`` is the last one observed.
        """

        deadline = time.monotonic() + wait_seconds
        while True:
            query = await self.get_search(query_id)
            if query and query.get("queryStatus") != "running":
                return query, True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return query, False
            await asyncio.sleep(min(poll_interval_seconds, remaining))
