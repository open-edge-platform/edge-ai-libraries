import logging
from typing import List

from fastapi import APIRouter

import api.api_schemas as schemas
from videos import get_videos_manager

router = APIRouter()
logger = logging.getLogger("api.routes.videos")


@router.get("", operation_id="get_videos", response_model=List[schemas.Video])
def get_videos():
    """
    List all discovered input videos with basic metadata.

    Operation:
        * Use VideosManager to scan ``RECORDINGS_PATH`` for supported video
          files (only ``h264`` / ``h265`` codecs).
        * Load or extract metadata (width, height, fps, frame_count, codec,
          duration) for each file.
        * Return the result as a list of Video schema objects.

    Path / query parameters:
        None.

    Returns:
        200 OK:
            JSON array of Video objects. If no videos are found, an empty list
            is returned.

    Success conditions:
        * VideosManager is successfully initialized at application startup
          (RECORDINGS_PATH exists and is a directory).
        * The endpoint is able to iterate over the cached videos map.

    Failure conditions:
        * If VideosManager cannot be created (e.g. RECORDINGS_PATH invalid),
          the application exits at startup and this endpoint will not be
          available.
        * Runtime errors inside VideosManager are not mapped to custom status
          codes here and will surface as 500 responses from FastAPI.

    Successful response example (200):
        .. code-block:: json

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
    """
    logger.info("Received request for all videos.")
    videos_manager = get_videos_manager()
    videos_dict = videos_manager.get_all_videos()
    logger.info(f"Found {len(videos_dict)} videos.")
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
