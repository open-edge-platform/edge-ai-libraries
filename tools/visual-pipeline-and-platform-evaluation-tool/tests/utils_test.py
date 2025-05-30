import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from utils import prepare_video_and_constants, run_pipeline_and_extract_metrics


class TestUtils(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for models and output
        self.temp_dir = tempfile.mkdtemp()
        self.models_path = os.path.join(self.temp_dir, "models")
        os.makedirs(self.models_path, exist_ok=True)
        self.input_video = os.path.join(self.temp_dir, "input.mp4")
        with open(self.input_video, "w") as f:
            f.write("dummy video content")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    @patch("utils.os.path.exists")
    @patch("utils.os.remove")
    def test_prepare_video_and_constants_output_file_removed(
        self, mock_remove, mock_exists
    ):
        mock_exists.return_value = True
        output_path, constants, param_grid = prepare_video_and_constants(
            self.input_video,
            "SSDLite MobileNet V2",
            "CPU",
            batch_size=1,
            nireq=1,
            inference_interval=1,
        )
        mock_remove.assert_called_once()
        self.assertTrue(output_path.endswith(".mp4"))
        self.assertIn("VIDEO_PATH", constants)
        self.assertIn("VIDEO_OUTPUT_PATH", constants)
        self.assertIn("object_detection_device", param_grid)

    @patch("utils.Popen")
    @patch("utils.ps")
    def test_run_pipeline_and_extract_metrics(self, mock_ps, mock_popen):
        # Mock pipeline command
        class DummyPipeline:
            def evaluate(
                self, constants, params, regular_channels, inference_channels, elements
            ):
                return "echo FpsCounter(average 10.0sec): total=100.0 fps, number-streams=1, per-stream=100.0 fps"

        # Mock process
        process_mock = MagicMock()
        process_mock.poll.side_effect = [None, 0]
        process_mock.stdout.readline.side_effect = [
            b"FpsCounter(average 10.0sec): total=100.0 fps, number-streams=1, per-stream=100.0 fps\n",
            b"",
        ]
        process_mock.pid = 1234
        mock_popen.return_value = process_mock
        mock_ps.Process.return_value.status.return_value = "zombie"

        constants = {"VIDEO_PATH": self.input_video, "VIDEO_OUTPUT_PATH": "out.mp4"}
        parameters = {"object_detection_device": ["CPU"]}
        results = run_pipeline_and_extract_metrics(
            DummyPipeline(),
            constants,
            parameters,
            channels=1,
            elements=[],
            poll_interval=0,
        )
        self.assertIsInstance(results, list)
        self.assertEqual(results[0]["total_fps"], 100.0)
        self.assertEqual(results[0]["per_stream_fps"], 100.0)
        self.assertEqual(results[0]["num_streams"], 1)


if __name__ == "__main__":
    unittest.main()
