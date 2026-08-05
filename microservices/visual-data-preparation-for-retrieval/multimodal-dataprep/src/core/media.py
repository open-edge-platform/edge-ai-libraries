# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Media-type helpers shared by the storage, validation and ingestion layers.

The dataprep service was originally video-only; every stored object was an
``.mp4`` and its MIME type was hardcoded to ``video/mp4``. Image ingestion makes
the service multi-modal, so the notion of "what is a media file" and "what MIME
type / content_type does it carry" is centralised here instead of being spread
across ``.mp4`` string checks.

Two vocabularies are used deliberately:

* **kind** -- the coarse modality bucket used by the embedding pipeline and the
  stored ``content_type`` metadata field: ``"video"`` or ``"image"``.
* **MIME type** -- the transport ``Content-Type`` written to the storage backend
  (e.g. ``video/mp4``, ``image/png``) and returned on download.

A single stored-media directory (``<video_id>/<filename>``) holds exactly one
media file; its extension is the source of truth for both kind and MIME type.
Client-declared MIME types are NOT trusted for images -- callers that accept
image bytes must sniff the real format (see ``core.image_ingest``) and derive the
extension from that, then use these helpers to map extension -> MIME/kind.
"""

import os
from typing import Optional

# ---------------------------------------------------------------------------
# Supported media extensions (lower-case, leading dot). These are code-level
# constants rather than env vars: the set of decodable/embeddable formats is a
# property of the pipeline (Pillow + CLIP image encoder), not a deployment knob.
# ---------------------------------------------------------------------------
SUPPORTED_VIDEO_EXTENSIONS = (".mp4",)
SUPPORTED_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")
SUPPORTED_MEDIA_EXTENSIONS = SUPPORTED_VIDEO_EXTENSIONS + SUPPORTED_IMAGE_EXTENSIONS

# Extension -> MIME type. Used when writing objects to storage and when serving
# them back on download. Kept explicit (rather than mimetypes.guess_type) so the
# supported set and its MIME mapping stay in one auditable place.
_EXTENSION_MIME = {
    ".mp4": "video/mp4",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
}

# Pillow format name (Image.format) -> canonical extension. Used to derive a
# trustworthy extension from sniffed image bytes, independent of the client's
# declared filename/MIME.
_PIL_FORMAT_EXTENSION = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
    "BMP": ".bmp",
    "GIF": ".gif",
    "MPO": ".jpg",  # multi-picture JPEG variant
}

_DEFAULT_MIME = "application/octet-stream"


def _ext(filename: str) -> str:
    """Return the lower-cased extension (including the dot) of ``filename``."""
    if not filename:
        return ""
    return os.path.splitext(filename)[1].lower()


def is_media_file(filename: Optional[str]) -> bool:
    """Return ``True`` when ``filename`` has a supported media (video or image) extension.

    This replaces the scattered ``obj_name.lower().endswith(".mp4")`` checks used
    for listing/resolving stored media. Sidecar/marker files (``.content_sha256``,
    ``.dedup/<hash>``, ``.json``) have no media extension and are therefore
    excluded, keeping them invisible to media listing exactly as before.
    """
    return _ext(filename or "") in SUPPORTED_MEDIA_EXTENSIONS


def is_image_file(filename: Optional[str]) -> bool:
    """Return ``True`` when ``filename`` has a supported image extension."""
    return _ext(filename or "") in SUPPORTED_IMAGE_EXTENSIONS


def is_video_file(filename: Optional[str]) -> bool:
    """Return ``True`` when ``filename`` has a supported video extension."""
    return _ext(filename or "") in SUPPORTED_VIDEO_EXTENSIONS


def detect_media_kind(filename: Optional[str]) -> Optional[str]:
    """Return ``"video"``, ``"image"`` or ``None`` based on the file extension.

    ``None`` means the name is not a recognised media file (e.g. a sidecar or an
    unsupported format), which callers use to skip non-media objects.
    """
    ext = _ext(filename or "")
    if ext in SUPPORTED_VIDEO_EXTENSIONS:
        return "video"
    if ext in SUPPORTED_IMAGE_EXTENSIONS:
        return "image"
    return None


def content_type_for_filename(filename: Optional[str]) -> str:
    """Return the MIME type for ``filename`` based on its extension.

    Falls back to ``application/octet-stream`` for unknown extensions so storage
    writes never fail purely on MIME derivation.
    """
    return _EXTENSION_MIME.get(_ext(filename or ""), _DEFAULT_MIME)


def extension_for_pil_format(pil_format: Optional[str]) -> Optional[str]:
    """Map a Pillow ``Image.format`` (e.g. ``"PNG"``) to a canonical extension.

    Returns ``None`` for formats outside the supported image set. Used to derive
    a trustworthy stored filename/extension from sniffed image bytes rather than
    trusting a client-supplied name or MIME type.
    """
    if not pil_format:
        return None
    return _PIL_FORMAT_EXTENSION.get(pil_format.upper())
