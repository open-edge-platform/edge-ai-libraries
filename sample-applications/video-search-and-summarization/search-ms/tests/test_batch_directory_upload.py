# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from src.utils import utils


class BatchDirectoryUploadTests(unittest.TestCase):
    def setUp(self):
        utils.uploaded_files.clear()

    def tearDown(self):
        utils.uploaded_files.clear()

    def test_single_upload_only_registers_video(self):
        response = Mock()
        response.json.return_value = {"videoId": "video-1"}

        with tempfile.NamedTemporaryFile(suffix=".mp4") as video:
            with (
                patch.object(utils.requests, "post", return_value=response) as post,
                patch.object(utils, "request_proxies", return_value=None),
            ):
                video_id = utils.upload_single_video_with_retry(video.name)

        self.assertEqual(video_id, "video-1")
        post.assert_called_once()
        self.assertTrue(post.call_args.args[0].endswith("/videos"))
        self.assertNotIn("search-embeddings", post.call_args.args[0])

    def test_submit_embedding_batch_uses_pipeline_manager_batch_endpoint(self):
        response = Mock()
        response.json.return_value = {"job_id": "job-1", "accepted": 2}

        with (
            patch.object(utils.requests, "post", return_value=response) as post,
            patch.object(utils, "request_proxies", return_value=None),
        ):
            job_id = utils.submit_embedding_batch(["video-1", "video-2"])

        self.assertEqual(job_id, "job-1")
        post.assert_called_once_with(
            f"{utils.settings.VIDEO_UPLOAD_ENDPOINT}/videos/search-embeddings-batch",
            json={"videoIds": ["video-1", "video-2"]},
            proxies=None,
        )

    def test_wait_for_embedding_batch_returns_terminal_status(self):
        running = Mock()
        running.json.return_value = {"job_id": "job-1", "state": "running"}
        completed = Mock()
        completed.json.return_value = {
            "job_id": "job-1",
            "state": "completed",
            "items": [],
        }

        with (
            patch.object(
                utils.requests,
                "get",
                side_effect=[running, completed],
            ) as get,
            patch.object(utils, "request_proxies", return_value=None),
            patch.object(utils.time, "sleep"),
        ):
            status = utils.wait_for_embedding_batch("job-1")

        self.assertEqual(status["state"], "completed")
        self.assertEqual(get.call_count, 2)
        self.assertTrue(
            get.call_args.args[0].endswith(
                "/videos/search-embeddings-jobs/job-1"
            )
        )

    def test_batch_result_tracks_only_successful_files(self):
        paths = ["/watch/one.mp4", "/watch/two.mp4"]
        status = {
            "state": "completed_with_errors",
            "items": [
                {"video_id": "video-1", "status": "success"},
                {
                    "video_id": "video-2",
                    "status": "error",
                    "message": "embedding failed",
                },
            ],
        }

        with (
            patch.object(
                utils,
                "upload_single_video_with_retry",
                side_effect=["video-1", "video-2"],
            ),
            patch.object(utils, "submit_embedding_batch", return_value="job-1") as submit,
            patch.object(utils, "wait_for_embedding_batch", return_value=status),
            patch.object(utils.settings, "DELETE_PROCESSED_FILES", False),
        ):
            successful = utils.upload_videos_to_dataprep(paths)

        self.assertEqual(successful, {"/watch/one.mp4"})
        self.assertEqual(utils.uploaded_files, {"/watch/one.mp4"})
        submit.assert_called_once_with(["video-1", "video-2"])

    def test_successful_batch_deletes_processed_files_when_enabled(self):
        handles = [
            tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            for _ in range(2)
        ]
        paths = [handle.name for handle in handles]
        for handle in handles:
            handle.close()

        status = {
            "state": "completed",
            "items": [
                {"video_id": "video-1", "status": "success"},
                {"video_id": "video-2", "status": "success"},
            ],
        }

        try:
            with (
                patch.object(
                    utils,
                    "upload_single_video_with_retry",
                    side_effect=["video-1", "video-2"],
                ),
                patch.object(utils, "submit_embedding_batch", return_value="job-1"),
                patch.object(utils, "wait_for_embedding_batch", return_value=status),
                patch.object(utils.settings, "DELETE_PROCESSED_FILES", True),
            ):
                successful = utils.upload_videos_to_dataprep(paths)

            self.assertEqual(successful, set(paths))
            self.assertTrue(all(not os.path.exists(path) for path in paths))
        finally:
            for path in paths:
                if os.path.exists(path):
                    os.remove(path)

    def test_large_watcher_group_is_split_into_configured_batches(self):
        paths = ["/watch/one.mp4", "/watch/two.mp4", "/watch/three.mp4"]

        def completed_status(job_id):
            suffix = job_id.removeprefix("job-")
            return {
                "state": "completed",
                "items": [{"video_id": suffix, "status": "success"}],
            }

        with (
            patch.object(
                utils,
                "upload_single_video_with_retry",
                side_effect=["video-1", "video-2", "video-3"],
            ),
            patch.object(
                utils,
                "submit_embedding_batch",
                side_effect=["job-video-1", "job-video-2", "job-video-3"],
            ) as submit,
            patch.object(
                utils,
                "wait_for_embedding_batch",
                side_effect=completed_status,
            ),
            patch.object(utils.settings, "WATCH_BATCH_SIZE", 1),
            patch.object(utils.settings, "DELETE_PROCESSED_FILES", False),
        ):
            successful = utils.upload_videos_to_dataprep(paths)

        self.assertEqual(successful, set(paths))
        self.assertEqual(
            [call.args[0] for call in submit.call_args_list],
            [["video-1"], ["video-2"], ["video-3"]],
        )

    def test_repeated_event_does_not_delete_an_already_processed_path(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as video:
            path = video.name
        utils.uploaded_files.add(path)

        try:
            with patch.object(utils.settings, "DELETE_PROCESSED_FILES", True):
                successful = utils.upload_videos_to_dataprep([path])

            self.assertEqual(successful, {path})
            self.assertTrue(os.path.exists(path))
        finally:
            if os.path.exists(path):
                os.remove(path)


if __name__ == "__main__":
    unittest.main()
