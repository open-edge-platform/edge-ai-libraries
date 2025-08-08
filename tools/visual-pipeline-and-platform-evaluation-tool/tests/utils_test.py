import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import itertools

import utils
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
            input_video_player=self.input_video,
            object_detection_model="SSDLite MobileNet V2 (INT8)",
            object_detection_device="CPU",
            object_detection_batch_size=1,
            object_detection_nireq=1,
            object_detection_inference_interval=1,
            object_classification_model="ResNet-50 TF (INT8)",
            object_classification_device="CPU",
            object_classification_batch_size=1,
            object_classification_nireq=1,
            object_classification_inference_interval=1,
            object_classification_reclassify_interval=1,
        )
        mock_remove.assert_called_once()
        self.assertTrue(output_path.endswith(".mp4"))
        self.assertIn("VIDEO_PATH", constants)
        self.assertIn("VIDEO_OUTPUT_PATH", constants)
        self.assertIn("object_detection_device", param_grid)
        self.assertIn("object_classification_device", param_grid)

    @patch("utils.Popen")
    @patch("utils.ps")
    @patch("utils.select.select")
    def test_run_pipeline_and_extract_metrics(self, mock_select, mock_ps, mock_popen):
        # Mock pipeline command
        class DummyPipeline:
            def evaluate(self, *_):
                return "gst-launch-1.0 videotestsrc ! fakesink"

        # Mock process
        process_mock = MagicMock()
        process_mock.poll.side_effect = [None, 0]
        # Avoid StopIteration by returning empty bytes forever after the real line
        process_mock.stdout.readline.side_effect = itertools.chain(
            [b"FpsCounter(average 10.0sec): total=100.0 fps, number-streams=1, per-stream=100.0 fps\n"],
            itertools.repeat(b"")
        )
        process_mock.pid = 1234
        # Ensure fileno returns an int to avoid TypeError in select and bad fd errors
        process_mock.stdout.fileno.return_value = 10
        process_mock.stderr.fileno.return_value = 11
        mock_select.return_value = ([process_mock.stdout], [], [])
        mock_popen.return_value = process_mock
        mock_ps.Process.return_value.status.return_value = "zombie"

        constants = {"VIDEO_PATH": self.input_video, "VIDEO_OUTPUT_PATH": "out.mp4"}
        parameters = {"object_detection_device": ["CPU"], "object_classification_device": ["CPU"]}
        gen = run_pipeline_and_extract_metrics(
            DummyPipeline(),
            constants,
            parameters,
            channels=1,
            elements=[],
            poll_interval=0,
        )
        try:
            while True:
                next(gen)
        except StopIteration as e:
            results = e.value

        self.assertIsInstance(results, list)
        self.assertEqual(results[0]["total_fps"], 100.0)
        self.assertEqual(results[0]["per_stream_fps"], 100.0)
        self.assertEqual(results[0]["num_streams"], 1)

    @patch("utils.Popen")
    def test_stop_pipeline(self, mock_popen):
        # Mock pipeline command
        class DummyPipeline:
            def evaluate(self, *_):
                return "gst-launch-1.0 videotestsrc ! fakesink"

        # Mock process
        process_mock = MagicMock()
        process_mock.poll.side_effect = [None]
        # Avoid TypeError in select by providing fileno
        process_mock.stdout.fileno.return_value = 10
        process_mock.stderr.fileno.return_value = 11
        mock_popen.return_value = process_mock

        constants = {"VIDEO_PATH": self.input_video, "VIDEO_OUTPUT_PATH": "out.mp4"}
        parameters = {"object_detection_device": ["CPU"]}

        # Signal to stop the pipeline
        utils.cancelled = True

        # Run the pipeline and handle generator
        gen = run_pipeline_and_extract_metrics(
            DummyPipeline(),
            constants,
            parameters,
            channels=1,
            elements=[],
            poll_interval=0,
        )
        try:
            # Exhaust generator to get return value
            while True:
                next(gen)
        except StopIteration as e:
            results = e.value

        self.assertIsInstance(results, list)
        self.assertEqual(utils.cancelled, False)
        process_mock.terminate.assert_called_once()
        self.assertEqual(results[0]["total_fps"], "N/A")
        self.assertEqual(results[0]["per_stream_fps"], "N/A")
        self.assertEqual(results[0]["num_streams"], "N/A")


if __name__ == "__main__":
    unittest.main()
