"""Integration test covering the videos endpoint happy path.

Run with Python 3.12+ and pytest while the VIPPET API is available locally:

    python3.12 -m pytest integration/test_videos_list.py
"""

import logging
from typing import Any

import requests

from api_helpers import fetch_videos
from vippet.api.api_schemas import Video

logger = logging.getLogger(__name__)

EXPECTED_VIDEOS: list[dict[str, Any]] = [
    {
        "filename": "people.mp4",
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "frame_count": 302,
        "codec": "h264",
        "duration": 10.066666666666666,
    },
    {
        "filename": "license-plate-detection.mp4",
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "frame_count": 923,
        "codec": "h264",
        "duration": 30.766666666666666,
    },
]


def _video_matches(candidate: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(candidate.get(key) == value for key, value in expected.items())


def test_videos_endpoint_returns_videos(http_client: requests.Session) -> None:
    videos = fetch_videos(http_client)

    assert videos, "Videos endpoint returned an empty list"
    for raw in videos:
        Video.model_validate(raw)

    for expected in EXPECTED_VIDEOS:
        matching = next(
            (video for video in videos if _video_matches(video, expected)), None
        )
        assert matching is not None, (
            f"Videos endpoint missing expected entry: {expected['filename']}"
        )
