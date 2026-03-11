# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import datetime
from http import HTTPStatus
from typing import Annotated, List

from fastapi import APIRouter, Body, HTTPException
from tzlocal import get_localzone

from src.common import DataPrepException, Strings, logger
from src.common.schema import DataPrepResponse, VideoSummaryRequest
from src.core.embedding import generate_text_embedding
from src.core.utils.common_utils import get_minio_client
from src.core.validation import sanitize_model

router = APIRouter(tags=["Document Processing APIs"])


def verify_params_and_get_video_name(
    bucket_name: str,
    video_id: str,
    video_start_time: float,
    video_end_time: float,
    video_summary: str,
    tags: List[str] = [],
) -> str:
    """
    Verify the parameters and get the video name from the specified bucket and video ID.
    Raises DataPrepException if the video does not exist or parameter verification fails.
    """

    # Validate video time ranges and whether summary text is empty
    if video_start_time < 0:
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST,
            msg="video_start_time must be greater than or equal to 0",
        )

    if video_end_time <= video_start_time:
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST,
            msg="video_end_time must be greater than video_start_time",
        )

    if not video_summary:
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST,
            msg="video_summary cannot be empty",
        )

    # Get the Minio client and ensure the bucket and video_id exists and is valid
    minio_client = get_minio_client()
    minio_client.ensure_bucket_exists(bucket_name)
    video_name = minio_client.get_video_in_directory(bucket_name, video_id, return_prefix=False)
    if not video_name:
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST,
            msg=f"Either video_id '{video_id}' is invalid or no video found in directory '{video_id}' in bucket '{bucket_name}'",
        )

    logger.debug(f"Video '{video_name}' found in bucket '{bucket_name}' in '{video_id}' directory")

    return video_name


@router.post(
    "/summary",
    summary="Process summary text with video timestamp references for embedding generation.",
    status_code=HTTPStatus.CREATED,
    response_model_exclude_none=True,
)
async def process_video_summary(
    summary_request: Annotated[
        VideoSummaryRequest, Body(description="Document processing parameters")
    ]
) -> DataPrepResponse:
    """
    ### Process summary text for a video with video timestamp references for embedding generation.

    This endpoint takes a summary text and video timestamp references, validates that the video exists,
    and stores the text embedding in the VDMS vector database with the associated video metadata.

    #### Body Params:
       - **bucket_name (str) :** The bucket name where the referenced video is stored
       - **video_id (str) :** The video ID (directory) containing the referenced video
       - **video_summary (str) :** The text summary for the video to be embedded
       - **video_start_time (float) :** The start timestamp in seconds for the video or video chunk
       - **video_end_time (float) :** The end timestamp in seconds for the video or video chunk
       - **tags (list(str), optional) :** A list of tags to be associated with the video. Useful for filtering the search.
       
    #### Raises:
    - **400 Bad Request :** If required parameters are missing or invalid.
    - **404 Not Found :** If the specified video cannot be found in Minio.
    - **502 Bad Gateway :** When something unpleasant happens at Minio storage.
    - **500 Internal Server Error :** When some internal error occurs at DataPrep API server.

    Returns:
    - **response (json) :** A response JSON containing status and message.
    """

    try:
        # Validate the request model
        summary_request = sanitize_model(summary_request)

        bucket_name: str = summary_request.bucket_name
        video_id: str = summary_request.video_id
        video_summary: str = summary_request.video_summary
        video_start_time: float = summary_request.video_start_time
        video_end_time: float = summary_request.video_end_time
        tags: List[str] = summary_request.tags or []

        comma_separated_tags: str = ",".join(tags) if tags else ""

        video_name: str = verify_params_and_get_video_name(
            bucket_name, video_id, video_start_time, video_end_time, video_summary, tags
        )

        local_timezone = get_localzone()
        created_at = (
            datetime.datetime.now(datetime.timezone.utc)
            .astimezone(local_timezone)
            .isoformat()
        )

        # Create metadata for summary text
        text_metadata = {
            "bucket_name": bucket_name,
            "video_id": video_id,
            "video_name": video_name,
            "video_start_time": video_start_time,
            "video_end_time": video_end_time,
            "content_type": "text",
            "timestamp": video_start_time,
            "tags": comma_separated_tags,
            "created_at": created_at,
        }

        logger.info(f"Text metadata for summary: {text_metadata}")
        # Process video_summary and generate text embeddings
        ids = await generate_text_embedding(text=video_summary, text_metadata=text_metadata)

        logger.info(f"Text embedding created with ids: {ids}")
        return DataPrepResponse(message="Video summary embedding created successfully")

    except DataPrepException as ex:
        logger.error(ex)
        raise HTTPException(status_code=ex.status_code, detail=ex.message)

    except ValueError as ex:
        logger.error(ex)
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(ex))

    except Exception as ex:
        logger.error(ex)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=Strings.server_error
        )
