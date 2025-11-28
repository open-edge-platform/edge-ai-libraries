import unittest
from unittest.mock import Mock, patch

from video_encoder import (
    VideoEncoder,
    GPU_0,
    OTHER,
)
from api.api_schemas import EncoderDeviceConfig


class TestVideoEncoderClass(unittest.TestCase):
    """Test cases for VideoEncoder class."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a fresh instance for each test
        with patch("video_encoder.GstInspector"):
            self.encoder = VideoEncoder()

    @patch("video_encoder.GstInspector")
    def test_initialization(self, mock_gst_inspector):
        """Test VideoEncoder initialization."""
        # Reset singleton for this test
        encoder = VideoEncoder()
        self.assertIsNotNone(encoder.gst_inspector)
        self.assertIn("h264", encoder.encoder_configs)
        mock_gst_inspector.assert_called_once()

    def test_select_gpu_single_gpu(self):
        """Test GPU device without index."""
        gpu_id, vaapi_suffix = self.encoder.select_gpu("GPU")
        self.assertEqual(gpu_id, 0)
        self.assertIsNone(vaapi_suffix)

    def test_select_gpu_first_with_index(self):
        """Test GPU.0 device."""
        gpu_id, vaapi_suffix = self.encoder.select_gpu("GPU.0")
        self.assertEqual(gpu_id, 0)
        self.assertIsNone(vaapi_suffix)

    def test_select_gpu_second_gpu(self):
        """Test GPU.1 device with vaapi suffix."""
        gpu_id, vaapi_suffix = self.encoder.select_gpu("GPU.1")
        self.assertEqual(gpu_id, 1)
        self.assertEqual(vaapi_suffix, "129")

    def test_select_gpu_cpu_device(self):
        """Test non-GPU device (CPU)."""
        gpu_id, vaapi_suffix = self.encoder.select_gpu("CPU")
        self.assertEqual(gpu_id, -1)
        self.assertIsNone(vaapi_suffix)

    def test_select_element_gpu_0(self):
        """Test selecting encoder for GPU 0."""
        self.encoder.gst_inspector.elements = [("elem1", "vah264enc")]

        encoder_device = EncoderDeviceConfig(device_name="GPU", gpu_id=0)
        encoder_dict = {
            GPU_0: [("vah264enc", "vah264enc")],
            OTHER: [("x264enc", "x264enc")],
        }

        result = self.encoder.select_element(encoder_dict, encoder_device, None)
        self.assertEqual(result, "vah264enc")

    def test_select_element_fallback_to_cpu(self):
        """Test fallback to CPU encoder when GPU encoder not available."""
        self.encoder.gst_inspector.elements = [("elem1", "x264enc")]

        encoder_device = EncoderDeviceConfig(device_name="GPU", gpu_id=0)
        encoder_dict = {
            GPU_0: [("vah264enc", "vah264enc")],
            OTHER: [("x264enc", "x264enc bitrate=16000")],
        }

        result = self.encoder.select_element(encoder_dict, encoder_device, None)
        self.assertEqual(result, "x264enc bitrate=16000")

    @patch("video_encoder.videos_manager")
    def test_detect_codec_from_input(self, mock_videos_manager):
        """Test codec detection from input videos."""
        mock_video = Mock()
        mock_video.codec = "h265"
        mock_videos_manager.get_video = Mock(return_value=mock_video)

        codec = self.encoder._detect_codec_from_input(["video1.mp4"])
        self.assertEqual(codec, "h265")

    @patch("video_encoder.videos_manager")
    def test_detect_codec_from_input_defaults_to_h264(self, mock_videos_manager):
        """Test codec detection defaults to h264 when video not found."""
        mock_videos_manager.get_video = Mock(return_value=None)

        codec = self.encoder._detect_codec_from_input(["video1.mp4"])
        self.assertEqual(codec, "h264")

    def test_detect_codec_empty_list(self):
        """Test codec detection with empty list."""
        codec = self.encoder._detect_codec_from_input([])
        self.assertEqual(codec, "h264")

    def test_validate_codec_valid(self):
        """Test codec validation with valid codec."""
        # Should not raise
        self.encoder._validate_codec("h264")
        self.encoder._validate_codec("h265")

    def test_validate_codec_invalid(self):
        """Test codec validation with invalid codec."""
        with self.assertRaises(ValueError) as context:
            self.encoder._validate_codec("av1")
        self.assertIn("Unsupported codec", str(context.exception))
        self.assertIn("av1", str(context.exception))

    @patch("video_encoder.videos_manager")
    def test_replace_fakesink_with_video_output(self, mock_videos_manager):
        """Test replacing fakesink with video output."""
        self.encoder.gst_inspector.elements = [("elem", "vah264enc")]

        mock_video = Mock()
        mock_video.codec = "h264"
        mock_videos_manager.get_video = Mock(return_value=mock_video)

        pipeline_str = "videotestsrc ! fakesink"
        encoder_device = EncoderDeviceConfig(device_name="GPU", gpu_id=0)
        pipeline_id = "test-pipeline-123"

        result, output_paths = self.encoder.replace_fakesink_with_video_output(
            pipeline_id, pipeline_str, encoder_device, ["input.mp4"]
        )

        self.assertIn("vah264enc", result)
        self.assertIn("h264parse", result)
        self.assertIn("mp4mux", result)
        self.assertIn("filesink location=", result)
        self.assertNotIn("fakesink", result)
        self.assertEqual(len(output_paths), 1)
        self.assertIn("pipeline_output_test-pipeline-123", output_paths[0])

    @patch("video_encoder.videos_manager")
    def test_replace_fakesink_with_h265_codec(self, mock_videos_manager):
        """Test replacing fakesink with H265 codec."""
        self.encoder.gst_inspector.elements = [("elem", "vah265enc")]

        mock_video = Mock()
        mock_video.codec = "h265"
        mock_videos_manager.get_video = Mock(return_value=mock_video)

        pipeline_str = "videotestsrc ! fakesink"
        encoder_device = EncoderDeviceConfig(device_name="GPU", gpu_id=0)
        pipeline_id = "test-pipeline-456"

        result, output_paths = self.encoder.replace_fakesink_with_video_output(
            pipeline_id, pipeline_str, encoder_device, ["input.mp4"]
        )

        self.assertIn("vah265enc", result)
        self.assertIn("h265parse", result)

    @patch("video_encoder.videos_manager")
    def test_replace_multiple_fakesinks(self, mock_videos_manager):
        """Test replacing multiple fakesink instances with unique outputs."""
        self.encoder.gst_inspector.elements = [("elem", "vah264enc")]

        mock_video = Mock()
        mock_video.codec = "h264"
        mock_videos_manager.get_video = Mock(return_value=mock_video)

        pipeline_str = (
            "videotestsrc ! tee name=t t. ! queue ! fakesink t. ! queue ! fakesink"
        )
        encoder_device = EncoderDeviceConfig(device_name="GPU", gpu_id=0)
        pipeline_id = "test-pipeline-789"

        result, output_paths = self.encoder.replace_fakesink_with_video_output(
            pipeline_id, pipeline_str, encoder_device, ["input.mp4"]
        )

        # Verify both fakesinks are replaced
        self.assertNotIn("fakesink", result)
        self.assertEqual(result.count("filesink"), 2)

        # Verify unique output paths
        self.assertEqual(len(output_paths), 2)
        self.assertNotEqual(
            output_paths[0], output_paths[1], "Output paths should be unique"
        )
        self.assertIn("pipeline_output_test-pipeline-789", output_paths[0])
        self.assertIn("pipeline_output_test-pipeline-789", output_paths[1])

        # Verify both outputs are in the result
        self.assertIn(f"filesink location={output_paths[0]}", result)
        self.assertIn(f"filesink location={output_paths[1]}", result)

    @patch("video_encoder.videos_manager")
    def test_replace_fakesink_unsupported_codec(self, mock_videos_manager):
        """Test that unsupported codec raises ValueError."""
        encoder_device = EncoderDeviceConfig(device_name="GPU", gpu_id=0)

        mock_video = Mock()
        mock_video.codec = "av1"  # Unsupported codec
        mock_videos_manager.get_video = Mock(return_value=mock_video)

        with self.assertRaises(ValueError) as context:
            self.encoder.replace_fakesink_with_video_output(
                "test-pipeline-999",
                "videotestsrc ! fakesink",
                encoder_device,
                ["input.mp4"],
            )

        self.assertIn("Unsupported codec", str(context.exception))

    @patch("video_encoder.videos_manager")
    def test_replace_fakesink_no_encoder_found(self, mock_videos_manager):
        """Test that no encoder found raises ValueError."""
        self.encoder.gst_inspector.elements = []

        mock_video = Mock()
        mock_video.codec = "h264"
        mock_videos_manager.get_video = Mock(return_value=mock_video)

        encoder_device = EncoderDeviceConfig(device_name="GPU", gpu_id=0)

        with self.assertRaises(ValueError) as context:
            self.encoder.replace_fakesink_with_video_output(
                "test-pipeline-000",
                "videotestsrc ! fakesink",
                encoder_device,
                ["input.mp4"],
            )

        self.assertIn("No suitable encoder found", str(context.exception))


if __name__ == "__main__":
    unittest.main()
