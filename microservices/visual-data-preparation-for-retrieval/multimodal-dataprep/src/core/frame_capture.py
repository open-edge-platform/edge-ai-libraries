# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""On-demand single-frame extraction (serve, don't store).

A retrieval hit names a frame by *where* it lives (``video_id`` / live segment)
and *when* it happened (a ``timestamp`` offset into that media). Rather than
persisting every embedded frame as a JPEG, this module reconstructs exactly one
frame on request: it opens the already-stored media (an uploaded file or a live
``segments/<ts>.mp4`` clip), seeks to the timestamp, decodes a single frame, and
returns JPEG bytes. Nothing is written back to object storage.

The service stays **query-agnostic**: callers (e.g. the search service, which
already identifies the peak-scoring frame of a segment) pass the frame address
and, for the cropped variant, the bounding box captured at ingest. This module
never ranks, scores, or interprets a query.

Timestamp contract
------------------
``timestamp`` is **seconds from the start of the addressed media object**:

* uploaded video -> position within the whole file;
* live stream -> offset within the segment named by ``media_path`` (this is
  exactly what the live ingest pipeline stores in each embedding's ``timestamp``).
"""

from __future__ import annotations

import io
import pathlib
import tempfile
from dataclasses import dataclass
from http import HTTPStatus
from typing import Iterable, List, Optional

import av
from PIL import Image

from src.common import DataPrepException, logger
from src.core.utils.video_utils import resolve_media_source

#: Clamp for the JPEG quality query parameter.
_MIN_JPEG_QUALITY = 1
_MAX_JPEG_QUALITY = 100
#: Default JPEG quality when the caller does not specify one.
DEFAULT_JPEG_QUALITY = 90


@dataclass
class ExtractedFrame:
    """One decoded frame plus the facts a caller needs to describe it."""

    jpeg_bytes: bytes
    #: Timestamp the caller asked for (seconds into the addressed media).
    requested_timestamp: float
    #: Timestamp of the frame actually returned (nearest decodable at/after the
    #: request, or the last frame when the request is past the end).
    actual_timestamp: Optional[float]
    width: int
    height: int
    #: Whether a crop box was applied to the returned image.
    cropped: bool


def _normalize_bbox(
    crop_bbox: Iterable[float], frame_width: int, frame_height: int
) -> Optional[tuple]:
    """Clamp a ``[x1, y1, x2, y2]`` pixel box to the frame; None if degenerate."""
    box = list(crop_bbox)
    if len(box) != 4:
        raise DataPrepException(
            msg="crop_bbox must be four numbers: x1,y1,x2,y2.",
            status_code=HTTPStatus.BAD_REQUEST,
        )
    try:
        x1, y1, x2, y2 = (float(v) for v in box)
    except (TypeError, ValueError):
        raise DataPrepException(
            msg="crop_bbox values must be numbers.",
            status_code=HTTPStatus.BAD_REQUEST,
        )

    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))

    left = max(0, int(round(left)))
    top = max(0, int(round(top)))
    right = min(frame_width, int(round(right)))
    bottom = min(frame_height, int(round(bottom)))

    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def parse_crop_bbox(raw: Optional[str]) -> Optional[List[float]]:
    """Parse a ``"x1,y1,x2,y2"`` query string into four floats (or None)."""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    parts = [p.strip() for p in text.split(",") if p.strip() != ""]
    if len(parts) != 4:
        raise DataPrepException(
            msg="crop_bbox must be four comma-separated numbers: x1,y1,x2,y2.",
            status_code=HTTPStatus.BAD_REQUEST,
        )
    try:
        return [float(p) for p in parts]
    except ValueError:
        raise DataPrepException(
            msg="crop_bbox must contain only numbers.",
            status_code=HTTPStatus.BAD_REQUEST,
        )


def _download_to_temp(bucket_name: str, video_id: str, media_path: Optional[str]) -> pathlib.Path:
    """Materialize the addressed media locally so PyAV can seek it efficiently.

    Byte-range decoding needs random access, so the object is streamed to a temp
    file (bounded memory) rather than held in RAM. Live segments are small; a
    whole uploaded file is read once per request.
    """
    source = resolve_media_source(bucket_name, video_id, media_path=media_path)
    suffix = pathlib.Path(source.filename).suffix or ".mp4"
    tmp = tempfile.NamedTemporaryFile(prefix="frame_", suffix=suffix, delete=False)
    try:
        for chunk in source.stream(bucket_name):
            tmp.write(chunk)
        tmp.flush()
    finally:
        tmp.close()
    return pathlib.Path(tmp.name)


def _decode_frame_at(path: pathlib.Path, timestamp: float):
    """Decode the single frame at/after ``timestamp`` seconds; return (PIL, pts_s)."""
    with av.open(str(path)) as container:
        if not container.streams.video:
            raise DataPrepException(
                msg="Addressed media has no video stream to extract a frame from.",
                status_code=HTTPStatus.BAD_REQUEST,
            )
        stream = container.streams.video[0]
        time_base = stream.time_base

        if timestamp and timestamp > 0 and time_base:
            seek_target = int(timestamp / time_base)
            try:
                container.seek(seek_target, backward=True, stream=stream)
            except (av.FFmpegError, ValueError):
                # Seek can fail on some containers; fall back to decoding from the
                # start, which still lands on the right frame (just slower).
                logger.debug("Seek failed for %s; decoding from start.", path.name)

        chosen = None
        chosen_pts_s: Optional[float] = None
        for frame in container.decode(stream):
            chosen = frame
            chosen_pts_s = float(frame.pts * time_base) if (frame.pts is not None and time_base) else None
            if chosen_pts_s is not None and chosen_pts_s >= timestamp:
                break

        if chosen is None:
            raise DataPrepException(
                msg="Could not decode any frame from the addressed media.",
                status_code=HTTPStatus.BAD_REQUEST,
            )
        return chosen.to_image(), chosen_pts_s


def extract_frame(
    *,
    bucket_name: str,
    video_id: str,
    timestamp: float,
    media_path: Optional[str] = None,
    crop_bbox: Optional[Iterable[float]] = None,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
) -> ExtractedFrame:
    """Decode one frame from stored media and return it as JPEG bytes.

    Args:
        bucket_name: Storage bucket / top-level directory holding the media.
        video_id: Media identifier (an uploaded ``video_id`` or a live ``stream_id``).
        timestamp: Seconds into the addressed media (see module contract).
        media_path: Relative object path inside ``video_id`` (e.g.
            ``"segments/1790655530.mp4"``). Required for live segments; must be
            pre-validated with ``sanitize_media_subpath``.
        crop_bbox: Optional ``[x1, y1, x2, y2]`` pixel box to return just that
            region (the detected-crop variant). Clamped to the frame.
        jpeg_quality: Output JPEG quality (1-100).

    Returns:
        ExtractedFrame with the encoded bytes and descriptive fields.

    Raises:
        DataPrepException: 400 on bad input / undecodable media, 404 when the
            media cannot be resolved (propagated from ``resolve_media_source``).
    """
    if timestamp is None or timestamp < 0:
        raise DataPrepException(
            msg="timestamp must be a non-negative number of seconds.",
            status_code=HTTPStatus.BAD_REQUEST,
        )
    quality = max(_MIN_JPEG_QUALITY, min(_MAX_JPEG_QUALITY, int(jpeg_quality)))

    temp_path = _download_to_temp(bucket_name, video_id, media_path)
    try:
        image, actual_pts = _decode_frame_at(temp_path, float(timestamp))
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Failed to remove temp frame file %s: %s", temp_path, exc)

    if image.mode != "RGB":
        image = image.convert("RGB")

    cropped = False
    if crop_bbox is not None:
        box = _normalize_bbox(crop_bbox, image.width, image.height)
        if box is not None:
            image = image.crop(box)
            cropped = True

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)

    return ExtractedFrame(
        jpeg_bytes=buffer.getvalue(),
        requested_timestamp=float(timestamp),
        actual_timestamp=actual_pts,
        width=image.width,
        height=image.height,
        cropped=cropped,
    )
