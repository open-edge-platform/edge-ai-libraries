"""Functional test covering the videos endpoint happy path."""

import logging
from typing import Any

import pytest
import requests

from helpers.api_helpers import fetch_default_video_recordings, fetch_videos

logger = logging.getLogger(__name__)

VALID_RECORDING_STATUSES: frozenset[str] = frozenset(
    {"available", "queued", "downloading", "downloaded", "failed", "conflict"}
)

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

    # Sample videos are downloaded on demand, so a fresh ViPPET may list none.
    for raw in videos:
        assert isinstance(raw, dict), "Each video entry must be an object"
        assert REQUIRED_VIDEO_KEYS.issubset(raw.keys()), (
            f"Video entry missing required keys: {REQUIRED_VIDEO_KEYS - raw.keys()}"
        )


@pytest.mark.smoke
def test_default_recordings_match_manifest(
    http_client: requests.Session,
    default_recordings_config: list[dict[str, Any]],
) -> None:
    """``GET /videos/default-recordings`` offers exactly the manifest videos.

    Sample videos are downloaded on demand, so they need not be in
    ``GET /videos``; the sample list must name each manifest video once,
    with a valid download status and a source.
    """
    recordings = fetch_default_video_recordings(http_client)
    assert recordings is not None, "GET /videos/default-recordings returned 404"

    listed = [r.get("filename") for r in recordings]
    expected = [r["filename"] for r in default_recordings_config]
    assert sorted(listed, key=str) == sorted(expected), (
        "GET /videos/default-recordings does not list exactly the videos of "
        f"default_recordings.yaml: missing {sorted(set(expected) - set(listed))}, "
        f"unexpected {sorted(set(listed) - set(expected), key=str)}"
    )
    for recording in recordings:
        name = recording["filename"]
        assert recording.get("status") in VALID_RECORDING_STATUSES, (
            f"Default recording '{name}' has an unknown status "
            f"{recording.get('status')!r}"
        )
        source = recording.get("source")
        assert isinstance(source, str) and source, (
            f"Default recording '{name}' has no source"
        )
