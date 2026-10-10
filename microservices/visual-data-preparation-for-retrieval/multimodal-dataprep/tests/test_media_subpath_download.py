# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Addressing a specific object inside a media directory.

Live-stream media is stored a level below ``video_id``
(``<stream_id>/segments/<ts>.mp4``, ``<stream_id>/frames/<ts>_<idx>.jpg``), so
``GET /media/download?video_id=<stream_id>`` alone cannot name the segment that
an embedding points at. ``media_path`` closes that gap -- and must not become a
path-traversal hole while doing it.
"""

from __future__ import annotations

from unittest import mock

import pytest

from src.common import DataPrepException
from src.core.validation import sanitize_media_subpath


class TestSanitizeMediaSubpath:
    """The validator is the only thing standing between a query param and storage."""

    @pytest.mark.parametrize(
        "path",
        [
            "segments/1790655530.mp4",
            "frames/1790655530_000000015.jpg",
            "clip.mp4",
            "a/b/c/d",
        ],
    )
    def test_accepts_safe_relative_paths(self, path):
        assert sanitize_media_subpath(path) == path

    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_absent_path_is_none(self, empty):
        assert sanitize_media_subpath(empty) is None

    @pytest.mark.parametrize(
        "path",
        [
            "../etc/passwd",
            "segments/../../etc/passwd",
            "..",
            "segments/..",
            "./segments/x.mp4",
        ],
    )
    def test_rejects_traversal(self, path):
        with pytest.raises(DataPrepException) as exc:
            sanitize_media_subpath(path)
        assert exc.value.status_code == 400

    @pytest.mark.parametrize("path", ["/abs/path.mp4", "segments\\x.mp4", "\\x.mp4"])
    def test_rejects_absolute_and_backslash(self, path):
        with pytest.raises(DataPrepException) as exc:
            sanitize_media_subpath(path)
        assert exc.value.status_code == 400

    @pytest.mark.parametrize("path", ["segments//x.mp4", "segments/", "a//b"])
    def test_rejects_empty_components(self, path):
        # An empty component would silently collapse and change the resolved object.
        with pytest.raises(DataPrepException) as exc:
            sanitize_media_subpath(path)
        assert exc.value.status_code == 400

    def test_rejects_paths_that_are_too_deep(self):
        with pytest.raises(DataPrepException, match="at most"):
            sanitize_media_subpath("a/b/c/d/e")

    @pytest.mark.parametrize("path", ["seg ments/x.mp4", "segments/x;rm -rf.mp4", "seg$/x.mp4"])
    def test_rejects_unexpected_characters(self, path):
        with pytest.raises(DataPrepException) as exc:
            sanitize_media_subpath(path)
        assert exc.value.status_code == 400


class TestResolveMediaSourceWithSubpath:
    """Resolution must stay anchored to the caller's video_id."""

    def test_resolves_object_under_the_video_id_prefix(self):
        from src.core.utils.video_utils import resolve_media_source

        client = mock.Mock()
        client.object_exists_by_path.return_value = True

        with mock.patch("src.core.utils.video_utils.get_minio_client", return_value=client):
            source = resolve_media_source(
                "live-streams", "streamabc", media_path="segments/1790655530.mp4"
            )

        client.object_exists_by_path.assert_called_once_with(
            "live-streams", "streamabc/segments/1790655530.mp4"
        )
        assert source.object_name == "streamabc/segments/1790655530.mp4"
        assert source.filename == "1790655530.mp4"

    def test_missing_object_is_404_not_a_fallback(self):
        from src.core.utils.video_utils import resolve_media_source

        client = mock.Mock()
        client.object_exists_by_path.return_value = False

        with mock.patch("src.core.utils.video_utils.get_minio_client", return_value=client):
            with pytest.raises(DataPrepException) as exc:
                resolve_media_source("live-streams", "streamabc", media_path="segments/nope.mp4")

        assert exc.value.status_code == 404
        # An explicit path must never silently fall back to "some other object
        # in this directory" -- that would serve the wrong media.
        client.get_video_in_directory.assert_not_called()

    def test_without_subpath_the_directory_lookup_is_used(self):
        from src.core.utils.video_utils import resolve_media_source

        client = mock.Mock()
        client.get_video_in_directory.return_value = "streamabc/clip.mp4"

        with mock.patch("src.core.utils.video_utils.get_minio_client", return_value=client):
            source = resolve_media_source("video-summary", "streamabc")

        assert source.object_name == "streamabc/clip.mp4"
        client.object_exists_by_path.assert_not_called()
