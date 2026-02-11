import unittest
from unittest.mock import Mock, patch, MagicMock

from video_encoder import (
    ENCODER_DEVICE_CPU,
    ENCODER_DEVICE_GPU,
    LIVE_STREAM_SERVER_HOST,
    LIVE_STREAM_SERVER_PORT,
    VideoEncoder,
)


class TestVideoEncoderClass(unittest.TestCase):
    """Test cases for VideoEncoder class."""

    def setUp(self):
        """Set up test fixtures and reset singleton."""
        VideoEncoder._instance = None

    def tearDown(self):
        """Reset singleton after each test."""
        VideoEncoder._instance = None

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_initialization(self, mock_gst_inspector, mock_videos_manager):
        """Test VideoEncoder initialization."""
        encoder = VideoEncoder()
        self.assertIsNotNone(encoder.gst_inspector)
        self.assertIsNotNone(encoder.videos_manager)
        self.assertIn("h264", encoder.encoder_configs)
        self.assertIn("h264", encoder.streaming_encoder_configs)
        mock_gst_inspector.assert_called_once()
        mock_videos_manager.assert_called_once()

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_singleton_returns_same_instance(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test that VideoEncoder returns same instance (singleton)."""
        encoder1 = VideoEncoder()
        encoder2 = VideoEncoder()
        self.assertIs(encoder1, encoder2)

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_streaming_encoder_configs_exist(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test that streaming encoder configs are defined for h264 and h265."""
        encoder = VideoEncoder()
        self.assertIn("h264", encoder.streaming_encoder_configs)
        self.assertIn("h265", encoder.streaming_encoder_configs)
        self.assertIn(ENCODER_DEVICE_GPU, encoder.streaming_encoder_configs["h264"])
        self.assertIn(ENCODER_DEVICE_CPU, encoder.streaming_encoder_configs["h264"])

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_select_element_gpu_0(self, mock_gst_inspector, mock_videos_manager):
        """Test selecting encoder for GPU 0."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem1", "vah264enc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        encoder = VideoEncoder()

        encoder_device = ENCODER_DEVICE_GPU
        encoder_dict = {
            ENCODER_DEVICE_GPU: [("vah264enc", "vah264enc")],
            ENCODER_DEVICE_CPU: [("x264enc", "x264enc")],
        }

        result = encoder.select_element(encoder_dict, encoder_device)
        self.assertEqual(result, "vah264enc")

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_detect_codec_from_input(self, mock_gst_inspector, mock_videos_manager):
        """Test codec detection from input videos."""
        mock_video = Mock()
        mock_video.codec = "h265"
        mock_videos_manager_instance = MagicMock()
        mock_videos_manager_instance.get_video.return_value = mock_video
        mock_videos_manager.return_value = mock_videos_manager_instance

        encoder = VideoEncoder()
        codec = encoder._detect_codec_from_input(["video1.mp4"])
        self.assertEqual(codec, "h265")

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_detect_codec_from_input_defaults_to_h264(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test codec detection defaults to h264 when video not found."""
        mock_videos_manager_instance = MagicMock()
        mock_videos_manager_instance.get_video.return_value = None
        mock_videos_manager.return_value = mock_videos_manager_instance

        encoder = VideoEncoder()
        codec = encoder._detect_codec_from_input(["video1.mp4"])
        self.assertEqual(codec, "h264")

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_detect_codec_empty_list(self, mock_gst_inspector, mock_videos_manager):
        """Test codec detection with empty list."""
        encoder = VideoEncoder()
        codec = encoder._detect_codec_from_input([])
        self.assertEqual(codec, "h264")

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_validate_codec_valid(self, mock_gst_inspector, mock_videos_manager):
        """Test codec validation with valid codec."""
        encoder = VideoEncoder()
        # Should not raise
        encoder._validate_codec("h264")
        encoder._validate_codec("h265")

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_validate_codec_invalid(self, mock_gst_inspector, mock_videos_manager):
        """Test codec validation with invalid codec."""
        encoder = VideoEncoder()
        with self.assertRaises(ValueError) as context:
            encoder._validate_codec("av1")
        self.assertIn("Unsupported codec", str(context.exception))
        self.assertIn("av1", str(context.exception))

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_create_video_output_subpipeline(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test creating video output subpipeline."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem", "vah264enc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        mock_video = Mock()
        mock_video.codec = "h264"
        mock_videos_manager_instance = MagicMock()
        mock_videos_manager_instance.get_video.return_value = mock_video
        mock_videos_manager.return_value = mock_videos_manager_instance

        encoder = VideoEncoder()

        encoder_device = ENCODER_DEVICE_GPU
        pipeline_id = "test-pipeline-123"

        subpipeline, output_path = encoder.create_video_output_subpipeline(
            pipeline_id, encoder_device, ["input.mp4"]
        )

        self.assertIn("vah264enc", subpipeline)
        self.assertIn("h264parse", subpipeline)
        self.assertIn("mp4mux", subpipeline)
        self.assertIn("filesink location=", subpipeline)
        self.assertIn("pipeline_output_test-pipeline-123", output_path)

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_create_video_output_subpipeline_h265_codec(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test creating video output subpipeline with H265 codec."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem", "vah265enc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        mock_video = Mock()
        mock_video.codec = "h265"
        mock_videos_manager_instance = MagicMock()
        mock_videos_manager_instance.get_video.return_value = mock_video
        mock_videos_manager.return_value = mock_videos_manager_instance

        encoder = VideoEncoder()

        encoder_device = ENCODER_DEVICE_GPU
        pipeline_id = "test-pipeline-456"

        subpipeline, output_path = encoder.create_video_output_subpipeline(
            pipeline_id, encoder_device, ["input.mp4"]
        )

        self.assertIn("vah265enc", subpipeline)
        self.assertIn("h265parse", subpipeline)

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_create_video_output_subpipeline_cpu_encoder(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test creating video output subpipeline with CPU encoder."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem", "x264enc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        mock_video = Mock()
        mock_video.codec = "h264"
        mock_videos_manager_instance = MagicMock()
        mock_videos_manager_instance.get_video.return_value = mock_video
        mock_videos_manager.return_value = mock_videos_manager_instance

        encoder = VideoEncoder()

        encoder_device = ENCODER_DEVICE_CPU
        pipeline_id = "test-pipeline-789"

        subpipeline, output_path = encoder.create_video_output_subpipeline(
            pipeline_id, encoder_device, ["input.mp4"]
        )

        # Verify CPU encoder is used
        self.assertIn("x264enc", subpipeline)
        self.assertIn("h264parse", subpipeline)
        self.assertIn("mp4mux", subpipeline)
        self.assertIn("filesink location=", subpipeline)
        self.assertIn("pipeline_output_test-pipeline-789", output_path)

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_create_video_output_subpipeline_unsupported_codec(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test that unsupported codec raises ValueError."""
        mock_video = Mock()
        mock_video.codec = "av1"  # Unsupported codec
        mock_videos_manager_instance = MagicMock()
        mock_videos_manager_instance.get_video.return_value = mock_video
        mock_videos_manager.return_value = mock_videos_manager_instance

        encoder = VideoEncoder()
        encoder_device = ENCODER_DEVICE_GPU

        with self.assertRaises(ValueError) as context:
            encoder.create_video_output_subpipeline(
                "test-pipeline-999",
                encoder_device,
                ["input.mp4"],
            )

        self.assertIn("Unsupported codec", str(context.exception))

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_create_video_output_subpipeline_no_encoder_found(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test that no encoder found raises ValueError."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = []
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        mock_video = Mock()
        mock_video.codec = "h264"
        mock_videos_manager_instance = MagicMock()
        mock_videos_manager_instance.get_video.return_value = mock_video
        mock_videos_manager.return_value = mock_videos_manager_instance

        encoder = VideoEncoder()
        encoder_device = ENCODER_DEVICE_GPU

        with self.assertRaises(ValueError) as context:
            encoder.create_video_output_subpipeline(
                "test-pipeline-000",
                encoder_device,
                ["input.mp4"],
            )

        self.assertIn("No suitable encoder found", str(context.exception))


class TestLiveStreamOutput(unittest.TestCase):
    """Test cases for live stream output functionality."""

    def setUp(self):
        """Set up test fixtures and reset singleton."""
        VideoEncoder._instance = None

    def tearDown(self):
        """Reset singleton after each test."""
        VideoEncoder._instance = None

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_create_live_stream_output_subpipeline_basic(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test creating live stream output subpipeline."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem", "x264enc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        mock_video = Mock()
        mock_video.codec = "h264"
        mock_videos_manager_instance = MagicMock()
        mock_videos_manager_instance.get_video.return_value = mock_video
        mock_videos_manager.return_value = mock_videos_manager_instance

        encoder = VideoEncoder()

        encoder_device = ENCODER_DEVICE_CPU
        pipeline_id = "test-pipeline-live"

        subpipeline, stream_url = encoder.create_live_stream_output_subpipeline(
            pipeline_id, encoder_device, ["input.mp4"]
        )

        # Verify encoder and RTSP sink are in the subpipeline
        self.assertIn("x264enc", subpipeline)
        self.assertIn("h264parse", subpipeline)
        self.assertIn("rtspclientsink", subpipeline)
        self.assertIn("protocols=tcp", subpipeline)

        # Verify stream URL format
        expected_url = f"rtsp://{LIVE_STREAM_SERVER_HOST}:{LIVE_STREAM_SERVER_PORT}/stream_{pipeline_id}"
        self.assertEqual(stream_url, expected_url)
        self.assertIn(stream_url, subpipeline)

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_create_live_stream_output_subpipeline_h265(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test live stream output subpipeline with H265 codec."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem", "x265enc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        mock_video = Mock()
        mock_video.codec = "h265"
        mock_videos_manager_instance = MagicMock()
        mock_videos_manager_instance.get_video.return_value = mock_video
        mock_videos_manager.return_value = mock_videos_manager_instance

        encoder = VideoEncoder()

        encoder_device = ENCODER_DEVICE_CPU
        pipeline_id = "test-pipeline-h265"

        subpipeline, stream_url = encoder.create_live_stream_output_subpipeline(
            pipeline_id, encoder_device, ["input.mp4"]
        )

        self.assertIn("x265enc", subpipeline)
        self.assertIn("h265parse", subpipeline)
        self.assertIn("rtspclientsink", subpipeline)

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_create_live_stream_output_subpipeline_gpu(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test live stream output subpipeline with GPU encoder."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem", "vah264lpenc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        mock_video = Mock()
        mock_video.codec = "h264"
        mock_videos_manager_instance = MagicMock()
        mock_videos_manager_instance.get_video.return_value = mock_video
        mock_videos_manager.return_value = mock_videos_manager_instance

        encoder = VideoEncoder()

        encoder_device = ENCODER_DEVICE_GPU
        pipeline_id = "test-pipeline-gpu"

        subpipeline, stream_url = encoder.create_live_stream_output_subpipeline(
            pipeline_id, encoder_device, ["input.mp4"]
        )

        self.assertIn("vah264lpenc", subpipeline)
        self.assertIn("rtspclientsink", subpipeline)

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_create_live_stream_output_subpipeline_no_encoder_found(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test that ValueError is raised when no encoder is found."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = []  # No encoders available
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        mock_video = Mock()
        mock_video.codec = "h264"
        mock_videos_manager_instance = MagicMock()
        mock_videos_manager_instance.get_video.return_value = mock_video
        mock_videos_manager.return_value = mock_videos_manager_instance

        encoder = VideoEncoder()

        encoder_device = ENCODER_DEVICE_GPU
        pipeline_id = "test-pipeline-no-enc"

        with self.assertRaises(ValueError) as context:
            encoder.create_live_stream_output_subpipeline(
                pipeline_id, encoder_device, ["input.mp4"]
            )

        self.assertIn("No suitable encoder found", str(context.exception))


class TestFakesinkPattern(unittest.TestCase):
    """Test cases for fakesink regex pattern matching."""

    def setUp(self):
        """Set up test fixtures and reset singleton."""
        VideoEncoder._instance = None

    def tearDown(self):
        """Reset singleton after each test."""
        VideoEncoder._instance = None

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_fakesink_pattern_matches_standalone(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test that pattern matches standalone fakesink."""
        encoder = VideoEncoder()
        pipeline_str = "videotestsrc ! fakesink"
        matches = encoder.re_pattern.findall(pipeline_str)
        self.assertEqual(len(matches), 1)

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_fakesink_pattern_matches_multiple(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test that pattern matches multiple fakesinks."""
        encoder = VideoEncoder()
        pipeline_str = "videotestsrc ! fakesink ! fakesink"
        matches = encoder.re_pattern.findall(pipeline_str)
        self.assertEqual(len(matches), 2)

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_fakesink_pattern_ignores_embedded(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test that pattern ignores fakesink embedded in properties."""
        encoder = VideoEncoder()
        pipeline_str = "playbin video-sink=fakesink"
        matches = encoder.re_pattern.findall(pipeline_str)
        self.assertEqual(len(matches), 0)

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_fakesink_pattern_matches_with_properties(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test that pattern matches fakesink with properties."""
        encoder = VideoEncoder()
        pipeline_str = "videotestsrc ! fakesink sync=false"
        matches = encoder.re_pattern.findall(pipeline_str)
        self.assertEqual(len(matches), 1)

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_fakesink_pattern_at_start(self, mock_gst_inspector, mock_videos_manager):
        """Test that pattern matches fakesink at start of string."""
        encoder = VideoEncoder()
        pipeline_str = "fakesink"
        matches = encoder.re_pattern.findall(pipeline_str)
        self.assertEqual(len(matches), 1)


if __name__ == "__main__":
    unittest.main()
