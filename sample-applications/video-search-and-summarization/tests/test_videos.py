# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
TIER 3 — Video Management Tests

These tests verify the core video CRUD operations through the Pipeline Manager.
They must pass before any search (TIER 4) or summarization (TIER 5) tests run,
because both pipelines start with a video upload.

Run with:
    cd test-functional/
    pytest test_videos.py -v

Tests in this file:
    T3.1 - test_upload_valid_video          (positive: upload MP4, get videoId)
    T3.2 - test_list_videos                 (positive: list returns object, not bare array)
    T3.3 - test_get_video_by_id             (positive: get single video by ID)
    T3.4 - test_upload_invalid_file_type    (negative: non-MP4 upload → 4xx)
    T3.5 - test_upload_missing_video_field  (negative: empty POST body → 4xx)
    T3.6 - test_get_nonexistent_video       (negative: fake ID → 404)
"""

import pytest
import requests

from conftest import TEST_VIDEO_PATH, TEST_NONVIDEO_PATH


class TestVideos:

    # ──────────────────────────────────────────────────────────────────────────
    # T3.1 — Upload a valid MP4 and receive a videoId
    # ──────────────────────────────────────────────────────────────────────────

    def test_upload_valid_video(self, base_url, vss_health, uploaded_video_id):
        if not vss_health:
            pytest.fail("VSS stack did not become healthy within the timeout period.")

        # uploaded_video_id fixture already uploaded and validated the response.
        # Here we just verify the ID looks like a real non-empty string.
        assert isinstance(uploaded_video_id, str), (
            f"Expected 'videoId' to be a string, got {type(uploaded_video_id).__name__}: "
            f"{uploaded_video_id!r}"
        )
        assert len(uploaded_video_id) > 0, "videoId must not be an empty string"

    # ──────────────────────────────────────────────────────────────────────────
    # T3.2 — List all videos returns an object with a 'videos' key (not bare array)
    # ──────────────────────────────────────────────────────────────────────────

    def test_list_videos(self, base_url, vss_health, uploaded_video_id):

        if not vss_health:
            pytest.fail("VSS stack did not become healthy within the timeout period.")

        response = requests.get(f"{base_url}/manager/videos", timeout=30)

        assert response.status_code == 200, (
            f"Expected 200 from GET /manager/videos, got {response.status_code}. "
            f"Response: {response.text}"
        )

        body = response.json()

        assert isinstance(body, dict), (
            f"Expected a JSON object from GET /manager/videos, "
            f"got {type(body).__name__}: {body}"
        )

        assert "videos" in body, (
            f"Expected 'videos' key in response, got keys: {list(body.keys())}"
        )

        assert isinstance(body["videos"], list), (
            f"Expected body['videos'] to be a list, "
            f"got {type(body['videos']).__name__}"
        )

        video_ids_in_list = [v.get("videoId") for v in body["videos"]]
        assert uploaded_video_id in video_ids_in_list, (
            f"Uploaded video '{uploaded_video_id}' not found in GET /manager/videos list.\n"
            f"IDs returned: {video_ids_in_list}"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # T3.3 — Get a single video by its ID
    # ──────────────────────────────────────────────────────────────────────────

    def test_get_video_by_id(self, base_url, vss_health, uploaded_video_id):
        if not vss_health:
            pytest.fail("VSS stack did not become healthy within the timeout period.")

        response = requests.get(
            f"{base_url}/manager/videos/{uploaded_video_id}", timeout=30
        )

        assert response.status_code == 200, (
            f"Expected 200 from GET /manager/videos/{uploaded_video_id}, "
            f"got {response.status_code}. Response: {response.text}"
        )

        body = response.json()

        assert "video" in body, (
            f"Expected 'video' key in response, got keys: {list(body.keys())}\n"
            f"Full response: {body}"
        )

        video = body["video"]

        assert video.get("videoId") == uploaded_video_id, (
            f"Returned videoId {video.get('videoId')!r} does not match "
            f"uploaded ID {uploaded_video_id!r}"
        )

        assert "dataStore" in video, (
            f"Expected 'dataStore' key in video object: {video}"
        )
        assert "fileName" in video["dataStore"], (
            f"Expected 'fileName' in dataStore: {video['dataStore']}"
        )
        assert video["dataStore"]["fileName"], (
            f"dataStore.fileName must not be empty: {video['dataStore']}"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # T3.4 — Uploading a non-video file must return a 4xx client error
    # ──────────────────────────────────────────────────────────────────────────

    def test_upload_invalid_file_type(self, base_url, vss_health):
        if not vss_health:
            pytest.fail("VSS stack did not become healthy within the timeout period.")

        assert TEST_NONVIDEO_PATH.exists(), (
            f"Non-video test file not found: {TEST_NONVIDEO_PATH}"
        )

        with open(TEST_NONVIDEO_PATH, "rb") as bad_file:
            response = requests.post(
                f"{base_url}/manager/videos",
                files={"video": ("not-a-video.txt", bad_file, "text/plain")},
                timeout=30,
            )

        assert response.status_code in range(400, 500), (
            f"Expected a 4xx client error for invalid file type, "
            f"got {response.status_code}. Response: {response.text}"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # T3.5 — POST without a 'video' field must return a 4xx client error
    # ──────────────────────────────────────────────────────────────────────────

    def test_upload_missing_video_field(self, base_url, vss_health):
        if not vss_health:
            pytest.fail("VSS stack did not become healthy within the timeout period.")

        # Send a POST with NO files — intentionally missing the required 'video' field
        response = requests.post(
            f"{base_url}/manager/videos",
            timeout=30,
        )

        assert response.status_code >= 400, (
            f"Expected an error response (>= 400) when 'video' field is missing, "
            f"got {response.status_code}. Response: {response.text}\n"
            "The server should not accept a video upload with no file attached."
        )

    # ──────────────────────────────────────────────────────────────────────────
    # T3.6 — GET with a non-existent video ID must return HTTP 404
    # ──────────────────────────────────────────────────────────────────────────

    def test_get_nonexistent_video(self, base_url, vss_health):
        if not vss_health:
            pytest.fail("VSS stack did not become healthy within the timeout period.")

        fake_id = "nonexistent-video-id-00000000"

        response = requests.get(
            f"{base_url}/manager/videos/{fake_id}", timeout=30
        )

        assert response.status_code == 404, (
            f"Expected 404 for non-existent video ID '{fake_id}', "
            f"got {response.status_code}. Response: {response.text}"
        )
