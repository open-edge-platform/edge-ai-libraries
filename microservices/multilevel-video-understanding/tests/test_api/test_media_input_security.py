# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from video_analyzer.core.settings import settings
from video_analyzer.utils.file_utils import download_to_temp, validate_local_file_path, validate_remote_url


def _address(ip_address: str) -> tuple:
    return (2, 1, 6, "", (ip_address, 443))


@pytest.mark.unit
@pytest.mark.parametrize("ip_address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_validate_remote_url_rejects_non_public_dns_results(ip_address):
    with patch("video_analyzer.utils.file_utils.socket.getaddrinfo", return_value=[_address(ip_address)]):
        with pytest.raises(HTTPException, match="Invalid URL"):
            validate_remote_url("https://example.com/video.mp4")


@pytest.mark.unit
def test_validate_remote_url_accepts_public_dns_result():
    with patch("video_analyzer.utils.file_utils.socket.getaddrinfo", return_value=[_address("8.8.8.8")]):
        assert validate_remote_url("https://example.com/video.mp4") == "https://example.com/video.mp4"


@pytest.mark.unit
def test_download_rejects_private_url_before_making_request():
    with patch("video_analyzer.utils.file_utils.socket.getaddrinfo", return_value=[_address("127.0.0.1")]), \
         patch("video_analyzer.utils.file_utils.requests.get") as get:
        with pytest.raises(HTTPException):
            download_to_temp("http://localhost/video.mp4")
    get.assert_not_called()


@pytest.mark.unit
def test_validate_local_file_path_rejects_file_outside_allowed_directories(tmp_path, monkeypatch):
    permitted_dir = tmp_path / "media"
    permitted_dir.mkdir()
    permitted_file = permitted_dir / "safe.mp4"
    permitted_file.touch()
    outside_file = tmp_path / "outside.mp4"
    outside_file.touch()
    monkeypatch.setattr(settings, "VIDEO_ALLOWED_PATHS", [str(permitted_dir)])

    assert validate_local_file_path(str(permitted_file)) == str(permitted_file)
    with pytest.raises(HTTPException, match="Invalid local file path"):
        validate_local_file_path(str(outside_file))