# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Helpers for user-provided RTSP stream URLs.

- ``validate_rtsp_url``: strict validation of RTSP URLs before they are placed
  in a GStreamer pipeline description (property values are not quoted there, so
  characters such as whitespace, ``!`` or quotes could inject extra elements).
- ``probe_rtsp_codec``: detect the video codec of an RTSP stream with
  ``gst-discoverer-1.0`` so a device-specific decoder can be selected.
"""

import logging
import os
import re
import subprocess
import threading
import time
from urllib.parse import urlsplit

logger = logging.getLogger("rtsp_utils")

RTSP_URL_PREFIX = "rtsp://"
RTSP_URL_MAX_LENGTH = 2048

# RFC 3986 unreserved + reserved characters and percent-encoding, without
# characters that are significant in GStreamer pipeline descriptions or
# that would require quoting: whitespace, '!', quotes, ',' (caps separator),
# parentheses, '*', '$' and '\'.
_RTSP_URL_ALLOWED_RE = re.compile(r"^[A-Za-z0-9\-._~:/?#\[\]@%&+;=]+$")

RTSP_PROBE_TIMEOUT_S: int = max(1, int(os.environ.get("RTSP_PROBE_TIMEOUT_S", "5")))
RTSP_PROBE_CACHE_TTL_S: float = 60.0
GST_DISCOVERER_BIN = "gst-discoverer-1.0"

# Media type of the first video stream reported by gst-discoverer, e.g.
# "    video #1: video/x-h264, stream-format=(string)avc, ..."
_DISCOVERER_VIDEO_STREAM_RE = re.compile(
    r"^\s*video #\d+:\s*([A-Za-z0-9\-/.]+)", re.MULTILINE
)

# Values must be keys of video_decoder.FOURCC_TO_CODEC.
_MEDIA_TYPE_TO_CODEC: dict[str, str] = {
    "video/x-h264": "h264",
    "video/x-h265": "h265",
    "image/jpeg": "MJPG",
}

_probe_cache: dict[str, tuple[str | None, float]] = {}
_probe_cache_lock = threading.Lock()


def validate_rtsp_url(url: str) -> str:
    """Validate a user-provided RTSP URL and return it stripped.

    Raises:
        ValueError: If the URL is not a safe, well-formed ``rtsp://`` URL.
    """
    if not isinstance(url, str):
        raise ValueError("RTSP URL must be a string")
    url = url.strip()
    if not url:
        raise ValueError("RTSP URL must not be empty")
    if len(url) > RTSP_URL_MAX_LENGTH:
        raise ValueError(f"RTSP URL is too long (max {RTSP_URL_MAX_LENGTH} characters)")
    if not url.startswith(RTSP_URL_PREFIX):
        raise ValueError(f"RTSP URL must start with '{RTSP_URL_PREFIX}'")
    if not _RTSP_URL_ALLOWED_RE.match(url):
        raise ValueError(
            "RTSP URL contains unsupported characters "
            "(whitespace, quotes, '!', ',', '(', ')', '*', '$' and '\\' are not allowed)"
        )

    parts = urlsplit(url)
    if parts.username is not None or parts.password is not None:
        raise ValueError(
            "Credentials embedded in the RTSP URL (user:password@) are not supported"
        )
    if not parts.hostname:
        raise ValueError("RTSP URL must include a host")
    try:
        parts.port
    except ValueError as e:
        raise ValueError(f"RTSP URL has an invalid port: {e}") from e

    return url


def redact_rtsp_url(url: str) -> str:
    """Return the URL without query string and fragment, for logging."""
    try:
        parts = urlsplit(url)
        netloc = parts.hostname or ""
        if parts.port is not None:
            netloc = f"{netloc}:{parts.port}"
        return f"{parts.scheme}://{netloc}{parts.path}"
    except ValueError:
        return "<invalid RTSP URL>"


def parse_discoverer_output(output: str) -> str | None:
    """Extract the codec of the first video stream from gst-discoverer output."""
    match = _DISCOVERER_VIDEO_STREAM_RE.search(output)
    if match is None:
        return None
    return _MEDIA_TYPE_TO_CODEC.get(match.group(1).lower())


def _run_discoverer(url: str) -> str | None:
    try:
        result = subprocess.run(
            [GST_DISCOVERER_BIN, "-v", "-t", str(RTSP_PROBE_TIMEOUT_S), url],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=RTSP_PROBE_TIMEOUT_S + 5,
            check=False,
        )
    except FileNotFoundError:
        logger.warning(f"'{GST_DISCOVERER_BIN}' not found, cannot probe RTSP stream")
        return None
    except subprocess.TimeoutExpired:
        logger.warning(f"Timed out probing RTSP stream {redact_rtsp_url(url)}")
        return None

    codec = parse_discoverer_output(result.stdout)
    if codec is None:
        logger.warning(
            f"Could not determine video codec of RTSP stream {redact_rtsp_url(url)}"
        )
    return codec


def probe_rtsp_codec(url: str) -> str | None:
    """Detect the video codec of an RTSP stream.

    Results (including failures) are cached per URL for ``RTSP_PROBE_CACHE_TTL_S``
    seconds so that multiple pipelines using the same stream probe it only once.

    Returns:
        Codec string accepted by ``VideoDecoder.select_decoder`` ("h264", "h265",
        "MJPG"), or None if the URL is invalid, the stream is unreachable or the
        codec is not supported.
    """
    try:
        url = validate_rtsp_url(url)
    except ValueError as e:
        logger.warning(f"Not probing invalid RTSP URL: {e}")
        return None

    now = time.monotonic()
    with _probe_cache_lock:
        cached = _probe_cache.get(url)
        if cached is not None and now - cached[1] < RTSP_PROBE_CACHE_TTL_S:
            return cached[0]

    codec = _run_discoverer(url)
    if codec is not None:
        logger.debug(f"Probed codec '{codec}' from RTSP stream {redact_rtsp_url(url)}")

    with _probe_cache_lock:
        _probe_cache[url] = (codec, time.monotonic())
    return codec


def clear_probe_cache() -> None:
    """Clear cached probe results (used in tests)."""
    with _probe_cache_lock:
        _probe_cache.clear()
