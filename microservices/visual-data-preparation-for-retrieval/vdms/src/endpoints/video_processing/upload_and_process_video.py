# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import datetime
import pathlib
import shutil
import io
from http import HTTPStatus
from typing import Annotated, List, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from src.common import DataPrepException, Strings, logger, settings
from src.common.schema import DataPrepResponse
from src.core.embedding import generate_video_embedding, generate_video_embedding_from_content
from src.core.utils.common_utils import get_minio_client
from src.core.utils.config_utils import read_config
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
    frame_interval: Annotated[
        Optional[int],
        Query(ge=1, le=60, description="Extract every Nth frame for processing (default: 15)"),
    ] = None,
    enable_object_detection: Annotated[
        Optional[bool],
        Query(description="Enable object detection and crop extraction (default: True)"),
    ] = None,
    detection_confidence: Annotated[
        Optional[float],
        Query(ge=0.1, le=1.0, description="Confidence threshold for object detection (default: 0.85)"),
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
    ### Upload and process a video file for frame-based embedding generation.

    This endpoint accepts an MP4 video file upload, stores it in Minio, and generates embeddings
    using frame-based processing with optional object detection.

    Video is processed by extracting individual frames at regular intervals (every Nth frame).
    Each frame generates its own embedding. When object detection is enabled, detected objects
    are cropped and embedded as separate entities, providing enhanced semantic coverage.

    ***For example:** Given a video of 30s at 30fps (900 frames total), with frame_interval = 15,
    60 frames will be extracted and embedded (every 15th frame). If object detection is enabled
    and suppose 3 objects are detected per frame on average, this results in approximately 240 embeddings
    (60 frames + 180 object crops).**

    #### File Upload:
    - **file (UploadFile, required) :** Video file to upload (MP4 format only, max size 500MB)

    #### Query Params:
    - **bucket_name (str, optional) :** The bucket name to store the video in. If not provided, default bucket will be used.
    - **frame_interval (int, optional) :** Extract every Nth frame for processing (default: 15, range: 1-60)
    - **enable_object_detection (bool, optional) :** Enable object detection and crop extraction (default: True)
    - **detection_confidence (float, optional) :** Confidence threshold for object detection (default: 0.85, range: 0.1-1.0)
    - **tags (list(str), optional) :** A list of tags to be associated with the video. Useful for filtering the search.

    #### Raises:
    - **400 Bad Request :** If the video file is not an MP4 or fails validation.
    - **413 Request Entity Too Large :** If the uploaded file exceeds the 500MB limit.
    - **502 Bad Gateway :** When something unpleasant happens at Minio storage.
    - **500 Internal Server Error :** When some internal error occurs at DataPrep API server.

    Returns:
    - **response (json) :** A response JSON containing status and message.
    """

    videos_temp_dir: Optional[pathlib.Path] = None
    metadata_temp_dir: Optional[pathlib.Path] = None
    temp_video_path: Optional[pathlib.Path] = None

    try:
        config = read_config(settings.CONFIG_FILEPATH, type="yaml")

        # Not able to read config file is a fatal error.
        if config is None:
            raise Exception(Strings.config_error)

        # Get processing parameters, fall back to config if not specified
        frame_interval = frame_interval or config.get("frame_interval", 15)
        enable_object_detection = (
            enable_object_detection if enable_object_detection is not None else config.get("enable_object_detection", True)
        )
        detection_confidence = detection_confidence or config.get("detection_confidence", 0.85)
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

        # Read file content once
        content = await file.read()

        # First, save the file to Minio directly from the uploaded file
        try:
            content_stream = io.BytesIO(content)
            minio_client.upload_video(bucket_name, object_name, content_stream, len(content))
            logger.info(f"Uploaded video {filename} to {bucket_name}/{object_name}")
        except Exception as ex:
            logger.error(f"Error uploading video to Minio: {ex}")
            raise DataPrepException(status_code=HTTPStatus.BAD_GATEWAY, msg=Strings.minio_error)

        # Choose processing approach based on embedding mode
        if settings.EMBEDDING_PROCESSING_MODE.lower() == "sdk":
            logger.info("Using SDK mode: processing video directly from memory for optimal performance")
            
            # SDK mode: Process video content directly from memory (most efficient)
            ids = await generate_video_embedding_from_content(
                video_content=content,  # Use in-memory content directly
                bucket_name=bucket_name,
                video_id=video_id,
                filename=filename,
                metadata_temp_path=metadata_temp_dir,
                frame_interval=frame_interval,
                enable_object_detection=enable_object_detection,
                detection_confidence=detection_confidence,
                tags=tags or [],
            )
            logger.info(f"SDK mode: {len(ids)} embeddings created with optimized memory usage")
        else:
            logger.info("Using API mode: traditional file-based processing")
            
            # Now save the uploaded file to a temporary location for processing
            temp_video_path = videos_temp_dir / filename
            with open(temp_video_path, "wb") as f:
                f.write(content)
            logger.debug(f"Successfully saved uploaded file {filename} to {temp_video_path}")
            
            # API mode: Use traditional file-based processing  
            ids = await generate_video_embedding(
                bucket_name=bucket_name,
                video_id=video_id,
                filename=filename,
                temp_video_path=temp_video_path,
                metadata_temp_path=metadata_temp_dir,
                frame_interval=frame_interval,
                enable_object_detection=enable_object_detection,
                detection_confidence=detection_confidence,
                tags=tags or [],
            )
            logger.info(f"API mode: {len(ids)} embeddings created using HTTP calls")

        logger.info(f"Frame-based embeddings created for video using {settings.EMBEDDING_PROCESSING_MODE} mode: {ids}")
        return DataPrepResponse(
            message=f"{Strings.embedding_success} (Mode: {settings.EMBEDDING_PROCESSING_MODE})"
        )

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
            if videos_temp_dir and videos_temp_dir.exists():
                shutil.rmtree(videos_temp_dir, ignore_errors=True)
            if metadata_temp_dir and metadata_temp_dir.exists():
                shutil.rmtree(metadata_temp_dir, ignore_errors=True)
        except Exception as ex:
            logger.error(f"Error cleaning up temporary directories: {ex}")
