# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Image-source loading for the JSON ingestion endpoints.

The multipart upload path receives raw image bytes directly. The JSON endpoints
(``POST /media/ingest`` and its batch variant) instead accept a typed source
that mirrors the multimodal-embedding-serving (MME) discriminator:

* ``type="image_base64"`` -- an inline base64 string (optionally a ``data:`` URL).
* ``type="image_url"``    -- a remote ``http(s)`` URL the server downloads.

This module turns either source into ``(content_bytes, filename)`` with the same
guarantees the multipart path relies on:

* **The bytes are the trust boundary.** The client-declared MIME/filename is
  never trusted; the real format is sniffed with Pillow and the stored filename's
  extension is derived from that sniffed format.
* **Bounded size.** Both transports enforce ``MAX_IMAGE_BYTES`` -- base64 is
  size-checked before/after decode; URL downloads are streamed and aborted the
  moment the cap is exceeded (so a hostile ``Content-Length`` cannot force an
  unbounded read).
* **URL fetch is SSRF-adjacent** and therefore restricted to ``http``/``https``
  with a bounded timeout. Network-level egress restrictions remain a deployment
  responsibility; this module provides the scheme/size/timeout guards.
"""

import base64
import binascii
import io
import os
import re
import uuid
from http import HTTPStatus
from typing import Tuple
from urllib.parse import urlparse

import requests
from PIL import Image, UnidentifiedImageError

from src.common import DataPrepException, logger
from src.core.media import extension_for_pil_format

# Maximum decoded image size. A code-level constant (not a deployment knob): it
# bounds memory for a single decode/encode and is a property of the pipeline.
MAX_IMAGE_BYTES = 50 * 1024 * 1024  # 50 MB

# Bounded network timeout for URL fetches (connect, read) in seconds.
_URL_FETCH_TIMEOUT = (5, 30)
_URL_STREAM_CHUNK = 64 * 1024

# data:<mime>;base64,<payload>
_DATA_URL_RE = re.compile(r"^data:[^;,]*;base64,", re.IGNORECASE)


def _too_large() -> DataPrepException:
    """Build the standard 413 error for oversized image payloads."""
    return DataPrepException(
        status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
        msg=f"Image exceeds the maximum allowed size of {MAX_IMAGE_BYTES // (1024 * 1024)} MB.",
    )


def decode_base64_image(image_base64: str) -> bytes:
    """Decode a base64 image string (bare or ``data:`` URL) into raw bytes.

    The size is bounded both before decoding (via the encoded-length estimate,
    which cheaply rejects hostile payloads) and after decoding (exact). Invalid
    base64 raises a 400.
    """
    if not image_base64 or not isinstance(image_base64, str):
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST, msg="image_base64 must be a non-empty string."
        )

    payload = _DATA_URL_RE.sub("", image_base64.strip())

    # Cheap pre-check: base64 encodes 3 bytes per 4 chars, so the decoded size is
    # ~3/4 of the string length. Reject clearly-oversized inputs before decoding.
    if (len(payload) * 3) // 4 > MAX_IMAGE_BYTES:
        raise _too_large()

    try:
        content = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST, msg=f"Invalid base64 image data: {exc}"
        )

    if len(content) > MAX_IMAGE_BYTES:
        raise _too_large()
    if not content:
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST, msg="Decoded base64 image is empty."
        )
    return content


def fetch_image_from_url(image_url: str) -> bytes:
    """Download an image from an ``http(s)`` URL with scheme/size/timeout guards.

    The response body is streamed and the accumulated size is checked against
    ``MAX_IMAGE_BYTES`` on every chunk, so an oversized or lying ``Content-Length``
    cannot force an unbounded read. Non-http(s) schemes and transport failures
    raise a 400/502 respectively.
    """
    if not image_url or not isinstance(image_url, str):
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST, msg="image_url must be a non-empty string."
        )

    parsed = urlparse(image_url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST,
            msg="image_url must be an absolute http(s) URL.",
        )

    try:
        with requests.get(
            image_url, stream=True, timeout=_URL_FETCH_TIMEOUT, allow_redirects=True
        ) as response:
            response.raise_for_status()

            # Fast-fail on an advertised oversized body (best-effort only).
            declared = response.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > MAX_IMAGE_BYTES:
                raise _too_large()

            buffer = io.BytesIO()
            total = 0
            for chunk in response.iter_content(chunk_size=_URL_STREAM_CHUNK):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_IMAGE_BYTES:
                    raise _too_large()
                buffer.write(chunk)
    except DataPrepException:
        raise
    except requests.RequestException as exc:
        logger.warning("Image URL fetch failed: %s", exc)
        raise DataPrepException(
            status_code=HTTPStatus.BAD_GATEWAY,
            msg=f"Failed to download image from URL: {exc}",
        )

    content = buffer.getvalue()
    if not content:
        raise DataPrepException(
            status_code=HTTPStatus.BAD_GATEWAY, msg="Downloaded image is empty."
        )
    return content


def sniff_image_extension(content: bytes) -> str:
    """Return the canonical extension for ``content`` by sniffing the real format.

    Uses Pillow to identify the format from the bytes themselves, independent of
    any client-declared name/MIME. Unsupported or undecodable formats raise a 400.
    """
    try:
        with Image.open(io.BytesIO(content)) as probe:
            pil_format = probe.format
    except (UnidentifiedImageError, OSError) as exc:
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST,
            msg=f"Provided data is not a supported/decodable image: {exc}",
        )

    extension = extension_for_pil_format(pil_format)
    if extension is None:
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST,
            msg=f"Unsupported image format: {pil_format or 'unknown'}.",
        )
    return extension


def resolve_image_filename(given_filename, source_url, extension: str) -> str:
    """Derive a safe stored filename with the sniffed ``extension``.

    Preference order for the base name: an explicit client ``filename`` (basename
    only, extension replaced by the sniffed one), then the URL path basename, then
    a generated uuid. The sniffed extension always wins so the stored name never
    contradicts the real bytes.
    """
    stem = None
    if given_filename and isinstance(given_filename, str):
        stem = os.path.splitext(os.path.basename(given_filename.strip()))[0]
    if not stem and source_url:
        url_name = os.path.basename(urlparse(source_url).path)
        if url_name:
            stem = os.path.splitext(url_name)[0]
    if not stem:
        stem = f"image_{uuid.uuid4().hex[:12]}"
    return f"{stem}{extension}"


def load_image_source(
    source_type: str,
    *,
    image_base64=None,
    image_url=None,
    filename=None,
) -> Tuple[bytes, str]:
    """Resolve a typed image source into ``(content_bytes, stored_filename)``.

    ``source_type`` selects the transport (``"image_base64"`` or ``"image_url"``);
    the bytes are then sniffed to derive a trustworthy stored filename/extension.
    """
    if source_type == "image_base64":
        content = decode_base64_image(image_base64)
        source_url = None
    elif source_type == "image_url":
        content = fetch_image_from_url(image_url)
        source_url = image_url
    else:
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST,
            msg=f"Unsupported image source type: {source_type!r}.",
        )

    extension = sniff_image_extension(content)
    stored_filename = resolve_image_filename(filename, source_url, extension)
    return content, stored_filename
