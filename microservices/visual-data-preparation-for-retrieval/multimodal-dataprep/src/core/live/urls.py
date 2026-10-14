# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""RTSP URL validation and credential redaction.

A live stream's source URL frequently embeds credentials (``rtsp://user:pw@host``).
The full URL is required to (re)connect and is therefore kept in the registry
record, but it must never leave that record: the vector database is read by
retrieval services and surfaced in search results, and logs/telemetry are
routinely shipped elsewhere.

:func:`redact_stream_url` is the single redaction implementation, applied at
every boundary (vector metadata, API responses, logs, telemetry).
"""

from __future__ import annotations

import re
from typing import Final, Optional
from urllib.parse import urlsplit, urlunsplit

#: Matches the ``[Errno 111] `` prefix that OSError/PyAV prepend to low-level
#: connection failures. Stripped from user-facing messages, which only need the
#: human-readable reason, not the numeric code.
_ERRNO_PREFIX: Final = re.compile(r"^\[Errno -?\d+\]\s*")

#: Schemes accepted for a live stream source.
ALLOWED_SCHEMES: Final[frozenset] = frozenset({"rtsp", "rtsps"})

#: Placeholder substituted for stripped userinfo so the presence of
#: credentials stays visible without disclosing them.
REDACTED_USERINFO: Final[str] = "***"


class InvalidStreamUrlError(ValueError):
    """Raised when a supplied live-stream URL is unusable or unsafe."""


def redact_stream_url(url) -> str:
    """Return ``url`` with any embedded credentials removed.

    ``rtsp://user:pw@cam-1:554/live`` becomes ``rtsp://***@cam-1:554/live``. The
    ``***@`` marker is kept so operators can tell that credentials were
    configured, without disclosing them.

    The function never raises: an unparsable value is reduced to a constant so a
    malformed URL cannot leak through an error path.
    """
    if not url:
        return ""
    try:
        parts = urlsplit(str(url).strip())
    except ValueError:
        return "<unparsable-stream-url>"

    host = parts.hostname or ""
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    netloc = host
    try:
        port = parts.port
    except ValueError:
        port = None
    if port:
        netloc = f"{netloc}:{port}"
    if parts.username:
        netloc = f"{REDACTED_USERINFO}@{netloc}"

    # The query string can also carry secrets (e.g. ?password=...); drop it.
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def validate_stream_url(url) -> str:
    """Validate and normalize a live-stream source URL.

    Returns the trimmed URL (credentials preserved, since the caller needs it to
    connect). Raises :class:`InvalidStreamUrlError` when the value is not an
    RTSP URL with a resolvable host.
    """
    if not url or not str(url).strip():
        raise InvalidStreamUrlError("Stream URL must not be empty.")

    candidate = str(url).strip()
    if any(ch in candidate for ch in ("\n", "\r", "\t", " ")):
        raise InvalidStreamUrlError("Stream URL must not contain whitespace or control characters.")

    try:
        parts = urlsplit(candidate)
    except ValueError as exc:
        raise InvalidStreamUrlError(f"Stream URL is not parsable: {exc}") from exc

    scheme = (parts.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise InvalidStreamUrlError(
            f"Unsupported scheme '{parts.scheme}'. Expected one of: {', '.join(sorted(ALLOWED_SCHEMES))}."
        )
    if not parts.hostname:
        raise InvalidStreamUrlError("Stream URL must include a host.")
    try:
        # Accessing .port validates the port component.
        _ = parts.port
    except ValueError as exc:
        raise InvalidStreamUrlError(f"Stream URL has an invalid port: {exc}") from exc

    return candidate


def default_stream_name(url) -> str:
    """Derive a friendly default name from a stream URL (credentials removed)."""
    redacted = redact_stream_url(url)
    return redacted or "live-stream"


def clean_connection_error(message, stream_url: Optional[str] = None) -> str:
    """Tidy a low-level connection error for display to an operator.

    PyAV/OSError render connection failures as ``[Errno 111] Connection
    refused: 'rtsp://...'``. Two things make that unfit for ``last_error`` and
    API responses:

    * the ``[Errno NNN] `` prefix is noise — the reason text is what an operator
      needs; and
    * the embedded URL carries the source credentials verbatim.

    This strips the errno prefix and replaces any occurrence of the credentialed
    ``stream_url`` with its redacted form, so a password never reaches
    ``last_error``, the API, logs, or telemetry.
    """
    text = str(message or "").strip()
    if stream_url:
        full = str(stream_url).strip()
        if full:
            text = text.replace(full, redact_stream_url(full))
    return _ERRNO_PREFIX.sub("", text)
