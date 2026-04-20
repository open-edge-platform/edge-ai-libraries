import logging
import os
import random
from typing import List

from fastapi import APIRouter, File, UploadFile, HTTPException, Query
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from videos import VideosManager, INPUT_VIDEO_DIR, VIDEO_EXTENSIONS

router = APIRouter()
logger = logging.getLogger("api.routes.videos")


@router.get(
    "",
    operation_id="get_videos",
    summary="List all available input videos",
    response_model=List[schemas.Video],
)
def get_videos():
    """
    **List all discovered input videos with metadata.**

    ## Operation

    1. VideosManager scans INPUT_VIDEO_DIR for supported video files (h264/h265 codecs only)
    2. Metadata is loaded or extracted for each file (resolution, fps, duration, codec)
    3. Returns array of Video objects

    ## Parameters

    None

    ## Response Format

    | Code | Description |
    |------|-------------|
    | 200  | JSON array of Video objects (empty if no videos found) |
    | 500  | Runtime error during video listing |

    ## Conditions

    ### ✅ Success
    - VideosManager successfully initialized at startup
    - INPUT_VIDEO_DIR exists and is a valid directory

    ### ❌ Failure
    - VideosManager initialization fails → application exits at startup
    - Runtime errors → 500

    ## Example Response

    ```json
    [
      {
        "filename": "traffic_1080p_h264.mp4",
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "frame_count": 900,
        "codec": "h264",
        "duration": 30.0
      },
      {
        "filename": "people_720p_h265.mp4",
        "width": 1280,
        "height": 720,
        "fps": 25.0,
        "frame_count": 2500,
        "codec": "h265",
        "duration": 100.0
      }
    ]
    ```
    """
    logger.debug("Received request for all videos.")
    try:
        videos_dict = VideosManager().get_all_videos()
        logger.debug(f"Found {len(videos_dict)} videos.")
        # Convert Video objects to schemas.Video
        return [
            schemas.Video(
                filename=v.filename,
                width=v.width,
                height=v.height,
                fps=v.fps,
                frame_count=v.frame_count,
                codec=v.codec,
                duration=v.duration,
            )
            for v in videos_dict.values()
        ]
    except Exception:
        logger.error("Failed to list videos", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error while listing videos"
            ).model_dump(),
            status_code=500,
        )


@router.get(
    "/check-video-input-exists",
    operation_id="check_video_input_exists",
    summary="Check if a video file already exists",
    response_model=schemas.VideoExistsResponse,
)
def check_video_input_exists(
    filename: str = Query(..., description="Video filename to check"),
):
    """
    **Check if a video file with the given filename already exists in INPUT_VIDEO_DIR.**

    ## Operation

    1. Validates filename against INPUT_VIDEO_DIR
    2. Returns whether the file exists

    ## Parameters

    - `filename` (query) - Name of the video file to check

    ## Response Format

    | Code | Description |
    |------|-------------|
    | 200  | Returns VideoExistsResponse with exists boolean |

    ## Conditions

    ### ✅ Success
    - Always succeeds with boolean response

    ## Example Response

    ```json
    {
      "exists": true,
      "filename": "traffic_1080p_h264.mp4"
    }
    ```
    """
    logger.debug(f"Checking existence of video file: {filename}")

    # Check if file exists in INPUT_VIDEO_DIR
    file_path = os.path.join(INPUT_VIDEO_DIR, filename)
    exists = os.path.isfile(file_path)

    logger.debug(f"Video '{filename}' exists: {exists}")

    return schemas.VideoExistsResponse(
        exists=exists,
        filename=filename,
    )


@router.post(
    "/upload",
    operation_id="upload_video",
    summary="Upload a new video file",
    response_model=schemas.Video,
    status_code=201,
)
async def upload_video(file: UploadFile = File(...)):
    """
    **Upload a new video file to the INPUT_VIDEO_DIR.**

    ## Operation

    1. Validate file extension against supported formats
    2. Save file to INPUT_VIDEO_DIR in 8KB chunks
    3. Extract video metadata (resolution, fps, codec, etc.)
    4. Create TS conversion for looping support
    5. Return Video object with extracted metadata

    ## Parameters

    - `file` (multipart/form-data) - Video file to upload

    ## Response Format

    | Code | Description |
    |------|-------------|
    | 201  | Video uploaded successfully, returns Video object |
    | 400  | Invalid file (unsupported extension or codec, duplicate filename) |
    | 500  | Error during upload or processing |

    ## Conditions

    ### ✅ Success
    - File has supported video extension (mp4, mkv, mov, avi, ts, 264, avc, h265, hevc)
    - File has supported codec (h264 or h265)
    - No file with same name exists in INPUT_VIDEO_DIR
    - Video metadata extraction successful

    ### ❌ Failure
    - No file provided → 400
    - File extension not supported → 400
    - Filename already exists → 400
    - Video codec not h264/h265 → 400
    - Cannot extract metadata → 500
    - Write error → 500

    ## Example Response

    ```json
    {
      "filename": "uploaded_video.mp4",
      "width": 1920,
      "height": 1080,
      "fps": 30.0,
      "frame_count": 1800,
      "codec": "h264",
      "duration": 60.0
    }
    ```
    """
    logger.info(f"Received video upload request: {file.filename}")

    # TESTING: Simulate error for frontend error handling (50% probability)
    if random.random() < 0.5:
        raise HTTPException(
            status_code=400,
            detail="Simulated error for testing frontend error handling",
        )

    if not file.filename:
        logger.warning("Upload request without filename")
        raise HTTPException(status_code=400, detail="No filename provided")

    # Validate file extension
    ext = file.filename.lower().rsplit(".", 1)[-1]
    if ext not in VIDEO_EXTENSIONS:
        logger.warning(f"Unsupported video extension: .{ext}")
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported video format. Allowed extensions: {', '.join(VIDEO_EXTENSIONS)}",
        )

    # Check for duplicate filename
    target_path = os.path.join(INPUT_VIDEO_DIR, file.filename)
    if os.path.exists(target_path):
        logger.warning(f"File already exists: {file.filename}")
        raise HTTPException(
            status_code=400, detail=f"File '{file.filename}' already exists"
        )

    try:
        # Save file in chunks (8KB)
        chunk_size = 8192
        logger.debug(f"Saving file to {target_path}")

        with open(target_path, "wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)

        file_size = os.path.getsize(target_path)
        logger.info(f"Uploaded '{file.filename}' ({file_size / (1024 * 1024):.2f} MB)")

        # Process video metadata using VideosManager
        videos_manager = VideosManager()
        video = videos_manager._ensure_video_metadata(target_path)

        if video is None:
            # Clean up file if processing fails
            try:
                os.remove(target_path)
            except OSError:
                pass
            logger.error(f"Failed to extract metadata from '{file.filename}'")
            raise HTTPException(
                status_code=400,
                detail="Failed to process video. Ensure codec is h264 or h265.",
            )

        # Add to VideosManager internal cache
        videos_manager._videos[file.filename] = video

        # Ensure TS conversion exists for looping support
        videos_manager.ensure_ts_file(target_path)

        logger.info(f"Successfully processed video: {file.filename}")

        # Return Video schema
        return schemas.Video(
            filename=video.filename,
            width=video.width,
            height=video.height,
            fps=video.fps,
            frame_count=video.frame_count,
            codec=video.codec,
            duration=video.duration,
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Clean up file on error
        if os.path.exists(target_path):
            try:
                os.remove(target_path)
            except OSError:
                pass
        logger.error(f"Error uploading video '{file.filename}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error uploading video: {str(e)}")
