# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Single-frame retrieval endpoint.

Serves ``GET /media/frame``: reconstruct one frame from already-stored media
(an uploaded file or a live ``segments/<ts>.mp4`` clip) and return it as JPEG
bytes or as base64 inside JSON. Frames are decoded on demand and never written
back to storage, so this adds no persistent footprint.

The endpoint is deliberately **query-agnostic**: it addresses a frame purely by
location + time (+ an optional crop box). The search service already identifies
*which* frame matters (e.g. the peak-scoring frame of a segment) and supplies the
address; downstream consumers (a VLM re-verification agent, the UI) fetch the
pixels here.
"""

import base64
from http import HTTPStatus
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from src.common import DataPrepException, Strings, logger, settings
from src.common.api_responses import error_responses
from src.core.frame_capture import (
    DEFAULT_JPEG_QUALITY,
    extract_frame,
    parse_crop_bbox,
)
from src.core.validation import sanitize_media_subpath, validate_params

router = APIRouter(tags=["Media Management APIs"])


class FrameMetadata(BaseModel):
    """Describes the frame returned by ``GET /media/frame`` (JSON variant)."""

    video_id: str
    bucket_name: str
    media_path: Optional[str] = Field(
        default=None, description="Segment object addressed for live media, if any."
    )
    requested_timestamp: float = Field(
        description="Timestamp requested, in seconds from the start of the addressed media."
    )
    actual_timestamp: Optional[float] = Field(
        default=None,
        description="Timestamp of the frame actually returned (nearest decodable at/after the request).",
    )
    variant: str = Field(description="'full' for the whole frame or 'crop' for a bounding-box region.")
    width: int
    height: int
    cropped: bool = Field(description="Whether a crop box was applied.")


class FrameJsonResponse(BaseModel):
    """JSON wrapper returning the frame as base64 plus its metadata."""

    mime: str = Field(default="image/jpeg", description="Media type of the encoded image.")
    image_base64: str = Field(description="Base64-encoded JPEG bytes (no data-URL prefix).")
    frame: FrameMetadata


def _frame_headers(width: int, height: int, requested: float, actual: Optional[float], variant: str) -> dict:
    """Expose frame facts as response headers for the raw-image variant."""
    headers = {
        "X-Frame-Requested-Timestamp": str(requested),
        "X-Frame-Width": str(width),
        "X-Frame-Height": str(height),
        "X-Frame-Variant": variant,
        "Cache-Control": "no-store",
    }
    if actual is not None:
        headers["X-Frame-Actual-Timestamp"] = str(actual)
    return headers


@router.get(
    "/media/frame",
    summary="Extract one frame from stored media (full frame or detected-crop region).",
    operation_id="getMediaFrame",
    responses={
        HTTPStatus.OK: {
            "description": (
                "The decoded frame. Returns raw image/jpeg bytes by default, or a "
                "JSON object with base64 image + metadata when format=json."
            ),
            "content": {
                "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
                "application/json": {"schema": FrameJsonResponse.model_json_schema()},
            },
        },
        **error_responses(
            HTTPStatus.BAD_REQUEST,
            HTTPStatus.NOT_FOUND,
            HTTPStatus.INTERNAL_SERVER_ERROR,
        ),
    },
)
@validate_params
async def get_media_frame(
    video_id: Annotated[
        str,
        Query(description="Media identifier: an uploaded video_id or a live stream_id."),
    ],
    timestamp: Annotated[
        float,
        Query(
            ge=0,
            description=(
                "Seconds from the start of the addressed media. For an uploaded video this is the "
                "position within the file; for a live stream it is the offset within the segment named "
                "by media_path. Pass the search result's best_frame_info.timestamp here."
            ),
        ),
    ],
    bucket_name: Annotated[
        Optional[str],
        Query(description="Bucket/top-level directory holding the media. Defaults to the configured bucket."),
    ] = None,
    media_path: Annotated[
        Optional[str],
        Query(
            description=(
                "Relative object path inside the video_id directory, e.g. 'segments/1790655530.mp4'. "
                "Required for live-stream frames (stored under <stream_id>/segments/)."
            )
        ),
    ] = None,
    variant: Annotated[
        str,
        Query(
            pattern="^(full|crop)$",
            description="'full' returns the whole frame; 'crop' returns the crop_bbox region.",
        ),
    ] = "full",
    crop_bbox: Annotated[
        Optional[str],
        Query(
            description=(
                "Pixel box 'x1,y1,x2,y2' for variant=crop. Supply the detection box captured at ingest "
                "(search result best_frame_info.crop_bbox). Ignored when variant=full."
            )
        ),
    ] = None,
    frame_format: Annotated[
        str,
        Query(
            alias="format",
            pattern="^(image|json)$",
            description="'image' returns raw image/jpeg (default); 'json' returns base64 + metadata.",
        ),
    ] = "image",
    quality: Annotated[
        int,
        Query(ge=1, le=100, description="Output JPEG quality (1-100)."),
    ] = DEFAULT_JPEG_QUALITY,
) -> Response:
    """
    ### Extract a single frame from stored media.

    Decodes exactly one frame on demand (no stored JPEGs). Typical flow for a
    downstream agent:

    1. Run a search; each result carries ``best_frame_info`` (the peak-scoring
       frame) with ``timestamp``, ``bucket_name``, ``is_live``/``media_path`` and,
       for detections, ``crop_bbox``.
    2. Call this endpoint with those values to fetch the exact frame.

    #### Query Params:
    - **video_id (str, required):** Uploaded ``video_id`` or live ``stream_id``.
    - **timestamp (float, required):** Seconds into the addressed media (see note above).
    - **bucket_name (str, optional):** Defaults to the configured bucket.
    - **media_path (str, optional):** Segment object for live media (required for live).
    - **variant (str, optional):** ``full`` (default) or ``crop``.
    - **crop_bbox (str, optional):** ``x1,y1,x2,y2`` for ``variant=crop``.
    - **format (str, optional):** ``image`` (raw JPEG, default) or ``json`` (base64 + metadata).
    - **quality (int, optional):** JPEG quality 1-100 (default 90).

    #### Raises:
    - **400 Bad Request:** Invalid params or undecodable media.
    - **404 Not Found:** Media/segment cannot be resolved.
    - **500 Internal Server Error:** On an internal error.
    """
    bucket_name = bucket_name or settings.DEFAULT_BUCKET_NAME

    try:
        media_path = sanitize_media_subpath(media_path)
        bbox = parse_crop_bbox(crop_bbox) if variant == "crop" else None

        frame = extract_frame(
            bucket_name=bucket_name,
            video_id=video_id,
            timestamp=float(timestamp),
            media_path=media_path,
            crop_bbox=bbox,
            jpeg_quality=quality,
        )
    except DataPrepException as ex:
        logger.error(ex)
        raise HTTPException(status_code=ex.status_code, detail=ex.message)
    except HTTPException:
        raise
    except Exception as ex:
        logger.error(f"Error extracting frame: {ex}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=Strings.server_error
        )

    if frame_format == "json":
        payload = FrameJsonResponse(
            mime="image/jpeg",
            image_base64=base64.b64encode(frame.jpeg_bytes).decode("ascii"),
            frame=FrameMetadata(
                video_id=video_id,
                bucket_name=bucket_name,
                media_path=media_path,
                requested_timestamp=frame.requested_timestamp,
                actual_timestamp=frame.actual_timestamp,
                variant=variant,
                width=frame.width,
                height=frame.height,
                cropped=frame.cropped,
            ),
        )
        return Response(
            content=payload.model_dump_json(),
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
        )

    return Response(
        content=frame.jpeg_bytes,
        media_type="image/jpeg",
        headers=_frame_headers(
            frame.width, frame.height, frame.requested_timestamp, frame.actual_timestamp, variant
        ),
    )
