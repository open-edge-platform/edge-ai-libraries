import unittest
from unittest.mock import patch, MagicMock

from video_encoder import (
    ENCODER_DEVICE_CPU,
    ENCODER_DEVICE_GPU,
    ENCODER_CONFIG,
    STREAMING_ENCODER_CONFIG,
    LIVE_STREAM_SERVER_HOST,
    LIVE_STREAM_SERVER_PORT,
    VideoEncoder,
)


class TestVideoEncoderClass(unittest.TestCase):
    """Test cases for VideoEncoder class."""

    def setUp(self):
        """Set up test fixtures and reset singleton."""
        VideoEncoder._instance = None
        self.output_dir = "/tmp/test-output-dir"
        self.job_id = "test-job-123"

    def tearDown(self):
        """Reset singleton after each test."""
        VideoEncoder._instance = None

    @patch("video_encoder.GstInspector")
    def test_initialization(self, mock_gst_inspector):
        """Test VideoEncoder initialization."""
        encoder = VideoEncoder()
        self.assertIsNotNone(encoder.gst_inspector)
        mock_gst_inspector.assert_called_once()

    @patch("video_encoder.GstInspector")
    def test_singleton_returns_same_instance(self, mock_gst_inspector):
        """Test that VideoEncoder returns same instance (singleton)."""
        encoder1 = VideoEncoder()
        encoder2 = VideoEncoder()
        self.assertIs(encoder1, encoder2)

    def test_encoder_config_has_cpu_and_gpu(self):
        """Test that ENCODER_CONFIG has entries for CPU and GPU."""
        self.assertIn(ENCODER_DEVICE_GPU, ENCODER_CONFIG)
        self.assertIn(ENCODER_DEVICE_CPU, ENCODER_CONFIG)

    def test_streaming_encoder_config_has_cpu_and_gpu(self):
        """Test that STREAMING_ENCODER_CONFIG has entries for CPU and GPU."""
        self.assertIn(ENCODER_DEVICE_GPU, STREAMING_ENCODER_CONFIG)
        self.assertIn(ENCODER_DEVICE_CPU, STREAMING_ENCODER_CONFIG)

    @patch("video_encoder.GstInspector")
    def test_select_element_gpu(self, mock_gst_inspector):
        """Test selecting encoder for GPU."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem1", "vah264enc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        encoder = VideoEncoder()

        result = encoder._select_element(ENCODER_DEVICE_GPU)
        self.assertEqual(result, "vah264enc")

    @patch("video_encoder.GstInspector")
    def test_select_element_cpu(self, mock_gst_inspector):
        """Test selecting encoder for CPU."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem1", "openh264enc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        encoder = VideoEncoder()

        result = encoder._select_element(ENCODER_DEVICE_CPU)
        assert result is not None  # Type narrowing for static analysis
        self.assertIn("openh264enc", result)

    @patch("video_encoder.GstInspector")
    def test_select_element_streaming(self, mock_gst_inspector):
        """Test selecting streaming encoder."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem1", "openh264enc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        encoder = VideoEncoder()

        result = encoder._select_element(ENCODER_DEVICE_CPU, streaming=True)
        assert result is not None  # Type narrowing for static analysis
        self.assertIn("openh264enc", result)
        # Streaming config should include low-latency settings
        self.assertIn("usage-type=camera", result)

    @patch("video_encoder.GstInspector")
    def test_select_element_invalid_device_raises(self, mock_gst_inspector):
        """Test that invalid encoder_device raises ValueError."""
        encoder = VideoEncoder()

        with self.assertRaises(ValueError) as context:
            encoder._select_element("INVALID")
        self.assertIn("Invalid encoder_device", str(context.exception))

    @patch("video_encoder.GstInspector")
    def test_select_element_no_match_returns_none(self, mock_gst_inspector):
        """Test that None is returned when no encoder matches."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = []  # No elements available
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        encoder = VideoEncoder()

        result = encoder._select_element(ENCODER_DEVICE_GPU)
        self.assertIsNone(result)

    @patch("video_encoder.GstInspector")
    def test_create_video_output_subpipeline(self, mock_gst_inspector):
        """Test creating video output subpipeline."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem", "vah264enc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        encoder = VideoEncoder()

        encoder_device = ENCODER_DEVICE_GPU

        subpipeline = encoder.create_video_output_subpipeline(
            self.output_dir, encoder_device
        )

        self.assertIn("vah264enc", subpipeline)
        self.assertIn("h264parse", subpipeline)
        self.assertIn("mp4mux", subpipeline)
        self.assertIn("filesink location=", subpipeline)
        self.assertIn("main_output.mp4", subpipeline)
        self.assertIn(self.output_dir, subpipeline)

    @patch("video_encoder.GstInspector")
    def test_create_video_output_subpipeline_cpu_encoder(self, mock_gst_inspector):
        """Test creating video output subpipeline with CPU encoder."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem", "openh264enc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        encoder = VideoEncoder()

        encoder_device = ENCODER_DEVICE_CPU

        subpipeline = encoder.create_video_output_subpipeline(
            self.output_dir, encoder_device
        )

        # Verify CPU encoder is used
        self.assertIn("openh264enc", subpipeline)
        self.assertIn("h264parse", subpipeline)
        self.assertIn("mp4mux", subpipeline)
        self.assertIn("filesink location=", subpipeline)
        self.assertIn("main_output.mp4", subpipeline)
        self.assertIn(self.output_dir, subpipeline)

    @patch("video_encoder.GstInspector")
    def test_create_video_output_subpipeline_no_encoder_found(self, mock_gst_inspector):
        """Test that no encoder found raises ValueError."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = []
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        encoder = VideoEncoder()
        encoder_device = ENCODER_DEVICE_GPU

        with self.assertRaises(ValueError) as context:
            encoder.create_video_output_subpipeline(self.output_dir, encoder_device)

        self.assertIn("No suitable encoder found", str(context.exception))


class TestLiveStreamOutput(unittest.TestCase):
    """Test cases for live stream output functionality."""

    def setUp(self):
        """Set up test fixtures and reset singleton."""
        VideoEncoder._instance = None
        self.job_id = "test-job-456"

    def tearDown(self):
        """Reset singleton after each test."""
        VideoEncoder._instance = None

    @patch("video_encoder.GstInspector")
    def test_create_live_stream_output_subpipeline_basic(self, mock_gst_inspector):
        """Test creating live stream output subpipeline."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem", "openh264enc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        encoder = VideoEncoder()

        encoder_device = ENCODER_DEVICE_CPU
        pipeline_id = "test-pipeline-live"

        subpipeline, stream_url = encoder.create_live_stream_output_subpipeline(
            pipeline_id, encoder_device, self.job_id
        )

        # Verify encoder and RTSP sink are in the subpipeline
        self.assertIn("openh264enc", subpipeline)
        self.assertIn("h264parse", subpipeline)
        self.assertIn("rtspclientsink", subpipeline)
        self.assertIn("protocols=tcp", subpipeline)

        # Verify stream URL format includes both pipeline_id and job_id
        expected_url = f"rtsp://{LIVE_STREAM_SERVER_HOST}:{LIVE_STREAM_SERVER_PORT}/stream-{pipeline_id}-{self.job_id}"
        self.assertEqual(stream_url, expected_url)
        self.assertIn(stream_url, subpipeline)

    @patch("video_encoder.GstInspector")
    def test_create_live_stream_output_subpipeline_gpu(self, mock_gst_inspector):
        """Test live stream output subpipeline with GPU encoder."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = [("elem", "vah264lpenc")]
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        encoder = VideoEncoder()

        encoder_device = ENCODER_DEVICE_GPU
        pipeline_id = "test-pipeline-gpu"

        subpipeline, stream_url = encoder.create_live_stream_output_subpipeline(
            pipeline_id, encoder_device, self.job_id
        )

        self.assertIn("vah264lpenc", subpipeline)
        self.assertIn("rtspclientsink", subpipeline)

    @patch("video_encoder.GstInspector")
    def test_create_live_stream_output_subpipeline_no_encoder_found(
        self, mock_gst_inspector
    ):
        """Test that ValueError is raised when no encoder is found."""
        mock_gst_inspector_instance = MagicMock()
        mock_gst_inspector_instance.elements = []  # No encoders available
        mock_gst_inspector.return_value = mock_gst_inspector_instance

        encoder = VideoEncoder()

        encoder_device = ENCODER_DEVICE_GPU
        pipeline_id = "test-pipeline-no-enc"

        with self.assertRaises(ValueError) as context:
            encoder.create_live_stream_output_subpipeline(
                pipeline_id, encoder_device, self.job_id
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

    @patch("video_encoder.GstInspector")
    def test_fakesink_pattern_matches_standalone(self, mock_gst_inspector):
        """Test that pattern matches standalone fakesink."""
        encoder = VideoEncoder()
        pipeline_str = "videotestsrc ! fakesink"
        matches = encoder.re_pattern.findall(pipeline_str)
        self.assertEqual(len(matches), 1)

    @patch("video_encoder.GstInspector")
    def test_fakesink_pattern_matches_multiple(self, mock_gst_inspector):
        """Test that pattern matches multiple fakesinks."""
        encoder = VideoEncoder()
        pipeline_str = "videotestsrc ! fakesink ! fakesink"
        matches = encoder.re_pattern.findall(pipeline_str)
        self.assertEqual(len(matches), 2)

    @patch("video_encoder.GstInspector")
    def test_fakesink_pattern_ignores_embedded(self, mock_gst_inspector):
        """Test that pattern ignores fakesink embedded in properties."""
        encoder = VideoEncoder()
        pipeline_str = "playbin video-sink=fakesink"
        matches = encoder.re_pattern.findall(pipeline_str)
        self.assertEqual(len(matches), 0)

    @patch("video_encoder.GstInspector")
    def test_fakesink_pattern_matches_with_properties(self, mock_gst_inspector):
        """Test that pattern matches fakesink with properties."""
        encoder = VideoEncoder()
        pipeline_str = "videotestsrc ! fakesink sync=false"
        matches = encoder.re_pattern.findall(pipeline_str)
        self.assertEqual(len(matches), 1)

    @patch("video_encoder.GstInspector")
    def test_fakesink_pattern_at_start(self, mock_gst_inspector):
        """Test that pattern matches fakesink at start of string."""
        encoder = VideoEncoder()
        pipeline_str = "fakesink"
        matches = encoder.re_pattern.findall(pipeline_str)
        self.assertEqual(len(matches), 1)


if __name__ == "__main__":
    unittest.main()
