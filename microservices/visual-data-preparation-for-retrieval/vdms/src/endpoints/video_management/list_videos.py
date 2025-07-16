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
        objects = minio_client.list_videos_in_bucket(bucket_name=bucket_name)

        video_list: List[VideoInfo] = []
        # Group objects by video_id (assuming format video_id/filename)
        video_map = {}

        for obj in objects:
            # Skip non-video files
            if not minio_client.is_video_object(obj.object_name):
                continue

            parts = obj.object_name.split("/", 1)
            if len(parts) != 2:
                # Skip files not in expected format
                continue

            video_id, video_name = parts
            if video_id not in video_map:
                video_map[video_id] = []
            video_map[video_id].append(
                {
                    "video_name": video_name,
                    "video_path": obj.object_name,
                    "creation_ts": obj.last_modified.isoformat(),
                }
            )

        # Create VideoInfo objects from the grouped data
        for video_id, videos in video_map.items():
            for video in videos:
                video_list.append(
                    VideoInfo(
                        video_id=video_id,
                        video_name=video["video_name"],
                        video_path=video["video_path"],
                        creation_ts=video["creation_ts"],
                    )
                )

        return BucketVideoListResponse(bucket_name=bucket_name, videos=video_list)

    except DataPrepException as ex:
        logger.error(ex)
        raise HTTPException(status_code=ex.status_code, detail=ex.message)
    except Exception as ex:
        logger.error(ex)
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=str(ex))
