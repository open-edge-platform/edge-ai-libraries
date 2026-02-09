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
    def test_replace_fakesink_with_video_output(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test replacing fakesink with video output."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem", "vah264enc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        mock_video = Mock()
        mock_video.codec = "h264"
        mock_videos_manager_instance = MagicMock()
        mock_videos_manager_instance.get_video.return_value = mock_video
        mock_videos_manager.return_value = mock_videos_manager_instance

        encoder = VideoEncoder()

        pipeline_str = "videotestsrc ! fakesink"
        encoder_device = ENCODER_DEVICE_GPU
        pipeline_id = "test-pipeline-123"

        result, output_paths = encoder.replace_fakesink_with_video_output(
            pipeline_id, pipeline_str, encoder_device, ["input.mp4"]
        )

        self.assertIn("vah264enc", result)
        self.assertIn("h264parse", result)
        self.assertIn("mp4mux", result)
        self.assertIn("filesink location=", result)
        self.assertNotIn("fakesink", result)
        self.assertEqual(len(output_paths), 1)
        self.assertIn("pipeline_output_test-pipeline-123", output_paths[0])

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_replace_fakesink_with_h265_codec(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test replacing fakesink with H265 codec."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem", "vah265enc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        mock_video = Mock()
        mock_video.codec = "h265"
        mock_videos_manager_instance = MagicMock()
        mock_videos_manager_instance.get_video.return_value = mock_video
        mock_videos_manager.return_value = mock_videos_manager_instance

        encoder = VideoEncoder()

        pipeline_str = "videotestsrc ! fakesink"
        encoder_device = ENCODER_DEVICE_GPU
        pipeline_id = "test-pipeline-456"

        result, output_paths = encoder.replace_fakesink_with_video_output(
            pipeline_id, pipeline_str, encoder_device, ["input.mp4"]
        )

        self.assertIn("vah265enc", result)
        self.assertIn("h265parse", result)

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_replace_multiple_fakesinks(self, mock_gst_inspector, mock_videos_manager):
        """Test replacing multiple fakesink instances with unique outputs."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem", "vah264enc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        mock_video = Mock()
        mock_video.codec = "h264"
        mock_videos_manager_instance = MagicMock()
        mock_videos_manager_instance.get_video.return_value = mock_video
        mock_videos_manager.return_value = mock_videos_manager_instance

        encoder = VideoEncoder()

        pipeline_str = (
            "videotestsrc ! tee name=t t. ! queue ! fakesink t. ! queue ! fakesink"
        )
        encoder_device = ENCODER_DEVICE_GPU
        pipeline_id = "test-pipeline-789"

        result, output_paths = encoder.replace_fakesink_with_video_output(
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

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_replace_fakesink_unsupported_codec(
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
            encoder.replace_fakesink_with_video_output(
                "test-pipeline-999",
                "videotestsrc ! fakesink",
                encoder_device,
                ["input.mp4"],
            )

        self.assertIn("Unsupported codec", str(context.exception))

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_replace_fakesink_no_encoder_found(
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
            encoder.replace_fakesink_with_video_output(
                "test-pipeline-000",
                "videotestsrc ! fakesink",
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
    def test_replace_fakesink_with_live_stream_output_basic(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test replacing fakesink with live stream output."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem", "x264enc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        mock_video = Mock()
        mock_video.codec = "h264"
        mock_videos_manager_instance = MagicMock()
        mock_videos_manager_instance.get_video.return_value = mock_video
        mock_videos_manager.return_value = mock_videos_manager_instance

        encoder = VideoEncoder()

        pipeline_str = "videotestsrc ! fakesink"
        encoder_device = ENCODER_DEVICE_CPU
        pipeline_id = "test-pipeline-live"

        result, stream_url = encoder.replace_fakesink_with_live_stream_output(
            pipeline_id, pipeline_str, encoder_device, ["input.mp4"]
        )

        # Verify encoder and RTSP sink are in the result
        self.assertIn("x264enc", result)
        self.assertIn("h264parse", result)
        self.assertIn("rtspclientsink", result)
        self.assertIn("protocols=tcp", result)
        self.assertNotIn("fakesink", result)

        # Verify stream URL format
        expected_url = f"rtsp://{LIVE_STREAM_SERVER_HOST}:{LIVE_STREAM_SERVER_PORT}/stream_{pipeline_id}"
        self.assertEqual(stream_url, expected_url)
        self.assertIn(stream_url, result)

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_replace_fakesink_with_live_stream_output_h265(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test live stream output with H265 codec."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem", "x265enc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        mock_video = Mock()
        mock_video.codec = "h265"
        mock_videos_manager_instance = MagicMock()
        mock_videos_manager_instance.get_video.return_value = mock_video
        mock_videos_manager.return_value = mock_videos_manager_instance

        encoder = VideoEncoder()

        pipeline_str = "videotestsrc ! fakesink"
        encoder_device = ENCODER_DEVICE_CPU
        pipeline_id = "test-pipeline-h265"

        result, stream_url = encoder.replace_fakesink_with_live_stream_output(
            pipeline_id, pipeline_str, encoder_device, ["input.mp4"]
        )

        self.assertIn("x265enc", result)
        self.assertIn("h265parse", result)
        self.assertIn("rtspclientsink", result)

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_replace_fakesink_with_live_stream_output_gpu(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test live stream output with GPU encoder."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem", "vah264lpenc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        mock_video = Mock()
        mock_video.codec = "h264"
        mock_videos_manager_instance = MagicMock()
        mock_videos_manager_instance.get_video.return_value = mock_video
        mock_videos_manager.return_value = mock_videos_manager_instance

        encoder = VideoEncoder()

        pipeline_str = "videotestsrc ! fakesink"
        encoder_device = ENCODER_DEVICE_GPU
        pipeline_id = "test-pipeline-gpu"

        result, stream_url = encoder.replace_fakesink_with_live_stream_output(
            pipeline_id, pipeline_str, encoder_device, ["input.mp4"]
        )

        self.assertIn("vah264lpenc", result)
        self.assertIn("rtspclientsink", result)

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_replace_fakesink_with_live_stream_no_fakesink(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test that ValueError is raised when no fakesink is found."""
        encoder = VideoEncoder()

        pipeline_str = "videotestsrc ! autovideosink"
        encoder_device = ENCODER_DEVICE_CPU
        pipeline_id = "test-pipeline-no-fakesink"

        with self.assertRaises(ValueError) as context:
            encoder.replace_fakesink_with_live_stream_output(
                pipeline_id, pipeline_str, encoder_device, ["input.mp4"]
            )

        self.assertIn("No fakesink found", str(context.exception))

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_replace_fakesink_with_live_stream_replaces_only_first(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test that only the first fakesink is replaced for live streaming."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem", "x264enc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        mock_video = Mock()
        mock_video.codec = "h264"
        mock_videos_manager_instance = MagicMock()
        mock_videos_manager_instance.get_video.return_value = mock_video
        mock_videos_manager.return_value = mock_videos_manager_instance

        encoder = VideoEncoder()

        pipeline_str = (
            "videotestsrc ! tee name=t t. ! queue ! fakesink t. ! queue ! fakesink"
        )
        encoder_device = ENCODER_DEVICE_CPU
        pipeline_id = "test-pipeline-multi"

        result, stream_url = encoder.replace_fakesink_with_live_stream_output(
            pipeline_id, pipeline_str, encoder_device, ["input.mp4"]
        )

        # Only one fakesink should be replaced
        self.assertEqual(result.count("rtspclientsink"), 1)
        self.assertEqual(result.count("fakesink"), 1)

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_replace_fakesink_with_live_stream_needs_looping_flag(
        self, mock_gst_inspector, mock_videos_manager
    ):
        """Test that needs_looping flag is accepted."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem", "x264enc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        mock_video = Mock()
        mock_video.codec = "h264"
        mock_videos_manager_instance = MagicMock()
        mock_videos_manager_instance.get_video.return_value = mock_video
        mock_videos_manager.return_value = mock_videos_manager_instance

        encoder = VideoEncoder()

        pipeline_str = "videotestsrc ! fakesink"
        encoder_device = ENCODER_DEVICE_CPU
        pipeline_id = "test-pipeline-loop"

        # Test with needs_looping=True
        result, stream_url = encoder.replace_fakesink_with_live_stream_output(
            pipeline_id,
            pipeline_str,
            encoder_device,
            ["input.mp4"],
            needs_looping=True,
        )

        self.assertIn("x264enc", result)
        self.assertIn("rtspclientsink", result)

    @patch("video_encoder.VideosManager")
    @patch("video_encoder.GstInspector")
    def test_replace_fakesink_with_live_stream_no_encoder_found(
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

        pipeline_str = "videotestsrc ! fakesink"
        encoder_device = ENCODER_DEVICE_GPU
        pipeline_id = "test-pipeline-no-enc"

        with self.assertRaises(ValueError) as context:
            encoder.replace_fakesink_with_live_stream_output(
                pipeline_id, pipeline_str, encoder_device, ["input.mp4"]
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
