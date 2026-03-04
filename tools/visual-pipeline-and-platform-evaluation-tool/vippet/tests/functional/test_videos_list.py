"""Functional test covering the videos endpoint happy path."""

import logging
from typing import Any

import pytest
import requests

from helpers.api_helpers import fetch_videos

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


@pytest.mark.smoke
def test_videos_endpoint_returns_valid_structure(http_client: requests.Session) -> None:
    videos = fetch_videos(http_client)

    assert videos, "Videos endpoint returned an empty list"
    for raw in videos:
        assert isinstance(raw, dict), "Each video entry must be an object"
        assert REQUIRED_VIDEO_KEYS.issubset(raw.keys()), (
            f"Video entry missing required keys: {REQUIRED_VIDEO_KEYS - raw.keys()}"
        )


@pytest.mark.smoke
def test_all_default_recordings_are_available(
    http_client: requests.Session,
    default_recordings_config: list[dict[str, Any]],
) -> None:
    """All recordings listed in default_recordings.yaml must be returned by the API."""
    videos = fetch_videos(http_client)
    available_filenames = {video["filename"] for video in videos}

    for recording in default_recordings_config:
        expected_filename = recording["filename"]
        assert expected_filename in available_filenames, (
            f"Default recording '{expected_filename}' is not present in the API response"
        )
