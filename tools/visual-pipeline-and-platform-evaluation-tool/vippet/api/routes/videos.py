import logging
from typing import List

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from videos import VideosManager

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
