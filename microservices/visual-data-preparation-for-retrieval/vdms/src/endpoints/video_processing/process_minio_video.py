# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import datetime
import pathlib
import shutil
from http import HTTPStatus
from typing import Annotated, List

from fastapi import APIRouter, Body, HTTPException

from src.common import DataPrepException, Strings, logger, settings
from src.common.schema import DataPrepResponse, VideoRequest
from src.core.embedding import generate_video_embedding
from src.core.util import get_minio_client, get_video_from_minio, read_config
from src.core.validation import sanitize_model

router = APIRouter(tags=["Video Processing APIs"])


def _validate_and_get_video_name(
    bucket_name: str,
    video_id: str,
    video_name: str = None,
) -> str:
    """
    Validate the parameters and get the video name from the specified bucket and video ID.
    If video_name is provided, it checks if the video exists in the specified bucket and directory.
    If video_name is not provided, it attempts to find the first MP4 video in the specified directory.

    Raises DataPrepException if the video does not exist or parameter verification fails.
    """

    # Validate required parameters
    if not bucket_name or not video_id:
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST,
            msg="Both bucket_name and video_id must be provided.",
        )

    # Get the Minio client and ensure the bucket exists
    minio_client = get_minio_client()
    minio_client.ensure_bucket_exists(bucket_name)

    # If video_name is not provided, try to get it from the directory
    if not video_name:
        logger.info(f"Video name not provided, attempting to find video in directory {video_id}")
        object_name = minio_client.get_video_in_directory(bucket_name, video_id)
        if not object_name:
            raise DataPrepException(
                status_code=HTTPStatus.NOT_FOUND,
                msg=f"No video found in directory '{video_id}' in bucket '{bucket_name}'",
            )
        # Extract just the filename part
        video_name = pathlib.Path(object_name).name
        logger.debug(f"Found video: {video_name} in directory {video_id}")

    else:
        if not minio_client.object_exists(bucket_name, video_id, video_name):
            raise DataPrepException(
                status_code=HTTPStatus.NOT_FOUND,
                msg=f"Video '{video_id}/{video_name}' not found in bucket '{bucket_name}'",
            )

        if not minio_client.validate_object_name(video_id, video_name):
            raise DataPrepException(
                status_code=HTTPStatus.BAD_REQUEST,
                msg=f"Invalid video name '{video_name}' in directory '{video_id}'",
            )

    return video_name


@router.post(
    "/videos/minio",
    summary="Process video from Minio storage for embedding generation.",
    status_code=HTTPStatus.CREATED,
    response_model_exclude_none=True,
)
async def process_minio_video(
    video_request: Annotated[VideoRequest, Body(description="Video processing parameters")],
) -> DataPrepResponse:
    """
    ### Processes videos stored in Minio using the provided parameters.

    Video is divided into different chunks having length equal to chunk_duration value. Embeddings are
    created and stored for uniformly sampled frames inside a clip (having length equal to clip_duration),
    occurring in each chunk.

    ***For example:** Given a video of 30s in total length, with chunk_duration = 10 and clip_duration = 5,
    embeddings will be created for uniformly sampled frames from first 5 sec clip (defined by clip_duration)
    in each of the three chunks. Three chunks would be created because total length of video is 30s and duration
    of every chunk is 10s (defined by chunk_duration). **Number of chunks = int(total length of video in sec / chunk_duration)***

    #### Body Params:
    - **video_request (VideoRequest) :** Contains processing parameters:
       - **bucket_name (str) :** The bucket name where the video is stored (If not provided, a default bucket name will be used based on application config.)
       - **video_id (str) :** The video ID (directory) containing the video (required)
       - **video_name (str, optional) :** The video filename within the video_id directory (if omitted, the first MP4 video found in the directory will be used automatically)
       - **chunk_duration (int) :** Interval of time in seconds for video chunking (default: 30)
       - **clip_duration (int) :** Length of clip in seconds for embedding selection (default: 10)
       - **tags (list(str), optional) :** A list of tags to be associated with the video. Useful for filtering the search.

    #### Raises:
    - **400 Bad Request :** If required parameters are missing or invalid.
    - **404 Not Found :** If the specified video cannot be found in Minio or no videos exist in the specified directory.
    - **502 Bad Gateway :** When something unpleasant happens at Minio storage.
    - **500 Internal Server Error :** When some internal error occurs at DataPrep API server.

    Returns:
    - **response (json) :** A response JSON containing status and message.
    """

    try:
        config = read_config(settings.CONFIG_FILEPATH, type="yaml")

        # Not able to read config file is a fatal error.
        if config is None:
            raise Exception(Strings.config_error)

        # Get directory paths from config file
        videos_temp_dir = pathlib.Path(config.get("videos_local_temp_dir", "/tmp/dataprep/videos"))
        metadata_temp_dir = pathlib.Path(
            config.get("metadata_local_temp_dir", "/tmp/dataprep/metadata")
        )

        # Sanitize the video request model
        video_request = sanitize_model(video_request)

        # Get parameters from video_request, fall back to config for some, if not specified
        bucket_name = video_request.bucket_name
        video_id = video_request.video_id
        video_name = video_request.video_name
        chunk_duration = video_request.chunk_duration or config.get("chunk_duration", 30)
        clip_duration = video_request.clip_duration or config.get("clip_duration", 10)
        tags: List[str] = video_request.tags or []

        # Validate the provided minio parameters and get the video name, if not provided
        video_name = _validate_and_get_video_name(
            bucket_name=bucket_name,
            video_id=video_id,
            video_name=video_name,
        )

        # Create a unique subdirectory for this request using video_id to avoid conflicts
        request_timestamp = int(datetime.datetime.now().timestamp())
        request_id = f"{video_id}_{request_timestamp}"
        videos_temp_dir = videos_temp_dir / request_id
        metadata_temp_dir = metadata_temp_dir / request_id

        # create the temp directories
        videos_temp_dir.mkdir(parents=True, exist_ok=True)
        metadata_temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Download video from Minio to process it
            logger.info(
                f"Retrieving video from Minio at bucket: {bucket_name}, video_id: {video_id}"
            )
            video_data, filename = get_video_from_minio(bucket_name, video_id, video_name)

            # Save video to temporary location for processing
            temp_video_path = videos_temp_dir / filename
            with open(temp_video_path, "wb") as f:
                f.write(video_data.read())

            # Reset video_data for potential reuse
            video_data.seek(0)

            logger.info(f"Retrieved video {filename} from {bucket_name}/{video_id}")

        except Exception as ex:
            logger.error(f"Error retrieving video from Minio: {ex}")
            raise DataPrepException(status_code=HTTPStatus.BAD_GATEWAY, msg=Strings.minio_error)

        # Process video metadata and generate video embeddings
        ids = await generate_video_embedding(
            bucket_name=bucket_name,
            video_id=video_id,
            filename=filename,
            temp_video_path=temp_video_path,
            metadata_temp_path=metadata_temp_dir,
            chunk_duration=chunk_duration,
            clip_duration=clip_duration,
            tags=tags,
        )

        logger.info(f"Embeddings created for videos: {ids}")
        return DataPrepResponse(message=Strings.embedding_success)

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

    finally:
        # Clean up unique request directory if it exists
        try:
            # Only remove specific request directories we created, not the base directories
            if (
                "request_id" in locals()
                and "videos_temp_dir" in locals()
                and videos_temp_dir.exists()
            ):
                shutil.rmtree(videos_temp_dir, ignore_errors=True)
            if (
                "request_id" in locals()
                and "metadata_temp_dir" in locals()
                and metadata_temp_dir.exists()
            ):
                shutil.rmtree(metadata_temp_dir, ignore_errors=True)
        except Exception as ex:
            logger.error(f"Error cleaning up temporary directories: {ex}")
