# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Request body size limit (HTTP 413 above ``max_bytes``).

The router buffers request bodies (chat JSON, pass-through uploads), so an
unbounded body is an easy way to exhaust its memory. The default matches the UI
nginx proxy's ``client_max_body_size 300M`` so the router applies the same cap
when it is reached directly.

Written as a plain ASGI middleware (not ``BaseHTTPMiddleware``) so streaming
responses pass through untouched.
"""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# 300 MiB: generous enough for audio/OCR pass-through uploads and base64 images.
DEFAULT_MAX_REQUEST_BYTES = 300 * 1024 * 1024


def _too_large_detail(max_bytes: int) -> str:
    return f"Request body exceeds the {max_bytes}-byte limit"


class BodySizeLimitMiddleware:
    """Reject request bodies larger than ``max_bytes`` (``<= 0`` disables)."""

    def __init__(self, app: ASGIApp, max_bytes: int = DEFAULT_MAX_REQUEST_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.max_bytes <= 0:
            await self.app(scope, receive, send)
            return

        # Fast path: a declared Content-Length over the limit is refused before
        # anything is read.
        for name, value in scope.get("headers", ()):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = None
                if declared is not None and declared > self.max_bytes:
                    response = JSONResponse(
                        {"detail": _too_large_detail(self.max_bytes)}, status_code=413
                    )
                    await response(scope, receive, send)
                    return
                break

        # Chunked or understated bodies: count bytes as the app reads them.
        # The HTTPException surfaces from ``request.body()`` / ``request.json()``
        # and is turned into a 413 response by FastAPI's exception handling.
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise HTTPException(
                        status_code=413, detail=_too_large_detail(self.max_bytes)
                    )
            return message

        await self.app(scope, limited_receive, send)
