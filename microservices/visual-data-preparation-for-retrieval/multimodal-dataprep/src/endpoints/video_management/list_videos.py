# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus
from typing import Annotated, List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.common import DataPrepException, logger, settings
from src.common.api_responses import error_responses
from src.common.schema import BucketVideoListResponse, VideoInfo
from src.core.media_ref import list_referenced_media
from src.core.utils.common_utils import get_minio_client
from src.core.validation import validate_params

router = APIRouter(tags=["Media Management APIs"])


@router.get(
    "/media",
    summary="List stored media (videos and images) in a bucket.",
    operation_id="listMedia",
    response_model=BucketVideoListResponse,
    response_model_exclude_none=True,
    responses=error_responses(
        HTTPStatus.BAD_REQUEST,
        HTTPStatus.INTERNAL_SERVER_ERROR,
    ),
)
@validate_params
async def list_videos(
    bucket_name: Annotated[
        Optional[str],
        Query(
            description="The bucket (object storage) or top-level directory (local storage) holding the media. Defaults to the service's configured bucket when omitted."
        ),
    ] = None,
) -> BucketVideoListResponse:
    """
    ### Get list of stored media from the configured storage backend.

    This endpoint retrieves a list of all media known to the service and returns their
    information. Media ingested by reference (``store_copy=false``) is included and
    flagged with ``stored=false``, carrying its host-visible ``source_path``.

    #### Query Params:
    - **bucket_name (str, optional) :** The bucket name where videos are stored. If not provided, default bucket will be used.

    #### Raises:
    - **502 Bad Gateway :** When the configured storage backend cannot be reached.
    - **500 Internal Server Error :** When some internal error occurs at DataPrep API server.

    Returns:
    - **response (json) :** A response JSON containing list of videos with their information.
    """

    bucket_name = bucket_name or settings.DEFAULT_BUCKET_NAME

    try:
        minio_client = get_minio_client()
        minio_client.ensure_bucket_exists(bucket_name)

        # Get all objects in the bucket, plus media that was ingested by
        # reference (store_copy=false) and so has no object to enumerate.
        videos: list[dict] = minio_client.list_all_videos(bucket_name=bucket_name)
        videos.extend(list_referenced_media(minio_client, bucket_name))

        video_list: List[VideoInfo] = []

        # Create VideoInfo objects from the grouped data
        for video in videos:
            video_list.append(VideoInfo.model_validate(video))

        return BucketVideoListResponse(bucket_name=bucket_name, videos=video_list)

    except DataPrepException as ex:
        logger.error(ex)
        raise HTTPException(status_code=ex.status_code, detail=ex.message)
    except Exception as ex:
        logger.error(ex)
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=str(ex))
