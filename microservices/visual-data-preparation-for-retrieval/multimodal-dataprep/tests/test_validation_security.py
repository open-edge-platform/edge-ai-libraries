# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from src.common import DataPrepException
from src.core.validation import sanitize_bucket_name, sanitize_video_id, sanitize_video_name


@pytest.mark.parametrize("video_id", ["../secret", "abc/def", "abc\\def", "a..b", ".."])
def test_sanitize_video_id_rejects_unsafe_paths(video_id):
    with pytest.raises(DataPrepException):
        sanitize_video_id(video_id)


def test_sanitize_video_id_accepts_safe_identifier():
    assert sanitize_video_id("video_123-abc.1") == "video_123-abc.1"


@pytest.mark.parametrize("video_name", ["../video.mp4", "folder/video.mp4", "folder\\video.mp4"])
def test_sanitize_video_name_rejects_unsafe_paths(video_name):
    with pytest.raises(DataPrepException):
        sanitize_video_name(video_name)


def test_sanitize_video_name_accepts_safe_filename():
    assert sanitize_video_name("video (1).mp4") == "video (1).mp4"


@pytest.mark.parametrize(
    "bucket_name", ["video/summary", "video\\summary", "video..summary", "AA", "A" * 64]
)
def test_sanitize_bucket_name_rejects_invalid_values(bucket_name):
    with pytest.raises(DataPrepException):
        sanitize_bucket_name(bucket_name)


def test_sanitize_bucket_name_accepts_safe_value():
    assert sanitize_bucket_name("video-summary") == "video-summary"
