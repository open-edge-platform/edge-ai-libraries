"""Functional test covering the videos endpoint happy path."""

import logging
from typing import Any

import requests

from api_helpers import fetch_videos

logger = logging.getLogger(__name__)

REQUIRED_VIDEO_KEYS: set[str] = {
    "filename",
    "width",
    "height",
    "fps",
    "frame_count",
    "codec",
    "duration",
}

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
        assert isinstance(raw, dict), "Each video entry must be an object"
        assert REQUIRED_VIDEO_KEYS.issubset(raw.keys()), (
            f"Video entry missing required keys: {REQUIRED_VIDEO_KEYS - raw.keys()}"
        )

    for expected in EXPECTED_VIDEOS:
        matching = next(
            (video for video in videos if _video_matches(video, expected)), None
        )
        assert matching is not None, (
            f"Videos endpoint missing expected entry: {expected['filename']}"
        )
