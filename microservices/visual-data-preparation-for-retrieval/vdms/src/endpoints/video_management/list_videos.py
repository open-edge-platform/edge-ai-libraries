# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus
from typing import Annotated, List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.common import DataPrepException, logger, settings
from src.common.schema import BucketVideoListResponse, VideoInfo
from src.core.util import get_minio_client
from src.core.validation import validate_params

router = APIRouter(tags=["Video Management APIs"])


@router.get(
    "/videos",
    summary="Get list of videos from Minio storage.",
    response_model_exclude_none=True,
)
@validate_params
async def list_videos(
    bucket_name: Annotated[
        Optional[str],
        Query(
            description="The bucket name where videos are stored. If not provided, default bucket will be used."
        ),
    ] = None,
) -> BucketVideoListResponse:
    """
    ### Get list of videos from Minio storage.

    This endpoint retrieves a list of all videos stored in Minio and returns their information.

    #### Query Params:
    - **bucket_name (str, optional) :** The bucket name where videos are stored. If not provided, default bucket will be used.

    #### Raises:
    - **502 Bad Gateway :** When something unpleasant happens at Minio storage.
    - **500 Internal Server Error :** When some internal error occurs at DataPrep API server.

    Returns:
    - **response (json) :** A response JSON containing list of videos with their information.
    """

    bucket_name = bucket_name or settings.DEFAULT_BUCKET_NAME

    try:
        minio_client = get_minio_client()
        minio_client.ensure_bucket_exists(bucket_name)

        # Get all objects in the bucket
        videos: list[dict] = minio_client.list_all_videos(bucket_name=bucket_name)

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
