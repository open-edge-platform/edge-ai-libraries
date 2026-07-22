# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path

from src.common import DataPrepException, Strings, logger, sanitize_for_log
from src.common.schema import DataPrepResponse
from src.core.dedup import remove_dedup_marker
from src.core.utils.common_utils import get_minio_client
from src.core.validation import validate_params
from src.core.vectorstores.factory import get_vector_store

router = APIRouter(tags=["Video Management APIs"])


def _delete_video_embeddings(bucket_name: str, video_id: str) -> None:
    """Delete a video's embeddings from the active vector DB backend.

    Removing the storage object(s) alone would leave orphaned vectors that a
    retriever could still surface, so deletion must span both stores. The vector
    delete is keyed on ``bucket_name`` + ``video_id`` (present on every embedding
    type) and is performed BEFORE the storage delete by the caller, so a failure
    here aborts the request without leaving orphaned vectors behind.

    Args:
        bucket_name: The bucket the video was ingested under.
        video_id: The video directory / identifier whose vectors to remove.

    Raises:
        DataPrepException: If the vector-store delete fails (mapped to 502).
    """
    try:
        vector_store = get_vector_store()
        vector_store.delete_embeddings(bucket_name, video_id)
        logger.info(
            "Deleted embeddings for video %s in bucket %s from vector DB",
            sanitize_for_log(video_id, max_length=128),
            sanitize_for_log(bucket_name, max_length=128),
        )
    except Exception as ex:
        logger.error("Error deleting embeddings from vector DB: %s", ex)
        raise DataPrepException(
            status_code=HTTPStatus.BAD_GATEWAY,
            msg=Strings.vectordb_delete_error,
        )


@router.delete(
    "/videos/{bucket_name}/{video_id}",
    summary="Delete a video from storage and its embeddings from the vector DB.",
    operation_id="deleteVideo",
    response_model=DataPrepResponse,
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
) -> DataPrepResponse:
    """
    ### Delete a video from storage and its embeddings from the vector DB.

    This endpoint deletes a video (the single file under a ``video_id`` directory)
    from the active storage backend AND removes the corresponding embeddings from
    the active vector DB, keeping both stores consistent. Embeddings are removed
    first so a failure never leaves orphaned vectors behind.

    #### Path Params:
    - **bucket_name (str, required) :** The bucket name where the video is stored
    - **video_id (str, required) :** The video ID (directory) containing the video to delete

    #### Raises:
    - **400 Bad Request :** If required parameters are missing or invalid.
    - **404 Not Found :** If no video exists in the specified directory.
    - **502 Bad Gateway :** When something unpleasant happens at the storage backend or vector DB.
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

        # Delete every object under the video_id directory (one video per directory).
        objects = minio_client.list_objects_in_directory(bucket_name, video_id)
        if not objects:
            raise DataPrepException(
                status_code=HTTPStatus.NOT_FOUND,
                msg=f"No videos found in directory '{video_id}' in bucket '{bucket_name}'",
            )

        # Vectors first: abort before touching storage if the vector delete fails.
        _delete_video_embeddings(bucket_name, video_id)

        # Remove the dedup forward marker so identical content can be re-uploaded
        # after this video is deleted (best-effort; never blocks the delete).
        remove_dedup_marker(minio_client, bucket_name, video_id)

        for obj in objects:
            minio_client.delete_object(bucket_name, obj.object_name)

        logger.info(
            "Deleted video %s from bucket %s",
            sanitize_for_log(video_id, max_length=128),
            sanitize_for_log(bucket_name, max_length=128),
        )
        return DataPrepResponse(message=f"Video {video_id} deleted successfully")

    except DataPrepException as ex:
        logger.error(ex)
        raise HTTPException(status_code=ex.status_code, detail=ex.message)
    except Exception as ex:
        logger.error(f"Error deleting video: {ex}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=Strings.server_error
        )
