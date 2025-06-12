# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus
from typing import Annotated, Optional

from fastapi import APIRouter, File, Query, UploadFile

from src.common import logger
from src.common.schema import DataPrepResponse, VideoRequest

from .process_minio_video import process_minio_video
from .upload_and_process_video import upload_and_process_video

router = APIRouter(tags=["Video Processing APIs"])


@router.post(
    "/videos",
    summary="(Legacy Endpoint) Process video parameters for DataPrep service.",
    status_code=HTTPStatus.CREATED,
    response_model_exclude_none=True,
    deprecated=True,
)
async def prep_data(
    bucket_name: Annotated[
        Optional[str],
        Query(description="The bucket name where the video is stored"),
    ] = None,
    video_id: Annotated[
        Optional[str],
        Query(description="The video ID (directory) containing the video"),
    ] = None,
    video_name: Annotated[
        Optional[str],
        Query(
            description="The video filename within the video_id directory (if omitted, first video found is used)"
        ),
    ] = None,
    chunk_duration: Annotated[
        Optional[int],
        Query(ge=3, description="Interval of time in seconds for video chunking"),
    ] = None,
    clip_duration: Annotated[
        Optional[int],
        Query(ge=3, description="Length of clip in seconds for embedding selection"),
    ] = None,
    file: Annotated[
        Optional[UploadFile | str], File(description="Video file to upload (MP4 format only)")
    ] = None,
) -> DataPrepResponse:
    """
    ### Legacy Endpoint: Please use /videos/upload to create embeddings by uploading videos or /videos/minio to create embeddings by getting videos from MINIO storage.

    ## Processes videos stored in Minio using the provided parameters or directly from an uploaded file. (DEPRECATED)

    You can either upload a video file directly or provide Minio parameters to process an existing video.
    If both are provided, the uploaded file takes precedence.

    Video is divided into different chunks having length equal to chunk_duration value. Embeddings are
    created and stored for uniformly sampled frames inside a clip (having length equal to clip_duration),
    occurring in each chunk.

    #### Query Params:
    - **bucket_name (str, optional) :** The bucket name where the video is stored (If not provided, a default bucket name will be used based on application config.)
    - **video_id (str, optional) :** The video ID (directory) containing the video (required if no file is uploaded)
    - **video_name (str, optional) :** The video filename within the video_id directory (if omitted, first video found is used)
    - **chunk_duration (int, optional) :** Interval of time in seconds for video chunking (default: 30)
    - **clip_duration (int, optional) :** Length of clip in seconds for embedding selection (default: 10)

    #### File Upload:
    - **file (UploadFile, optional) :** Video file to upload (MP4 format only, max size 500MB)
      When a file is uploaded, Minio parameters (bucket_name, video_id) are optional. Uploaded files are
      processed and then stored in Minio with an object name format of `{request_id}/{filename}` for future reference.

    #### Raises:
    - **400 Bad Request :** If video files are not .mp4 or fail any validation error.
    - **413 Request Entity Too Large :** If uploaded file exceeds the 500MB limit.
    - **502 Bad Gateway :** When Something unpleasant happens at Minio storage.
    - **500 Internal Server Error :** When some internal error occurs at DataPrep API server.

    Returns:
    - **response (json) :** A response JSON containing status and message.
    """
    logger.warning(
        "The /videos endpoint is deprecated. Please use /videos/upload or /videos/minio instead."
    )

    # Redirect to the appropriate endpoint based on whether a file is provided
    if file:
        # Redirect to file upload endpoint with the query parameters
        return await upload_and_process_video(
            file=file,
            bucket_name=bucket_name,
            chunk_duration=chunk_duration,
            clip_duration=clip_duration,
        )
    else:
        # Create a VideoRequest object and redirect to Minio endpoint
        video_request = VideoRequest(
            bucket_name=bucket_name,
            video_id=video_id,
            video_name=video_name,
            chunk_duration=chunk_duration,
            clip_duration=clip_duration,
        )

        # Redirect to Minio endpoint with the created VideoRequest object
        return await process_minio_video(video_request=video_request)
