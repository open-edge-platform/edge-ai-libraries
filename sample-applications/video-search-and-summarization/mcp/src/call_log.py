# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Log the flow of agent calls: one line per tool, resource and prompt call.

Each call gets a short id, set as :data:`current_call_id` for its duration,
so the Pipeline Manager requests it makes carry the same ``[id]`` and can be
grepped together. Arguments are logged only at DEBUG, with RTSP credentials
masked and image data and long text shortened.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any

from fastmcp.exceptions import FastMCPError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from .core.logging import current_call_id

logger = logging.getLogger("vss_mcp.calls")

_MAX_TEXT = 200
#: Any ``scheme://user:pass@`` -- wider than the RTSP-only redaction in
#: projections, since a log line can echo whatever the agent sent.
_CREDENTIALS_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/@\s'\"]+@")


def redact(text: str) -> str:
    """Mask URL credentials in ``text``."""

    return _CREDENTIALS_RE.sub(r"\1***@", text)
_MAX_ITEMS = 20


def safe_args(value: Any) -> Any:
    """Return ``value`` fit for a log line: no credentials, no image bytes."""

    if isinstance(value, str):
        if value.startswith("data:"):
            header = value.split(",", 1)[0]
            return f"<{header},... {len(value)} chars>"
        text = redact(value)
        if len(text) > _MAX_TEXT:
            return f"{text[:_MAX_TEXT]}... ({len(text)} chars)"
        return text
    if isinstance(value, dict):
        return {key: safe_args(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        items = [safe_args(item) for item in value[:_MAX_ITEMS]]
        if len(value) > _MAX_ITEMS:
            items.append(f"... {len(value) - _MAX_ITEMS} more")
        return items
    return value


class CallLogMiddleware(Middleware):
    """Log when each tool, resource or prompt call starts and how it ends."""

    async def on_call_tool(self, context: MiddlewareContext, call_next: CallNext) -> Any:
        params = context.message
        return await self._logged(
            "tool", params.name, getattr(params, "arguments", None), context, call_next
        )

    async def on_read_resource(
        self, context: MiddlewareContext, call_next: CallNext
    ) -> Any:
        return await self._logged(
            "resource", str(context.message.uri), None, context, call_next
        )

    async def on_get_prompt(self, context: MiddlewareContext, call_next: CallNext) -> Any:
        params = context.message
        return await self._logged(
            "prompt", params.name, getattr(params, "arguments", None), context, call_next
        )

    @staticmethod
    async def _logged(
        kind: str,
        name: str,
        arguments: dict[str, Any] | None,
        context: MiddlewareContext,
        call_next: CallNext,
    ) -> Any:
        token = current_call_id.set(uuid.uuid4().hex[:8])
        started = time.perf_counter()
        try:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("%s %s called with %s", kind, name, safe_args(arguments or {}))
            try:
                result = await call_next(context)
            except FastMCPError as exc:
                # Agent-facing errors (bad id, VSS down): expected, worth a line.
                logger.info(
                    "%s %s failed in %.0f ms: %s",
                    kind, name, _elapsed_ms(started), redact(str(exc)),
                )
                raise
            except Exception as exc:
                logger.error(
                    "%s %s crashed in %.0f ms: %s",
                    kind, name, _elapsed_ms(started), type(exc).__name__,
                )
                raise
            if getattr(result, "is_error", False):
                logger.info("%s %s returned an error in %.0f ms", kind, name, _elapsed_ms(started))
            else:
                logger.info("%s %s ok in %.0f ms", kind, name, _elapsed_ms(started))
            return result
        finally:
            current_call_id.reset(token)


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000
