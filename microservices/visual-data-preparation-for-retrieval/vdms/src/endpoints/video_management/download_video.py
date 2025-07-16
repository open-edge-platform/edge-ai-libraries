# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from src.common import DataPrepException, Strings, logger, settings
from src.core.util import get_video_from_minio
from src.core.validation import validate_params

router = APIRouter(tags=["Video Management APIs"])


@router.get(
    "/videos/download",
    summary="Download a video from Minio storage.",
    response_model_exclude_none=True,
)
@validate_params
async def download_video(
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
    ### Download a video from Minio storage.

    This endpoint retrieves a video from Minio storage and returns it as a stream.

    #### Query Params:
    - **video_id (str, required) :** The video ID (directory) containing the video to download
    - **bucket_name (str, optional) :** The bucket name where the video is stored. If not provided, default bucket will be used.
    - **video_name (str, optional) :** The video filename to download. If not provided, the first video in the directory will be used.
    - **download (bool, optional) :** Set to true to download the file instead of streaming it

    #### Raises:
    - **400 Bad Request :** If required parameters are missing or invalid.
    - **404 Not Found :** If the specified video cannot be found in Minio or no videos exist in the specified directory.
    - **502 Bad Gateway :** When something unpleasant happens at Minio storage.
    - **500 Internal Server Error :** When some internal error occurs at DataPrep API server.

    Returns:
    - **response (stream) :** The video file as a stream.
    """

    bucket_name = bucket_name or settings.DEFAULT_BUCKET_NAME

    try:
        # Get the video data from Minio
        data, filename = get_video_from_minio(bucket_name, video_id, video_name)

        # Determine content-disposition header based on download flag
        content_disposition = (
            f"attachment; filename={filename}" if download else f"inline; filename={filename}"
        )

        # Return the video as a streaming response
        return StreamingResponse(
            content=data,
            media_type="video/mp4",
            headers={"Content-Disposition": content_disposition},
        )

    except DataPrepException as ex:
        logger.error(ex)
        raise HTTPException(status_code=ex.status_code, detail=ex.message)
    except Exception as ex:
        logger.error(f"Error downloading video: {ex}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=Strings.server_error
        )
