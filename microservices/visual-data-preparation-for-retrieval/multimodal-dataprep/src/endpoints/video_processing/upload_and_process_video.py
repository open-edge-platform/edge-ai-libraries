# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import datetime
import pathlib
import shutil
import io
import asyncio
import threading
import time
import uuid
from http import HTTPStatus
from typing import Annotated, List, Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile

from src.common import DataPrepException, Strings, logger, sanitize_for_log, settings
from src.common.api_responses import INGEST_ERRORS, error_responses
from src.common.schema import DataPrepResponse
from src.core.dedup import check_and_register_upload
from src.core.embedding import (
    generate_image_embedding_from_content,
    generate_video_embedding_from_content,
    generate_video_embedding_from_uri,
)
from src.core.media import detect_media_kind
from src.core.utils.common_utils import get_minio_client
from src.core.utils.config_utils import read_config
from src.core.validation import validate_params

router = APIRouter(tags=["Media Processing APIs"])


@router.post(
    "/media/upload",
    summary="Upload and process a video or image file for embedding generation.",
    operation_id="uploadAndProcessMedia",
    status_code=HTTPStatus.CREATED,
    response_model=DataPrepResponse,
    response_model_exclude_none=True,
    responses=error_responses(*INGEST_ERRORS),
)
@validate_params
async def upload_and_process_video(
    file: Annotated[UploadFile, File(description="Media file to upload (MP4 video or JPG/PNG/WEBP/BMP/GIF image)")],
    bucket_name: Annotated[
        Optional[str],
        Query(
            description="The bucket (object storage) or top-level directory (local storage) "
            "to store the media in. Defaults to the service's configured bucket when omitted."
        ),
    ] = None,
    frame_interval: Annotated[
        Optional[int],
        Query(ge=1, le=60, description="Extract every Nth frame for processing (defaults to the service's configured frame_interval, 15 unless overridden)"),
    ] = None,
    enable_object_detection: Annotated[
        Optional[bool],
        Query(description="Enable object detection and crop extraction (defaults to the service's configured setting, enabled unless overridden)"),
    ] = None,
    detection_confidence: Annotated[
        Optional[float],
        Query(ge=0.1, le=1.0, description="Confidence threshold for object detection (defaults to the service's configured threshold, 0.85 unless overridden)"),
    ] = None,
    tags: Annotated[
        Optional[List[str]],
        Query(
            description="List of tags to be associated with the video. Useful for filtering the search.",
        ),
    ] = None,
) -> DataPrepResponse:
    """
    ### Upload and process a video or image file for embedding generation.

    This endpoint accepts a media file upload (MP4 video or a supported image
    format), stores it, and generates embeddings. Videos are processed with
    frame-based extraction; images are embedded directly (whole image plus, when
    object detection is enabled, one embedding per detected object crop). Both
    paths share the same storage, duplicate-detection and metadata contract; the
    embedding is discriminated by the ``content_type`` metadata field.

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
    - **frame_interval (int, optional) :** Extract every Nth frame for processing (range: 1-60; defaults to the service's configured frame_interval, 15 unless overridden)
    - **enable_object_detection (bool, optional) :** Enable object detection and crop extraction (defaults to the service's configured setting, enabled unless overridden)
    - **detection_confidence (float, optional) :** Confidence threshold for object detection (range: 0.1-1.0; defaults to the service's configured threshold, 0.85 unless overridden)
    - **tags (list(str), optional) :** A list of tags to be associated with the video. Useful for filtering the search.

    #### Raises:
    - **400 Bad Request :** If the video file is not an MP4 or fails validation.
    - **413 Request Entity Too Large :** If the uploaded file exceeds the 500MB limit.
    - **502 Bad Gateway :** When the configured storage backend or vector database cannot be reached.
    - **500 Internal Server Error :** When some internal error occurs at DataPrep API server.

    Returns:
    - **response (json) :** A response JSON containing status and message.
    """

    videos_temp_dir: Optional[pathlib.Path] = None
    metadata_temp_dir: Optional[pathlib.Path] = None

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

        # Detect the media kind from the uploaded filename so images and videos
        # can share this endpoint. Unknown extensions are rejected earlier by
        # validate_file; default to "video" defensively.
        media_kind = detect_media_kind(file.filename) or "video"

        # Generate a media id based on the kind and timestamp
        id_prefix = "dp_image" if media_kind == "image" else "dp_video"
        video_id = f"{id_prefix}_{int(datetime.datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"

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
            logger.info(
                "Uploaded video %s to %s/%s",
                sanitize_for_log(filename, max_length=256),
                sanitize_for_log(bucket_name, max_length=128),
                sanitize_for_log(object_name, max_length=256),
            )
        except Exception as ex:
            logger.error(f"Error uploading video to Minio: {ex}")
            raise DataPrepException(status_code=HTTPStatus.BAD_GATEWAY, msg=Strings.minio_error)

        # Enforce the duplicate-upload policy and register dedup markers. When
        # duplicates are disallowed and this content already exists, a 409 is
        # raised (the just-stored object is rolled back below before returning).
        try:
            check_and_register_upload(minio_client, bucket_name, video_id, content)
        except DataPrepException:
            try:
                minio_client.delete_object(bucket_name, object_name)
            except Exception as cleanup_ex:  # noqa: BLE001
                logger.warning("Failed to roll back duplicate upload object: %s", cleanup_ex)
            raise

        telemetry_context = {
            "request_id": str(uuid.uuid4()),
            "source": "/media/upload",
            "requested_at": time.time(),
        }

        # Process media content directly from memory (most efficient). Images
        # and videos take different embedding paths but share storage + dedup.
        if media_kind == "image":
            logger.info("Processing image directly from memory")
            ids = await generate_image_embedding_from_content(
                image_content=content,
                bucket_name=bucket_name,
                video_id=video_id,
                filename=filename,
                enable_object_detection=enable_object_detection,
                detection_confidence=detection_confidence,
                tags=tags or [],
                telemetry_context=telemetry_context,
            )
        else:
            logger.info("Processing video directly from memory for optimal performance")
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
                telemetry_context=telemetry_context,
            )
        logger.info(f"{len(ids)} embeddings created with optimized memory usage")

        logger.info(
            "Frame-based embeddings created for media: %s",
            sanitize_for_log(ids, max_length=512),
        )
        return DataPrepResponse(
            message=f"{Strings.embedding_success}"
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


@router.post(
    "/media/rtsp",
    summary="Provide list of RTSP Stream URLs to process and generate embeddings.",
    operation_id="processRtspStreams",
    status_code=HTTPStatus.OK,
    response_model=DataPrepResponse,
    response_model_exclude_none=True,
    responses=error_responses(
        HTTPStatus.BAD_REQUEST,
        HTTPStatus.BAD_GATEWAY,
        HTTPStatus.INTERNAL_SERVER_ERROR,
    ),
)
@validate_params
async def process_rtsp_streams(
    request: Request,
    rtsp_urls: Annotated[
        List[str],
        Query(
            description="List of RTSP stream URLs to process. Each URL will be validated and processed for embedding generation."
        ),
    ],
    frame_interval: Annotated[
        Optional[int],
        Query(ge=1, le=60, description="Extract every Nth frame for processing (defaults to the service's configured frame_interval, 15 unless overridden)"),
    ] = None,
    enable_object_detection: Annotated[
        Optional[bool],
        Query(description="Enable object detection and crop extraction (defaults to the service's configured setting, enabled unless overridden)"),
    ] = None,
    detection_confidence: Annotated[
        Optional[float],
        Query(ge=0.1, le=1.0, description="Confidence threshold for object detection (defaults to the service's configured threshold, 0.85 unless overridden)"),
    ] = None,
    tags: Annotated[
        Optional[List[str]],
        Query(
            description="List of tags to be associated with the videos. Useful for filtering the search.",
        ),
    ] = None,
) -> DataPrepResponse:
    """
    ### Process RTSP stream URLs for frame-based embedding generation.

    This endpoint accepts a list of RTSP stream URLs, validates them, and generates embeddings
    using frame-based processing with optional object detection.

    Each RTSP stream is processed by extracting individual frames at regular intervals (every Nth frame).
    Each frame generates its own embedding. When object detection is enabled and suppose 3 objects are detected per frame on average, this results in approximately 240 embeddings
    (60 frames + 180 object crops) per video. The generated embeddings are stored in the vector database with associated metadata and tags.

    #### Query Params:
    - **rtsp_urls (list(str), required) :** List of RTSP stream URLs to process. Each URL will be validated and processed for embedding generation.
    - **frame_interval (int, optional) :** Extract every Nth frame for processing (range: 1-60; defaults to the service's configured frame_interval, 15 unless overridden)
    - **enable_object_detection (bool, optional) :** Enable object detection and crop extraction (defaults to the service's configured setting, enabled unless overridden)
    - **detection_confidence (float, optional) :** Confidence threshold for object detection (range: 0.1-1.0; defaults to the service's configured threshold, 0.85 unless overridden)
    - **tags (list(str), optional) :** A list of tags to be associated with the videos. Useful for filtering the search.

    #### Raises:
    - **400 Bad Request :** If any of the RTSP URLs are invalid or fail validation.
    - **502 Bad Gateway :** When the configured storage backend cannot be reached, or during stream access.
    - **500 Internal Server Error :** When some internal error occurs at DataPrep API server.

    Returns:
    - **response (json) :** A response JSON containing status and message.
    """
    # Sanitize and validate RTSP URLs
    valid_rtsp_urls = []
    for url in rtsp_urls:
        url = url.strip()
        if not url.lower().startswith("rtsp://"):
            logger.warning(f"Invalid RTSP URL skipped: {url}")
            continue
        valid_rtsp_urls.append(url)
    
    if not valid_rtsp_urls:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="No valid RTSP URLs provided. Each URL must start with 'rtsp://'.")
    
    logger.info(f"Processing {valid_rtsp_urls} valid RTSP URLs for embedding generation")

    # Create shutdown event for graceful termination
    shutdown_event = threading.Event()
    shutdown_event.clear()

    # Monitor for client disconnect in background
    async def monitor_disconnect():
        logger.info("Monitor disconnect task started")
        try:
            while not shutdown_event.is_set():
                try:
                    is_disconnected = await request.is_disconnected()
                    if is_disconnected:
                        logger.info("Client disconnected, triggering graceful shutdown...")
                        shutdown_event.set()
                        break
                    else:
                        logger.debug("Client still connected")
                except Exception as e:
                    logger.warning(f"Error checking disconnect status: {e}")
                await asyncio.sleep(0.5)
        finally:
            logger.info("Monitor disconnect task exiting")

    monitor_task = asyncio.create_task(monitor_disconnect())
    logger.info("ID of shutdown_event in process_rtsp_streams: %s", id(shutdown_event))
    telemetry_context = {
            "request_id": str(uuid.uuid4()),
            "source": "/media/rtsp",
            "requested_at": time.time(),
        }

    try:
        ids = await generate_video_embedding_from_uri(
                    video_uris=valid_rtsp_urls,
                    bucket_name=None,
                    video_id=None,
                    filename=None,
                    metadata_temp_path=None,
                    frame_interval=frame_interval,
                    enable_object_detection=enable_object_detection,
                    detection_confidence=detection_confidence,
                    tags=tags or [],
                    telemetry_context=telemetry_context,
                    shutdown_event=shutdown_event,
                )
        logger.info(f"{len(ids) if ids else 0} embeddings created with optimized memory usage")
        
        return DataPrepResponse(
            message=f"{Strings.embedding_success} for RTSP streams"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("RTSP stream processing failed")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"Failed to process RTSP streams: {e}",
        )
    finally:
        # Stop the monitor task
        shutdown_event.set()
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass