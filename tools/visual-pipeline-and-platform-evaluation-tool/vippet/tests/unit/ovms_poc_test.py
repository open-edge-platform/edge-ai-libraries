# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.ovms_poc import router as ovms_poc_router
from managers.ovms_poc_manager import OvmsPocManager
from ovms_poc_runner import OvmsInferenceMetrics, _read_ovms_inference_metrics


class TestOvmsPocAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = FastAPI()
        app.include_router(ovms_poc_router, prefix="/ovms-poc")
        cls.client = TestClient(app)

    @patch("api.routes.ovms_poc.OvmsPocManager")
    def test_run_rejects_invalid_request_before_starting_job(
        self, mock_manager_class: MagicMock
    ) -> None:
        response = self.client.post(
            "/ovms-poc/run",
            json={
                "input_video": "auto/input.mp4",
                "graph_name": "unsupportedGraph",
                "max_parallel_requests": 9,
            },
        )

        self.assertEqual(response.status_code, 422)
        mock_manager_class.assert_not_called()


class TestOvmsPocManager(unittest.TestCase):
    def setUp(self) -> None:
        OvmsPocManager._instance = None

    def tearDown(self) -> None:
        OvmsPocManager._instance = None

    def test_resolve_input_video_accepts_file_below_input_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            input_directory = Path(temporary_directory)
            input_video = input_directory / "auto" / "input.mp4"
            input_video.parent.mkdir()
            input_video.touch()

            with patch("managers.ovms_poc_manager.INPUT_VIDEO_DIR", input_directory):
                resolved = OvmsPocManager._resolve_input_video("auto/input.mp4")

            self.assertEqual(resolved, input_video)

    def test_resolve_input_video_rejects_parent_traversal(self) -> None:
        with self.assertRaisesRegex(ValueError, "relative path"):
            OvmsPocManager._resolve_input_video("../outside.mp4")

    def test_resolve_input_video_rejects_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as input_temporary_directory:
            with tempfile.TemporaryDirectory() as outside_temporary_directory:
                input_directory = Path(input_temporary_directory)
                outside_video = Path(outside_temporary_directory) / "outside.mp4"
                outside_video.touch()
                (input_directory / "linked.mp4").symlink_to(outside_video)

                with patch(
                    "managers.ovms_poc_manager.INPUT_VIDEO_DIR", input_directory
                ):
                    with self.assertRaisesRegex(ValueError, "located below"):
                        OvmsPocManager._resolve_input_video("linked.mp4")

    def test_get_metadata_returns_only_latest_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            job_directory = Path(temporary_directory)
            metadata_path = job_directory / "predictions.jsonl"
            metadata_path.write_text(
                "".join(f'{{"frame_id": {frame_id}}}\n' for frame_id in range(5)),
                encoding="utf-8",
            )
            manager = OvmsPocManager()
            manager._job_directories["job-id"] = job_directory

            records = manager.get_metadata("job-id", limit=2)

            self.assertEqual(records, [{"frame_id": 3}, {"frame_id": 4}])


class TestOvmsPocMetrics(unittest.TestCase):
    @patch("ovms_poc_runner.httpx.get")
    def test_read_ovms_inference_metrics_aggregates_matching_series(
        self, mock_get: MagicMock
    ) -> None:
        response = MagicMock()
        response.text = "\n".join(
            (
                'ovms_inference_time_us_count{name="target",version="1"} 2',
                'ovms_inference_time_us_count{name="target",version="2"} 3',
                'ovms_inference_time_us_sum{name="target",version="1"} 4000',
                'ovms_inference_time_us_sum{name="target",version="2"} 6500',
                'ovms_inference_time_us_count{name="other",version="1"} 99',
            )
        )
        mock_get.return_value = response

        result = _read_ovms_inference_metrics("http://ovms:8080/metrics", "target")

        self.assertEqual(result, OvmsInferenceMetrics(count=5, total_time_us=10500))
        response.raise_for_status.assert_called_once_with()
        mock_get.assert_called_once_with("http://ovms:8080/metrics", timeout=1.0)


if __name__ == "__main__":
    unittest.main()
