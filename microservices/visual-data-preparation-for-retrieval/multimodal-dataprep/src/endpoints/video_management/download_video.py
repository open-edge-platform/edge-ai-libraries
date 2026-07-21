# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Video download / streaming endpoint.

Serves ``GET /videos/download`` from the active storage backend (MinIO or local
filesystem) with HTTP Range support, so media players can seek without fetching
the whole file. Ranges are read directly from storage (server-side range read on
MinIO, seek/read on local), keeping large videos out of memory.
"""

from http import HTTPStatus
from typing import Annotated, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from src.common import DataPrepException, Strings, logger, settings
from src.core.utils.common_utils import get_minio_client
from src.core.utils.video_utils import resolve_video_object
from src.core.validation import validate_params

router = APIRouter(tags=["Video Management APIs"])


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
    "/videos/download",
    summary="Download or stream a video (supports HTTP Range/seek).",
    operation_id="downloadVideo",
    response_class=StreamingResponse,
    responses={
        HTTPStatus.OK: {
            "description": "Full video stream response",
            "content": {"video/mp4": {"schema": {"type": "string", "format": "binary"}}},
        },
        HTTPStatus.PARTIAL_CONTENT: {
            "description": "Partial video stream response (byte range).",
            "content": {"video/mp4": {"schema": {"type": "string", "format": "binary"}}},
        },
        HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE: {
            "description": "The requested byte range cannot be satisfied.",
        },
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
            description="The bucket name where the video is stored. If not provided, default bucket will be used."
        ),
    ] = None,
    video_name: Annotated[
        Optional[str],
        Query(
            description="The video filename to download. If not provided, the first video in the directory will be used."
        ),
    ] = None,
    download: Annotated[
        bool,
        Query(description="Set to true to download the file instead of streaming it"),
    ] = False,
) -> StreamingResponse:
    """
    ### Download or stream a video from storage.

    Streams a video from the active storage backend (MinIO or local filesystem).
    The endpoint advertises ``Accept-Ranges: bytes`` and honours the HTTP
    ``Range`` request header, so media players can **seek** without downloading
    the whole file:

    - No ``Range`` header -> ``200 OK`` with the full body.
    - Valid ``Range`` header -> ``206 Partial Content`` with ``Content-Range``.
    - Unsatisfiable ``Range`` -> ``416 Range Not Satisfiable``.

    #### Query Params:
    - **video_id (str, required) :** The video ID (directory) containing the video to download.
    - **bucket_name (str, optional) :** The bucket where the video is stored. Defaults to the configured bucket.
    - **video_name (str, optional) :** The video filename. If omitted, the first video in the directory is used.
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
        storage = get_minio_client()

        # Resolve the concrete object + size without downloading it.
        object_name, filename = resolve_video_object(bucket_name, video_id, video_name)
        file_size = storage.get_object_size(bucket_name, object_name)

        content_disposition = (
            f"attachment; filename={filename}" if download else f"inline; filename={filename}"
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
                content=storage.stream_object_range(bucket_name, object_name),
                media_type="video/mp4",
                headers=base_headers,
            )

        start, end = byte_range
        length = end - start + 1
        base_headers["Content-Length"] = str(length)
        base_headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        return StreamingResponse(
            content=storage.stream_object_range(
                bucket_name, object_name, offset=start, length=length
            ),
            status_code=HTTPStatus.PARTIAL_CONTENT,
            media_type="video/mp4",
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
