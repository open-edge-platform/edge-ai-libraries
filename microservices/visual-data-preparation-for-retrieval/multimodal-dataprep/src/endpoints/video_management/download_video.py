# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Media download / streaming endpoint.

Serves ``GET /media/download`` from the active storage backend (MinIO or local
filesystem) with HTTP Range support, so media players can seek without fetching
the whole file. Ranges are read directly from storage (server-side range read on
MinIO, seek/read on local), keeping large media out of memory.

Media ingested by reference (``store_copy=false``) has no stored object; it is
resolved to its file on the ingest mount and served with the same Range logic.
"""

from http import HTTPStatus
from typing import Annotated, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from src.common import DataPrepException, Strings, logger, settings
from src.common.api_responses import error_responses
from src.core.media import content_type_for_filename
from src.core.utils.video_utils import resolve_media_source
from src.core.validation import validate_params

router = APIRouter(tags=["Media Management APIs"])


class _RangeNotSatisfiable(Exception):
    """Raised when a syntactically valid Range cannot be satisfied for the object."""


def _parse_byte_range(range_header: str, file_size: int) -> Optional[Tuple[int, int]]:
    """Parse a single HTTP ``Range`` header into inclusive ``(start, end)`` bytes.

    Only a single byte range is supported (sufficient for media seeking). A
    syntactically invalid header returns ``None`` so the caller serves the full
    body (per RFC 7233, an unparsable Range is ignored). A valid-but-unsatisfiable
    range (e.g. start beyond EOF) raises :class:`_RangeNotSatisfiable` (HTTP 416).

    Args:
        range_header: Raw ``Range`` header value (e.g. ``"bytes=0-1023"``).
        file_size: Total object size in bytes.

    Returns:
        ``(start, end)`` inclusive byte offsets, or ``None`` to serve the full body.
    """
    value = (range_header or "").strip()
    if not value.lower().startswith("bytes="):
        return None

    spec = value[len("bytes=") :].strip()
    # Multiple ranges are not supported; fall back to full body.
    if "," in spec or "-" not in spec:
        return None

    start_str, _, end_str = spec.partition("-")
    start_str, end_str = start_str.strip(), end_str.strip()

    try:
        if start_str == "":
            # Suffix range: last N bytes (bytes=-N).
            if end_str == "":
                return None
            suffix = int(end_str)
            if suffix <= 0:
                raise _RangeNotSatisfiable()
            start = max(0, file_size - suffix)
            end = file_size - 1
        else:
            start = int(start_str)
            end = int(end_str) if end_str != "" else file_size - 1
    except ValueError:
        return None

    if start < 0 or end < 0:
        return None
    if file_size == 0 or start >= file_size:
        raise _RangeNotSatisfiable()
    if start > end:
        return None

    # Clamp end to the last available byte.
    end = min(end, file_size - 1)
    return start, end


@router.get(
    "/media/download",
    summary="Download or stream stored media, video or image (supports HTTP Range/seek).",
    operation_id="downloadMedia",
    response_class=StreamingResponse,
    responses={
        HTTPStatus.OK: {
            "description": (
                "Full media stream. The Content-Type reflects the stored media "
                "(for example video/mp4 or image/jpeg)."
            ),
            "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
        },
        HTTPStatus.PARTIAL_CONTENT: {
            "description": "Partial media stream (byte range).",
            "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
        },
        **error_responses(
            HTTPStatus.BAD_REQUEST,
            HTTPStatus.NOT_FOUND,
            HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE,
            HTTPStatus.INTERNAL_SERVER_ERROR,
        ),
    },
    response_model_exclude_none=True,
)
@validate_params
async def download_video(
    request: Request,
    video_id: Annotated[
        str,
        Query(description="The video ID (directory) containing the video to download"),
    ],
    bucket_name: Annotated[
        Optional[str],
        Query(
            description="The bucket (object storage) or top-level directory (local storage) holding the media. Defaults to the service's configured bucket when omitted."
        ),
    ] = None,
    download: Annotated[
        bool,
        Query(description="Set to true to download the file instead of streaming it"),
    ] = False,
) -> StreamingResponse:
    """
    ### Download or stream a video from storage.

    Streams stored media from the active storage backend (object storage or local filesystem).
    The endpoint advertises ``Accept-Ranges: bytes`` and honours the HTTP
    ``Range`` request header, so media players can **seek** without downloading
    the whole file:

    - No ``Range`` header -> ``200 OK`` with the full body.
    - Valid ``Range`` header -> ``206 Partial Content`` with ``Content-Range``.
    - Unsatisfiable ``Range`` -> ``416 Range Not Satisfiable``.

    Media ingested by reference (``store_copy=false``) is served too: it has no
    stored object, so it is read from its file on the ingest mount instead.

    #### Query Params:
    - **video_id (str, required) :** The video ID (directory) containing the video to download.
    - **bucket_name (str, optional) :** The bucket where the video is stored. Defaults to the configured bucket.
    - **download (bool, optional) :** Set to true to force a file download (``attachment``) instead of inline streaming.

    #### Raises:
    - **400 Bad Request :** If required parameters are missing or invalid.
    - **404 Not Found :** If the specified video cannot be found.
    - **416 Range Not Satisfiable :** If the requested byte range is invalid for the object.
    - **500 Internal Server Error :** On an internal error.

    Returns:
    - **response (stream) :** The (partial or full) video file as a stream.
    """

    bucket_name = bucket_name or settings.DEFAULT_BUCKET_NAME
    file_size = 0

    try:
        # Resolve the concrete media + size without downloading it. This covers
        # both stored objects and media referenced in place on the ingest mount.
        source = resolve_media_source(bucket_name, video_id)
        file_size = source.size(bucket_name)
        # Serve the media with its real MIME type (video/mp4, image/png, ...)
        # derived from the filename extension.
        media_type = content_type_for_filename(source.filename)

        content_disposition = (
            f"attachment; filename={source.filename}"
            if download
            else f"inline; filename={source.filename}"
        )
        base_headers = {
            "Content-Disposition": content_disposition,
            "Accept-Ranges": "bytes",
        }

        range_header = request.headers.get("range")
        byte_range = _parse_byte_range(range_header, file_size) if range_header else None

        if byte_range is None:
            # Full-body response (also served when no/invalid Range header).
            base_headers["Content-Length"] = str(file_size)
            return StreamingResponse(
                content=source.stream(bucket_name),
                media_type=media_type,
                headers=base_headers,
            )

        start, end = byte_range
        length = end - start + 1
        base_headers["Content-Length"] = str(length)
        base_headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        return StreamingResponse(
            content=source.stream(bucket_name, offset=start, length=length),
            status_code=HTTPStatus.PARTIAL_CONTENT,
            media_type=media_type,
            headers=base_headers,
        )

    except _RangeNotSatisfiable:
        return Response(
            status_code=HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={
                "Content-Range": f"bytes */{file_size}",
                "Accept-Ranges": "bytes",
            },
        )
    except DataPrepException as ex:
        logger.error(ex)
        raise HTTPException(status_code=ex.status_code, detail=ex.message)
    except Exception as ex:
        logger.error(f"Error downloading video: {ex}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=Strings.server_error
        )
