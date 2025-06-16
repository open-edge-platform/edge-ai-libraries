# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
import datetime
import io
import pathlib
import shutil
from http import HTTPStatus
from typing import Annotated, List, Optional

import requests
from fastapi import Body, FastAPI, File, Header, HTTPException, Path, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from src.common import DataPrepException, Settings, Strings
from src.core.db import VDMSClient
from src.core.embedding_wrapper import vCLIPEmbeddingsWrapper
from src.core.minio_client import MinioClient
from src.core.util import get_minio_client, get_video_from_minio, read_config, store_video_metadata
from src.core.validation import sanitize_model, validate_params
from src.core.vclip import vCLIP
from src.logger import logger
from src.schema import (
    BucketVideoListResponse,
    DataPrepErrorResponse,
    DataPrepResponse,
    StatusEnum,
    VideoInfo,
    VideoRequest,
)

settings = Settings()
logger.debug(f"Settings loaded: {settings.model_dump()}")
app = FastAPI(
    title=settings.APP_DISPLAY_NAME, description=settings.APP_DESC, root_path="/v1/dataprep"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOW_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=settings.ALLOW_METHODS.split(","),
    allow_headers=settings.ALLOW_HEADERS.split(","),
)


# Setting up custom error message format
@app.exception_handler(HTTPException)
async def custom_exception_handler(request, exc):
    error_res = DataPrepResponse(status=StatusEnum.error, message=exc.detail)
    return JSONResponse(content=error_res.model_dump(), status_code=exc.status_code)


"""
API Endpoints
"""


async def generate_embeddings(
    bucket_name: str,
    video_id: str,
    filename: str,
    temp_video_path: pathlib.Path,
    metadata_temp_path: pathlib.Path,
    chunk_duration: int,
    clip_duration: int,
) -> List[str]:
    """
    Generate metadata and embeddings for a video file.

    Args:
        bucket_name: The bucket name where the video is stored or will be stored
        video_id: The video ID (directory) containing the video
        filename: The video filename
        temp_video_path: Temporary path where the video file is stored
        metadata_temp_path: Path where metadata will be stored
        chunk_duration: Interval of time in seconds for video chunking
        clip_duration: Length of clip in seconds for embedding selection

    Returns:
        List of IDs of the created embeddings

    Raises:
        DataPrepException: If there is an error in the embedding generation process
    """
    # Read configuration
    config = read_config(settings.CONFIG_FILEPATH, type="yaml")
    if config is None:
        raise Exception(Strings.config_error)

    vector_dimension = config["embeddings"]["vector_dimensions"]

    # Generate metadata for the video
    metadata_file = store_video_metadata(
        bucket_name=bucket_name,
        video_id=video_id,
        video_filename=filename,
        temp_video_path=temp_video_path,
        chunk_duration=chunk_duration,
        clip_duration=clip_duration,
        metadata_temp_path=str(metadata_temp_path),
    )

    logger.info(f"Metadata generated and saved to {metadata_file}")

    # Setup embedding model
    if settings.MULTIMODAL_EMBEDDING_ENDPOINT:
        vclip_model = vCLIPEmbeddingsWrapper(
            api_url=settings.MULTIMODAL_EMBEDDING_ENDPOINT,
            model_name=settings.MULTIMODAL_EMBEDDING_MODEL_NAME,
            num_frames=settings.MULTIMODAL_EMBEDDING_NUM_FRAMES,
        )
    else:
        # Get the vclip model
        vclip_model = vCLIP(config["embeddings"])

    # Initialize VDMS db client
    vdms = VDMSClient(
        host=settings.VDMS_VDB_HOST,
        port=settings.VDMS_VDB_PORT,
        collection_name=settings.DB_COLLECTION,
        model=vclip_model,
        video_metadata_path=metadata_file,
        embedding_dimensions=vector_dimension,
    )

    # Store the video embeddings in VDMS vector DB
    ids = vdms.store_embeddings()
    logger.info(f"Embeddings created for videos: {ids}")

    return ids


@app.get("/health", tags=["Status APIs"], summary="Check the health of the API service")
async def check_health():
    """Health API endpoint to check whether API Server is reachable and responding."""
    return {"status": "ok"}


@app.post(
    "/videos",
    tags=["Data Preparation APIs"],
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


@app.post(
    "/videos/minio",
    tags=["Data Preparation APIs"],
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

        # Validate required parameters
        if not bucket_name or not video_id:
            raise DataPrepException(
                status_code=HTTPStatus.BAD_REQUEST,
                msg="Both bucket_name and video_id must be provided.",
            )

        # Get the Minio client and ensure the bucket exists
        minio_client = get_minio_client()
        minio_client.ensure_bucket_exists(bucket_name)

        # Create a unique subdirectory for this request using video_id to avoid conflicts
        request_timestamp = int(datetime.datetime.now().timestamp())
        request_id = f"{video_id}_{request_timestamp}"
        videos_temp_dir = videos_temp_dir / request_id
        metadata_temp_dir = metadata_temp_dir / request_id

        # create the temp directories
        videos_temp_dir.mkdir(parents=True, exist_ok=True)
        metadata_temp_dir.mkdir(parents=True, exist_ok=True)

        # If video_name is not provided, try to get it from the directory
        if not video_name:
            logger.info(
                f"Video name not provided, attempting to find video in directory {video_id}"
            )
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

        # Process video metadata and generate embeddings
        ids: list[str] = await generate_embeddings(
            bucket_name=bucket_name,
            video_id=video_id,
            filename=filename,
            temp_video_path=temp_video_path,
            metadata_temp_path=metadata_temp_dir,
            chunk_duration=chunk_duration,
            clip_duration=clip_duration,
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


@app.post(
    "/videos/upload",
    tags=["Data Preparation APIs"],
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
            # Reset the file position to the beginning
            await file.seek(0)

            # Upload to Minio
            minio_client.upload_video(bucket_name, object_name, file.file, file.size)

            logger.info(f"Uploaded file saved to Minio at {bucket_name}/{object_name}")
        except Exception as ex:
            logger.error(f"Error storing uploaded file in Minio: {ex}")
            raise DataPrepException(
                status_code=HTTPStatus.BAD_GATEWAY, msg=f"Failed to store file in Minio"
            )

        await file.seek(0)  # Reset file position again

        # Now save the uploaded file to a temporary location for processing
        temp_video_path = videos_temp_dir / filename
        with open(temp_video_path, "wb") as f:
            f.write(await file.read())

        logger.debug(f"Successfully saved uploaded file {filename} to {temp_video_path}")

        # Process video metadata and generate embeddings
        ids: list[str] = await generate_embeddings(
            bucket_name=bucket_name,
            video_id=video_id,
            filename=filename,
            temp_video_path=temp_video_path,
            metadata_temp_path=metadata_temp_dir,
            chunk_duration=chunk_duration,
            clip_duration=clip_duration,
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
        # Clean up any unique video directory created for this request
        try:
            if (
                "video_id" in locals()
                and "videos_temp_dir" in locals()
                and videos_temp_dir.exists()
            ):
                shutil.rmtree(videos_temp_dir, ignore_errors=True)
            if (
                "video_id" in locals()
                and "metadata_temp_dir" in locals()
                and metadata_temp_dir.exists()
            ):
                shutil.rmtree(metadata_temp_dir, ignore_errors=True)
        except Exception as ex:
            logger.error(f"Error cleaning up temporary directories: {ex}")


@app.get(
    "/videos",
    tags=["Data Preparation APIs"],
    summary="Get list of videos from Minio storage.",
    response_model_exclude_none=True,
)
@validate_params
async def get_video_files_list(
    bucket_name: Annotated[
        str,
        Query(
            description="The bucket name to list videos from. If not provided, default bucket will be used."
        ),
    ] = None,
) -> BucketVideoListResponse:
    """
    ### Get list of available videos from Minio storage.

    #### Query Params:
    - **bucket_name (str, optional):** The bucket name to list videos from. If not provided, default bucket will be used.

    #### Raises:
    - **502 Bad Gateway:** When something goes wrong with Minio storage access.
    - **500 Internal Server Error:** When some internal error occurs at the API server.

    #### Returns:
    - **response (json):** A JSON response containing list of videos with details like video_id, video_name, video_path, and creation timestamp.
    """

    try:
        # Use provided bucket_name or fall back to default
        if not bucket_name:
            bucket_name = settings.DEFAULT_BUCKET_NAME

        # Get the Minio client
        minio_client = get_minio_client()

        # Check if bucket exists
        minio_client.ensure_bucket_exists(bucket_name)

        # Get list of videos with metadata
        video_list: List[dict] = minio_client.list_all_videos(bucket_name)

        # Convert to VideoInfo objects
        videos = [
            VideoInfo(
                video_id=video["video_id"],
                video_name=video["video_name"],
                video_path=video["video_path"],
                creation_ts=video["creation_ts"],
            )
            for video in video_list
        ]

        return BucketVideoListResponse(bucket_name=bucket_name, videos=videos)

    except DataPrepException as ex:
        logger.error(ex)
        raise HTTPException(status_code=ex.status_code, detail=ex.message)

    except Exception as ex:
        logger.error(f"Error listing videos: {ex}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=Strings.minio_error
        )


@app.get(
    "/videos/download",
    tags=["Data Preparation APIs"],
    summary="(Legacy Endpoint) Download a video from Minio storage",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"application/octet-stream": {}},
            "description": "A downloadable video file.",
        },
        404: {"model": DataPrepErrorResponse, "description": "File not found"},
    },
    deprecated=True,
)
@validate_params
async def download_video_file_legacy(
    video_id: Annotated[
        str,
        Query(min_length=3, description="Directory on MINIO Server containing the video"),
    ],
    video_name: Annotated[
        Optional[str],
        Query(
            description="Specific video filename to download. If not provided, first video found is used."
        ),
    ] = None,
    bucket_name: Annotated[
        Optional[str],
        Query(
            description="The bucket name where the video is stored. If not provided, default bucket will be used."
        ),
    ] = None,
    range: Optional[str] = Header(None),
) -> StreamingResponse:
    """
    ### Legacy Endpoint: Please use /{video_id}/{video_name} endpoint instead.
    ## Download a video file from Minio storage (DEPRECATED).

    #### Query Params:
    - **video_id (str):** Directory/collection ID containing the video
    - **video_name (str, optional):** Specific video filename to download. If not provided, first video found is used.
    - **bucket_name (str, optional):** The bucket name where the video is stored. If not provided, default bucket will be used.

    #### Headers:
    - **Range (str, optional):** HTTP Range header for partial content download

    #### Returns:
    - **File (binary):** Returns the video file as a streaming response.
    """
    # Redirect to the new endpoint
    return await download_video_by_path(video_id, video_name or "", bucket_name, range)


@app.get(
    "/{video_id}/{video_name}",
    tags=["Data Preparation APIs"],
    summary="Download a video from Minio storage",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"application/octet-stream": {}},
            "description": "A downloadable video file.",
        },
        400: {"model": DataPrepErrorResponse, "description": "Invalid parameters"},
        404: {"model": DataPrepErrorResponse, "description": "File not found"},
        502: {"model": DataPrepErrorResponse, "description": "Minio storage error"},
    },
)
@validate_params
async def download_video_by_path(
    video_id: Annotated[
        str,
        Path(min_length=3, description="Directory/collection ID containing the video"),
    ],
    video_name: Annotated[
        str,
        Path(description="Specific video filename to download"),
    ],
    bucket_name: Annotated[
        Optional[str],
        Query(
            description="The bucket name where the video is stored. If not provided, default bucket will be used."
        ),
    ] = None,
    range: Optional[str] = Header(None),
) -> StreamingResponse:
    """
    ### Download a video file from Minio storage.

    #### Path Params:
    - **video_id (str):** Directory/collection ID containing the video
    - **video_name (str):** Specific video filename to download

    #### Query Params:
    - **bucket_name (str, optional):** The bucket name where the video is stored. If not provided, default bucket will be used.

    #### Headers:
    - **Range (str, optional):** HTTP Range header for partial content download

    #### Raises:
    - **400 Bad Request:** When video_id or video_name are invalid according to Minio naming rules.
    - **404 Not Found:** When the requested video cannot be found.
    - **502 Bad Gateway:** When something goes wrong with Minio storage access.
    - **500 Internal Server Error:** When some internal error occurs at the API server.

    #### Returns:
    - **File (binary):** Returns the video file as a streaming response.
    """

    try:
        # Use provided bucket_name or fall back to default
        if not bucket_name:
            bucket_name = settings.DEFAULT_BUCKET_NAME

        # Get the Minio client
        minio_client = get_minio_client()

        # Check if bucket exists
        minio_client.ensure_bucket_exists(bucket_name)

        # Validate video_id and video_name
        if not minio_client.validate_object_name(video_id, video_name):
            raise DataPrepException(
                status_code=HTTPStatus.BAD_REQUEST,
                msg="Invalid video_id or video_name format. Please check naming conventions.",
            )

        # Check if the object exists
        if not minio_client.object_exists(bucket_name, video_id, video_name):
            raise DataPrepException(
                status_code=HTTPStatus.NOT_FOUND,
                msg=f"Video '{video_id}/{video_name}' not found in bucket '{bucket_name}'",
            )

        # Get the object name
        object_name = f"{video_id}/{video_name}"

        # Get video from Minio
        video_data = minio_client.download_video_stream(bucket_name, object_name)
        if not video_data:
            raise DataPrepException(
                status_code=HTTPStatus.NOT_FOUND, msg=Strings.minio_file_not_found
            )

        # Get total size for the video object
        total_size = minio_client.get_object_size(bucket_name, object_name)

        # Handle range request if needed
        if range:
            logger.debug(f"Range request: {range}")
            # Parse range header (e.g., "bytes=0-1023")
            start_byte, end_byte = range.replace("bytes=", "").split("-")
            start_byte = int(start_byte)
            end_byte = int(end_byte) if end_byte else None

            # Set the end byte if not specified
            if end_byte is None:
                end_byte = total_size - 1

            # Calculate content length
            content_length = end_byte - start_byte + 1

            # Prepare content range header
            content_range = f"bytes {start_byte}-{end_byte}/{total_size}"

            # Seek to the start position
            video_data.seek(start_byte)

            # Create a new BytesIO with just the requested range
            range_data = io.BytesIO(video_data.read(content_length))

            def range_stream():
                yield from range_data

            headers = {
                "Content-Range": content_range,
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Content-Type": "video/mp4",
                "Content-Disposition": f"attachment; filename={video_name}",
            }

            return StreamingResponse(range_stream(), headers=headers, status_code=206)
        else:
            logger.debug(f"Full video download for {video_name}")

            def download_streaming_file():
                yield from video_data

            headers = {
                "Content-Type": "video/mp4",
                "Content-Length": str(total_size),
                "Content-Disposition": f"attachment; filename={video_name}",
            }

            return StreamingResponse(download_streaming_file(), headers=headers)

    except DataPrepException as ex:
        logger.error(ex)
        raise HTTPException(status_code=ex.status_code, detail=ex.message)

    except Exception as ex:
        logger.error(f"Error downloading video: {ex}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=Strings.server_error
        )
