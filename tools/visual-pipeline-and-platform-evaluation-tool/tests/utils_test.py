import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import itertools

from gstpipeline import GstPipeline
import utils
from utils import (
    prepare_video_and_constants,
    run_pipeline_and_extract_metrics,
    is_yolov10_model,
)


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

    @patch("utils.discover_video_codec")
    @patch("utils.os.path.exists")
    @patch("utils.os.remove")
    def test_prepare_video_and_constants_output_file_removed(
        self, mock_remove, mock_exists, mock_discover_video_codec
    ):
        mock_exists.return_value = True
        mock_discover_video_codec.return_value = "h264"
        output_path, constants, param_grid = prepare_video_and_constants(
            **{
                "input_video_player": self.input_video,
                "object_detection_model": "SSDLite MobileNet V2 (INT8)",
                "object_detection_device": "CPU",
                "object_detection_batch_size": 1,
                "object_detection_nireq": 1,
                "object_detection_inference_interval": 1,
                "object_classification_model": "ResNet-50 TF (INT8)",
                "object_classification_device": "CPU",
                "object_classification_batch_size": 1,
                "object_classification_nireq": 1,
                "object_classification_inference_interval": 1,
                "object_classification_reclassify_interval": 1,
            }
        )
        mock_remove.assert_called_once()
        self.assertTrue(output_path.endswith(".mp4"))
        self.assertIn("VIDEO_PATH", constants)
        self.assertIn("VIDEO_CODEC", constants)
        self.assertIn("VIDEO_OUTPUT_PATH", constants)
        self.assertIn("object_detection_device", param_grid)
        self.assertIn("object_classification_device", param_grid)

    @patch("utils.discover_video_codec")
    def test_prepare_video_and_constants_unknown_codec(self, mock_discover_video_codec):
        mock_discover_video_codec.return_value = "unknown"
        with self.assertRaises(ValueError) as context:
            prepare_video_and_constants(
                **{
                    "input_video_player": self.input_video,
                    "object_detection_model": "SSDLite MobileNet V2 (INT8)",
                    "object_detection_device": "CPU",
                    "object_detection_batch_size": 1,
                    "object_detection_nireq": 1,
                    "object_detection_inference_interval": 1,
                    "object_classification_model": "ResNet-50 TF (INT8)",
                    "object_classification_device": "CPU",
                    "object_classification_batch_size": 1,
                    "object_classification_nireq": 1,
                    "object_classification_inference_interval": 1,
                    "object_classification_reclassify_interval": 1,
                }
            )
        self.assertIn(
            "Could not detect the video codec of the input file. Please provide a valid video file.",
            str(context.exception),
        )

    @patch("utils.discover_video_codec")
    def test_prepare_video_and_constants_not_supported_codec(
        self, mock_discover_video_codec
    ):
        mock_discover_video_codec.return_value = (
            "av1"  # Assuming 'av1' is not in the supported list
        )
        with self.assertRaises(ValueError) as context:
            prepare_video_and_constants(
                **{
                    "input_video_player": self.input_video,
                    "object_detection_model": "SSDLite MobileNet V2 (INT8)",
                    "object_detection_device": "CPU",
                    "object_detection_batch_size": 1,
                    "object_detection_nireq": 1,
                    "object_detection_inference_interval": 1,
                    "object_classification_model": "ResNet-50 TF (INT8)",
                    "object_classification_device": "CPU",
                    "object_classification_batch_size": 1,
                    "object_classification_nireq": 1,
                    "object_classification_inference_interval": 1,
                    "object_classification_reclassify_interval": 1,
                    "video_codec": "unsupported_codec",
                }
            )
        self.assertIn(
            f"Input video codec '{mock_discover_video_codec.return_value}' is not supported.",
            str(context.exception),
        )

    @patch("utils.Popen")
    @patch("utils.ps")
    @patch("utils.select.select")
    def test_run_pipeline_and_extract_metrics(self, mock_select, mock_ps, mock_popen):
        # Mock pipeline command
        class DummyPipeline(GstPipeline):
            def evaluate(
                self,
                constants,
                parameters,
                regular_channels,
                inference_channels,
                elements,
            ):
                return "gst-launch-1.0 videotestsrc ! fakesink"

        # Mock process
        process_mock = MagicMock()
        process_mock.poll.side_effect = [None, 0]
        # Avoid StopIteration by returning empty bytes forever after the real line
        process_mock.stdout.readline.side_effect = itertools.chain(
            [
                b"FpsCounter(average 10.0sec): total=100.0 fps, number-streams=1, per-stream=100.0 fps\n"
            ],
            itertools.repeat(b""),
        )
        process_mock.pid = 1234
        # Ensure fileno returns an int to avoid TypeError in select and bad fd errors
        process_mock.stdout.fileno.return_value = 10
        process_mock.stderr.fileno.return_value = 11
        mock_select.return_value = ([process_mock.stdout], [], [])
        mock_popen.return_value = process_mock
        mock_ps.Process.return_value.status.return_value = "zombie"

        constants = {"VIDEO_PATH": self.input_video, "VIDEO_OUTPUT_PATH": "out.mp4"}
        parameters = {
            "object_detection_device": ["CPU"],
            "object_classification_device": ["CPU"],
        }
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
        class DummyPipeline(GstPipeline):
            def evaluate(
                self,
                constants,
                parameters,
                regular_channels,
                inference_channels,
                elements,
            ):
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

    @patch("cv2.VideoCapture")
    def test_discover_video_codec(self, mock_videocap):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True

        # Mock VideoCapture to simulate a video file with H.264 codec
        # 'avc' as fourcc: ord('a') | ord('v')<<8 | ord('c')<<16 | ord(' ')<<24
        fourcc = (ord("a")) | (ord("v") << 8) | (ord("c") << 16) | (ord(" ") << 24)
        mock_cap.get.return_value = fourcc
        mock_videocap.return_value = mock_cap
        video_codec = utils.discover_video_codec("dummy.mp4")
        self.assertEqual(video_codec, "h264")

        # Mock VideoCapture to simulate a video file with H.265 codec
        # 'hevc' as fourcc: ord('h') | ord('e')<<8 | ord('v')<<16 | ord('c')<<24
        fourcc = (ord("h")) | (ord("e") << 8) | (ord("v") << 16) | (ord("c") << 24)
        mock_cap.get.return_value = fourcc
        mock_videocap.return_value = mock_cap
        video_codec = utils.discover_video_codec("dummy.mp4")
        self.assertEqual(video_codec, "h265")

        # Mock VideoCapture to simulate a video file with AV1 codec
        # 'av01' as fourcc: ord('a') | ord('v')<<8 | ord('0')<<16 | ord('1')<<24
        fourcc = (ord("a")) | (ord("v") << 8) | (ord("0") << 16) | (ord("1") << 24)
        mock_cap.get.return_value = fourcc
        mock_videocap.return_value = mock_cap
        video_codec = utils.discover_video_codec("dummy.mp4")
        self.assertEqual(video_codec, "av01")

    def test_discover_video_codec_non_existing_file(self):
        video_codec = utils.discover_video_codec("non_existing_file.mp4")
        self.assertEqual(video_codec, "unknown")

    def test_yolov10_model(self):
        # Test with a valid YOLO v10 model path
        self.assertTrue(is_yolov10_model("/path/to/yolov10s_model.xml"))

    def test_non_yolov10_model(self):
        # Test with a non-YOLO v10 model path
        self.assertFalse(is_yolov10_model("/path/to/other_model.xml"))

    def test_case_insensitivity(self):
        # Test with mixed-case YOLO v10 model path
        self.assertTrue(is_yolov10_model("/path/to/YOLOv10m_model.xml"))

    def test_empty_path(self):
        # Test with an empty string
        self.assertFalse(is_yolov10_model(""))

    def test_no_yolo_in_path(self):
        # Test with a path that does not contain "yolov10"
        self.assertFalse(is_yolov10_model("/path/to/yolo_model.xml"))


if __name__ == "__main__":
    unittest.main()
