# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the media-type registry helpers (``src.core.media``)."""

import pytest

from src.core.media import (
    content_type_for_filename,
    detect_media_kind,
    extension_for_pil_format,
    is_image_file,
    is_media_file,
    is_video_file,
)


@pytest.mark.parametrize(
    "name,expected",
    [
        ("clip.mp4", True),
        ("CLIP.MP4", True),
        ("photo.jpg", True),
        ("photo.JPEG", True),
        ("photo.png", True),
        ("photo.webp", True),
        ("photo.bmp", True),
        ("photo.gif", True),
        (".content_sha256", False),
        (".dedup/abc123", False),
        ("meta.json", False),
        ("notes.txt", False),
        ("", False),
        (None, False),
    ],
)
def test_is_media_file(name, expected):
    assert is_media_file(name) is expected


def test_kind_helpers_are_mutually_consistent():
    assert is_video_file("a.mp4") and not is_image_file("a.mp4")
    assert is_image_file("a.png") and not is_video_file("a.png")


@pytest.mark.parametrize(
    "name,kind",
    [
        ("a.mp4", "video"),
        ("a.jpg", "image"),
        ("a.jpeg", "image"),
        ("a.png", "image"),
        ("a.txt", None),
        ("noext", None),
    ],
)
def test_detect_media_kind(name, kind):
    assert detect_media_kind(name) == kind


@pytest.mark.parametrize(
    "name,mime",
    [
        ("a.mp4", "video/mp4"),
        ("a.jpg", "image/jpeg"),
        ("a.jpeg", "image/jpeg"),
        ("a.png", "image/png"),
        ("a.webp", "image/webp"),
        ("a.unknown", "application/octet-stream"),
    ],
)
def test_content_type_for_filename(name, mime):
    assert content_type_for_filename(name) == mime


@pytest.mark.parametrize(
    "pil_format,ext",
    [
        ("JPEG", ".jpg"),
        ("PNG", ".png"),
        ("WEBP", ".webp"),
        ("MPO", ".jpg"),
        ("TIFF", None),
        (None, None),
    ],
)
def test_extension_for_pil_format(pil_format, ext):
    assert extension_for_pil_format(pil_format) == ext
