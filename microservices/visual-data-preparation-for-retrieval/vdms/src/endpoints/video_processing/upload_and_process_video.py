# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import datetime
import pathlib
import shutil
from http import HTTPStatus
from typing import Annotated, List, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from src.common import DataPrepException, Strings, logger, settings
from src.common.schema import DataPrepResponse
from src.core.embedding import generate_video_embedding
from src.core.util import get_minio_client, read_config
from src.core.validation import validate_params

router = APIRouter(tags=["Video Processing APIs"])


@router.post(
    "/videos/upload",
    summary="Upload and process a video file for embedding generation.",
    status_code=HTTPStatus.CREATED,
    response_model_exclude_none=True,
)
@validate_params
async def upload_and_process_video(
    file: Annotated[UploadFile, File(description="Video file to upload (MP4 format only)")],
    bucket_name: Annotated[
        Optional[str],
        Query(
            description="The bucket name to store the video in. If not provided, default bucket will be used."
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
    tags: Annotated[
        Optional[List[str]],
        Query(
            default_factory=list,
            description="List of tags to be associated with the video. Useful for filtering the search.",
        ),
    ] = None,
) -> DataPrepResponse:
    """
    ### Upload and process a video file for embedding generation.

    This endpoint accepts an MP4 video file upload, stores it in Minio, and generates embeddings.

    Video is divided into different chunks having length equal to chunk_duration value. Embeddings are
    created and stored for uniformly sampled frames inside a clip (having length equal to clip_duration),
    occurring in each chunk.

    ***For example:** Given a video of 30s in total length, with chunk_duration = 10 and clip_duration = 5,
    embeddings will be created for uniformly sampled frames from first 5 sec clip (defined by clip_duration)
    in each of the three chunks. Three chunks would be created because total length of video is 30s and duration
    of every chunk is 10s (defined by chunk_duration). **Number of chunks = int(total length of video in sec / chunk_duration)***

    #### File Upload:
    - **file (UploadFile, required) :** Video file to upload (MP4 format only, max size 500MB)

    #### Query Params:
    - **bucket_name (str, optional) :** The bucket name to store the video in. If not provided, default bucket will be used.
    - **chunk_duration (int, optional) :** Interval of time in seconds for video chunking (default: 30)
    - **clip_duration (int, optional) :** Length of clip in seconds for embedding selection (default: 10)
    - **tags (list(str), optional) :** A list of tags to be associated with the video. Useful for filtering the search.

    #### Raises:
    - **400 Bad Request :** If the video file is not an MP4 or fails validation.
    - **413 Request Entity Too Large :** If the uploaded file exceeds the 500MB limit.
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

        # Get processing parameters, fall back to config if not specified
        chunk_duration = chunk_duration or config.get("chunk_duration", 30)
        clip_duration = clip_duration or config.get("clip_duration", 10)
        bucket_name = bucket_name or settings.DEFAULT_BUCKET_NAME

        # Get directory paths from config file
        videos_temp_dir = pathlib.Path(config.get("videos_local_temp_dir", "/tmp/dataprep/videos"))
        metadata_temp_dir = pathlib.Path(
            config.get("metadata_local_temp_dir", "/tmp/dataprep/metadata")
        )

        # Generate a video_id based on the filename and timestamp
        video_id = f"dp_video_{int(datetime.datetime.now().timestamp())}"

        # Create temp directories to store the video and metadata
        videos_temp_dir = videos_temp_dir / video_id
        metadata_temp_dir = metadata_temp_dir / video_id

        videos_temp_dir.mkdir(parents=True, exist_ok=True)
        metadata_temp_dir.mkdir(parents=True, exist_ok=True)

        # Create the object name using video_id and filename
        filename = file.filename
        object_name = f"{video_id}/{filename}"

        minio_client = get_minio_client()
        minio_client.ensure_bucket_exists(bucket_name)

        # First, save the file to Minio directly from the uploaded file
        try:
            content = await file.read()
            minio_client.upload_video(bucket_name, object_name, content)
            logger.info(f"Uploaded video {filename} to {bucket_name}/{object_name}")
        except Exception as ex:
            logger.error(f"Error uploading video to Minio: {ex}")
            raise DataPrepException(status_code=HTTPStatus.BAD_GATEWAY, msg=Strings.minio_error)

        await file.seek(0)  # Reset file position again

        # Now save the uploaded file to a temporary location for processing
        temp_video_path = videos_temp_dir / filename
        with open(temp_video_path, "wb") as f:
            content = await file.read()
            f.write(content)

        logger.debug(f"Successfully saved uploaded file {filename} to {temp_video_path}")

        # Process video metadata and generate embeddings
        ids = await generate_video_embedding(
            bucket_name=bucket_name,
            video_id=video_id,
            filename=filename,
            temp_video_path=temp_video_path,
            metadata_temp_path=metadata_temp_dir,
            chunk_duration=chunk_duration,
            clip_duration=clip_duration,
            tags=tags or [],
        )

        logger.info(f"Embeddings created for video: {ids}")
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
            if videos_temp_dir.exists():
                shutil.rmtree(videos_temp_dir, ignore_errors=True)
            if metadata_temp_dir.exists():
                shutil.rmtree(metadata_temp_dir, ignore_errors=True)
        except Exception as ex:
            logger.error(f"Error cleaning up temporary directories: {ex}")
