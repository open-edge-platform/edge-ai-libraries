# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Logging configuration helpers."""

import logging
from contextvars import ContextVar

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(call_tag)s%(message)s"

#: Id of the MCP call being served, so every line it causes can be grepped.
current_call_id: ContextVar[str | None] = ContextVar("current_call_id", default=None)

#: Library loggers replaced by this server's own lines: httpx/httpcore by
#: ``VssClient``'s one line per request, and FastMCP's handler trace -- which
#: logs tool arguments unredacted at DEBUG -- by ``CallLogMiddleware``.
_QUIET_LOGGERS = ("httpx", "httpcore", "fastmcp.server.mixins.mcp_operations")


class CallIdFilter(logging.Filter):
    """Stamp each record with ``call_tag``: ``"[<call id>] "`` or ``""``."""

    def filter(self, record: logging.LogRecord) -> bool:
        call_id = current_call_id.get()
        record.call_tag = f"[{call_id}] " if call_id else ""
        return True


def configure_logging(level: str) -> None:
    """Configure the root logger and tag lines with the current call id."""

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(level=level, format=LOG_FORMAT)
    root_logger.setLevel(level)
    for handler in root_logger.handlers:
        if not any(isinstance(f, CallIdFilter) for f in handler.filters):
            handler.addFilter(CallIdFilter())
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger(__name__).debug("Logging initialised at level %s", level)
