# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Path, Query

from src.common import DataPrepException, Strings, logger
from src.common.schema import DataPrepResponse
from src.core.utils.common_utils import get_minio_client
from src.core.validation import validate_params

router = APIRouter(tags=["Video Management APIs"])


@router.delete(
    "/videos/{bucket_name}/{video_id}",
    summary="Delete a video from Minio storage.",
    response_model_exclude_none=True,
)
@validate_params
async def delete_video(
    bucket_name: Annotated[
        str,
        Path(description="The bucket name where the video is stored"),
    ],
    video_id: Annotated[
        str,
        Path(description="The video ID (directory) containing the video to delete"),
    ],
    video_name: Annotated[
        Optional[str],
        Query(
            description="The video filename to delete. If not provided, all videos in the directory will be deleted."
        ),
    ] = None,
) -> DataPrepResponse:
    """
    ### Delete a video from Minio storage.

    This endpoint deletes a video or all videos in a directory from Minio storage.

    #### Path Params:
    - **bucket_name (str, required) :** The bucket name where the video is stored
    - **video_id (str, required) :** The video ID (directory) containing the video to delete

    #### Query Params:
    - **video_name (str, optional) :** The video filename to delete. If not provided, all videos in the directory will be deleted.

    #### Raises:
    - **400 Bad Request :** If required parameters are missing or invalid.
    - **404 Not Found :** If the specified video cannot be found in Minio or no videos exist in the specified directory.
    - **502 Bad Gateway :** When something unpleasant happens at Minio storage.
    - **500 Internal Server Error :** When some internal error occurs at DataPrep API server.

    Returns:
    - **response (json) :** A response JSON containing status and message.
    """

    try:
        minio_client = get_minio_client()

        if not minio_client.bucket_exists(bucket_name):
            raise DataPrepException(
                status_code=HTTPStatus.NOT_FOUND,
                msg=f"Bucket '{bucket_name}' not found",
            )

        if video_name:
            # Delete a specific video file
            object_name = f"{video_id}/{video_name}"
            if not minio_client.object_exists_by_path(bucket_name, object_name):
                raise DataPrepException(
                    status_code=HTTPStatus.NOT_FOUND,
                    msg=f"Video '{object_name}' not found in bucket '{bucket_name}'",
                )

            minio_client.delete_object(bucket_name, object_name)
            logger.info(f"Deleted video {object_name} from bucket {bucket_name}")
            return DataPrepResponse(message=f"Video {video_name} deleted successfully")
        else:
            # Delete all videos in the directory
            objects = minio_client.list_objects_in_directory(bucket_name, video_id)
            if not objects:
                raise DataPrepException(
                    status_code=HTTPStatus.NOT_FOUND,
                    msg=f"No videos found in directory '{video_id}' in bucket '{bucket_name}'",
                )

            for obj in objects:
                minio_client.delete_object(bucket_name, obj.object_name)

            logger.info(f"Deleted all videos in directory {video_id} from bucket {bucket_name}")
            return DataPrepResponse(
                message=f"All videos in directory {video_id} deleted successfully"
            )

    except DataPrepException as ex:
        logger.error(ex)
        raise HTTPException(status_code=ex.status_code, detail=ex.message)
    except Exception as ex:
        logger.error(f"Error deleting video: {ex}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=Strings.server_error
        )
