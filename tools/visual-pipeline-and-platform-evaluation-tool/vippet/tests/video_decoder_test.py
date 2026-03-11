import unittest
from unittest.mock import MagicMock, patch

from video_decoder import (
    DECODER_DEVICE_CPU,
    DECODER_DEVICE_GPU,
    FOURCC_TO_CODEC,
    FOURCC_TO_CAPS_PREFIX,
    RAW_FOURCC_CODES,
    VideoDecoder,
)


class TestVideoDecoderSingleton(unittest.TestCase):
    """Test VideoDecoder singleton pattern."""

    def setUp(self):
        VideoDecoder._instance = None

    def tearDown(self):
        VideoDecoder._instance = None

    @patch("video_decoder.GstInspector")
    def test_singleton_returns_same_instance(self, mock_gst_inspector):
        """Test that VideoDecoder returns same instance."""
        d1 = VideoDecoder()
        d2 = VideoDecoder()
        self.assertIs(d1, d2)

    @patch("video_decoder.GstInspector")
    def test_initialization(self, mock_gst_inspector):
        """Test VideoDecoder initializes with decoder configs."""
        decoder = VideoDecoder()
        self.assertIn("h264", decoder.decoder_configs)
        self.assertIn("h265", decoder.decoder_configs)
        self.assertIn("mjpg", decoder.decoder_configs)
        mock_gst_inspector.assert_called_once()


class TestSelectDecoder(unittest.TestCase):
    """Test VideoDecoder.select_decoder() method."""

    def setUp(self):
        VideoDecoder._instance = None

    def tearDown(self):
        VideoDecoder._instance = None

    @patch("video_decoder.GstInspector")
    def test_h264_gpu_selects_vah264dec(self, mock_gst_inspector):
        """Test H264 on GPU selects vah264dec when available."""
        mock_instance = MagicMock()
        mock_instance.elements = [("plugin", "vah264dec", "desc")]
        mock_gst_inspector.return_value = mock_instance

        decoder = VideoDecoder()
        result = decoder.select_decoder("h264", "GPU")
        self.assertEqual(result, "vah264dec")

    @patch("video_decoder.GstInspector")
    def test_h264_gpu_falls_back_to_avdec(self, mock_gst_inspector):
        """Test H264 on GPU falls back to avdec_h264 when VA not available."""
        mock_instance = MagicMock()
        mock_instance.elements = [("plugin", "avdec_h264", "desc")]
        mock_gst_inspector.return_value = mock_instance

        decoder = VideoDecoder()
        result = decoder.select_decoder("h264", "GPU")
        self.assertEqual(result, "avdec_h264")

    @patch("video_decoder.GstInspector")
    def test_h264_cpu_selects_avdec(self, mock_gst_inspector):
        """Test H264 on CPU selects avdec_h264."""
        mock_instance = MagicMock()
        mock_instance.elements = [
            ("plugin", "vah264dec", "desc"),
            ("plugin", "avdec_h264", "desc"),
        ]
        mock_gst_inspector.return_value = mock_instance

        decoder = VideoDecoder()
        result = decoder.select_decoder("h264", "CPU")
        self.assertEqual(result, "avdec_h264")

    @patch("video_decoder.GstInspector")
    def test_h265_gpu_selects_vah265dec(self, mock_gst_inspector):
        """Test H265 on GPU selects vah265dec when available."""
        mock_instance = MagicMock()
        mock_instance.elements = [("plugin", "vah265dec", "desc")]
        mock_gst_inspector.return_value = mock_instance

        decoder = VideoDecoder()
        result = decoder.select_decoder("h265", "GPU")
        self.assertEqual(result, "vah265dec")

    @patch("video_decoder.GstInspector")
    def test_h265_cpu_selects_avdec(self, mock_gst_inspector):
        """Test H265 on CPU selects avdec_h265."""
        mock_instance = MagicMock()
        mock_instance.elements = [("plugin", "avdec_h265", "desc")]
        mock_gst_inspector.return_value = mock_instance

        decoder = VideoDecoder()
        result = decoder.select_decoder("h265", "CPU")
        self.assertEqual(result, "avdec_h265")

    @patch("video_decoder.GstInspector")
    def test_mjpg_gpu_selects_vajpegdec(self, mock_gst_inspector):
        """Test MJPG on GPU selects vajpegdec when available."""
        mock_instance = MagicMock()
        mock_instance.elements = [("plugin", "vajpegdec", "desc")]
        mock_gst_inspector.return_value = mock_instance

        decoder = VideoDecoder()
        result = decoder.select_decoder("MJPG", "GPU")
        self.assertEqual(result, "vajpegdec")

    @patch("video_decoder.GstInspector")
    def test_mjpg_cpu_selects_avdec_mjpeg(self, mock_gst_inspector):
        """Test MJPG on CPU selects avdec_mjpeg."""
        mock_instance = MagicMock()
        mock_instance.elements = [("plugin", "avdec_mjpeg", "desc")]
        mock_gst_inspector.return_value = mock_instance

        decoder = VideoDecoder()
        result = decoder.select_decoder("MJPG", "CPU")
        self.assertEqual(result, "avdec_mjpeg")

    @patch("video_decoder.GstInspector")
    def test_npu_maps_to_gpu(self, mock_gst_inspector):
        """Test NPU device maps to GPU for decoder selection."""
        mock_instance = MagicMock()
        mock_instance.elements = [("plugin", "vah264dec", "desc")]
        mock_gst_inspector.return_value = mock_instance

        decoder = VideoDecoder()
        result = decoder.select_decoder("h264", "NPU")
        self.assertEqual(result, "vah264dec")

    @patch("video_decoder.GstInspector")
    def test_raw_format_returns_none(self, mock_gst_inspector):
        """Test raw format returns None (no decoder needed)."""
        decoder = VideoDecoder()
        result = decoder.select_decoder("YUYV", "GPU")
        self.assertIsNone(result)

    @patch("video_decoder.GstInspector")
    def test_unknown_codec_returns_none(self, mock_gst_inspector):
        """Test unknown codec returns None."""
        decoder = VideoDecoder()
        result = decoder.select_decoder("UNKNOWN_CODEC", "GPU")
        self.assertIsNone(result)

    @patch("video_decoder.GstInspector")
    def test_empty_codec_returns_none(self, mock_gst_inspector):
        """Test empty codec string returns None."""
        decoder = VideoDecoder()
        result = decoder.select_decoder("", "GPU")
        self.assertIsNone(result)

    @patch("video_decoder.GstInspector")
    def test_no_elements_available_returns_none(self, mock_gst_inspector):
        """Test returns None when no decoder elements are available."""
        mock_instance = MagicMock()
        mock_instance.elements = []
        mock_gst_inspector.return_value = mock_instance

        decoder = VideoDecoder()
        result = decoder.select_decoder("h264", "GPU")
        self.assertIsNone(result)

    @patch("video_decoder.GstInspector")
    def test_fourcc_normalization_h264_variants(self, mock_gst_inspector):
        """Test that all H264 fourcc variants normalize correctly."""
        mock_instance = MagicMock()
        mock_instance.elements = [("plugin", "avdec_h264", "desc")]
        mock_gst_inspector.return_value = mock_instance

        decoder = VideoDecoder()
        for fourcc in ["H264", "h264", "H.264", "avc", "avc1"]:
            result = decoder.select_decoder(fourcc, "CPU")
            self.assertEqual(result, "avdec_h264", f"Failed for fourcc: {fourcc}")

    @patch("video_decoder.GstInspector")
    def test_fourcc_normalization_h265_variants(self, mock_gst_inspector):
        """Test that all H265 fourcc variants normalize correctly."""
        mock_instance = MagicMock()
        mock_instance.elements = [("plugin", "avdec_h265", "desc")]
        mock_gst_inspector.return_value = mock_instance

        decoder = VideoDecoder()
        for fourcc in ["H265", "h265", "H.265", "HEVC", "hevc"]:
            result = decoder.select_decoder(fourcc, "CPU")
            self.assertEqual(result, "avdec_h265", f"Failed for fourcc: {fourcc}")

    @patch("video_decoder.GstInspector")
    def test_fourcc_normalization_mjpg_variants(self, mock_gst_inspector):
        """Test that all MJPG fourcc variants normalize correctly."""
        mock_instance = MagicMock()
        mock_instance.elements = [("plugin", "avdec_mjpeg", "desc")]
        mock_gst_inspector.return_value = mock_instance

        decoder = VideoDecoder()
        for fourcc in ["MJPG", "MJPEG", "JPEG", "jpeg"]:
            result = decoder.select_decoder(fourcc, "CPU")
            self.assertEqual(result, "avdec_mjpeg", f"Failed for fourcc: {fourcc}")

    @patch("video_decoder.GstInspector")
    def test_unknown_device_defaults_to_cpu(self, mock_gst_inspector):
        """Test unknown device defaults to CPU decoder selection."""
        mock_instance = MagicMock()
        mock_instance.elements = [("plugin", "avdec_h264", "desc")]
        mock_gst_inspector.return_value = mock_instance

        decoder = VideoDecoder()
        result = decoder.select_decoder("h264", "UNKNOWN_DEVICE")
        self.assertEqual(result, "avdec_h264")


class TestIsRawFormat(unittest.TestCase):
    """Test VideoDecoder.is_raw_format() method."""

    def setUp(self):
        VideoDecoder._instance = None

    def tearDown(self):
        VideoDecoder._instance = None

    @patch("video_decoder.GstInspector")
    def test_raw_formats_detected(self, mock_gst_inspector):
        """Test all known raw formats are detected."""
        decoder = VideoDecoder()
        for fourcc in RAW_FOURCC_CODES:
            self.assertTrue(decoder.is_raw_format(fourcc), f"Expected raw: {fourcc}")

    @patch("video_decoder.GstInspector")
    def test_raw_formats_case_insensitive(self, mock_gst_inspector):
        """Test raw format detection is case insensitive."""
        decoder = VideoDecoder()
        self.assertTrue(decoder.is_raw_format("yuyv"))
        self.assertTrue(decoder.is_raw_format("Nv12"))

    @patch("video_decoder.GstInspector")
    def test_compressed_formats_not_raw(self, mock_gst_inspector):
        """Test compressed formats are not detected as raw."""
        decoder = VideoDecoder()
        self.assertFalse(decoder.is_raw_format("H264"))
        self.assertFalse(decoder.is_raw_format("MJPG"))
        self.assertFalse(decoder.is_raw_format("H265"))

    @patch("video_decoder.GstInspector")
    def test_empty_string_not_raw(self, mock_gst_inspector):
        """Test empty string is not detected as raw."""
        decoder = VideoDecoder()
        self.assertFalse(decoder.is_raw_format(""))


class TestBuildCapsString(unittest.TestCase):
    """Test VideoDecoder.build_caps_string() method."""

    def setUp(self):
        VideoDecoder._instance = None

    def tearDown(self):
        VideoDecoder._instance = None

    @patch("video_decoder.GstInspector")
    def test_mjpg_caps(self, mock_gst_inspector):
        """Test MJPG caps string."""
        decoder = VideoDecoder()
        result = decoder.build_caps_string("MJPG", 1920, 1080, 30.0)
        self.assertEqual(result, "image/jpeg,width=1920,height=1080,framerate=30/1")

    @patch("video_decoder.GstInspector")
    def test_yuyv_caps(self, mock_gst_inspector):
        """Test YUYV caps string includes format."""
        decoder = VideoDecoder()
        result = decoder.build_caps_string("YUYV", 640, 480, 30.0)
        self.assertEqual(
            result, "video/x-raw,format=YUY2,width=640,height=480,framerate=30/1"
        )

    @patch("video_decoder.GstInspector")
    def test_h264_caps(self, mock_gst_inspector):
        """Test H264 caps string."""
        decoder = VideoDecoder()
        result = decoder.build_caps_string("H264", 1920, 1080, 25.0)
        self.assertEqual(result, "video/x-h264,width=1920,height=1080,framerate=25/1")

    @patch("video_decoder.GstInspector")
    def test_nv12_caps(self, mock_gst_inspector):
        """Test NV12 caps string."""
        decoder = VideoDecoder()
        result = decoder.build_caps_string("NV12", 1280, 720, 60.0)
        self.assertEqual(
            result, "video/x-raw,format=NV12,width=1280,height=720,framerate=60/1"
        )

    @patch("video_decoder.GstInspector")
    def test_fps_rounded(self, mock_gst_inspector):
        """Test fps is rounded to integer."""
        decoder = VideoDecoder()
        result = decoder.build_caps_string("MJPG", 640, 480, 29.97)
        self.assertEqual(result, "image/jpeg,width=640,height=480,framerate=30/1")

    @patch("video_decoder.GstInspector")
    def test_unknown_fourcc_returns_none(self, mock_gst_inspector):
        """Test unknown fourcc returns None."""
        decoder = VideoDecoder()
        result = decoder.build_caps_string("UNKNOWN", 640, 480, 30.0)
        self.assertIsNone(result)


class TestSelectElement(unittest.TestCase):
    """Test VideoDecoder.select_element() method."""

    def setUp(self):
        VideoDecoder._instance = None

    def tearDown(self):
        VideoDecoder._instance = None

    @patch("video_decoder.GstInspector")
    def test_select_element_first_match_wins(self, mock_gst_inspector):
        """Test that first matching element wins."""
        mock_instance = MagicMock()
        mock_instance.elements = [
            ("plugin", "vah264dec", "desc"),
            ("plugin", "avdec_h264", "desc"),
        ]
        mock_gst_inspector.return_value = mock_instance

        decoder = VideoDecoder()
        field_dict = {
            DECODER_DEVICE_GPU: [
                ("vah264dec", "vah264dec"),
                ("avdec_h264", "avdec_h264"),
            ],
        }
        result = decoder.select_element(field_dict, DECODER_DEVICE_GPU)
        self.assertEqual(result, "vah264dec")

    @patch("video_decoder.GstInspector")
    def test_select_element_empty_device_returns_none(self, mock_gst_inspector):
        """Test that missing device key returns None."""
        decoder = VideoDecoder()
        field_dict = {
            DECODER_DEVICE_GPU: [("vah264dec", "vah264dec")],
        }
        result = decoder.select_element(field_dict, DECODER_DEVICE_CPU)
        self.assertIsNone(result)


class TestConstants(unittest.TestCase):
    """Test module-level constants."""

    def test_fourcc_to_codec_has_expected_entries(self):
        """Test FOURCC_TO_CODEC has all expected entries."""
        self.assertEqual(FOURCC_TO_CODEC["MJPG"], "mjpg")
        self.assertEqual(FOURCC_TO_CODEC["H264"], "h264")
        self.assertEqual(FOURCC_TO_CODEC["H265"], "h265")
        self.assertEqual(FOURCC_TO_CODEC["HEVC"], "h265")
        self.assertEqual(FOURCC_TO_CODEC["avc1"], "h264")

    def test_raw_fourcc_codes_has_expected_entries(self):
        """Test RAW_FOURCC_CODES has expected entries."""
        self.assertIn("YUYV", RAW_FOURCC_CODES)
        self.assertIn("NV12", RAW_FOURCC_CODES)
        self.assertIn("I420", RAW_FOURCC_CODES)
        self.assertNotIn("H264", RAW_FOURCC_CODES)
        self.assertNotIn("MJPG", RAW_FOURCC_CODES)

    def test_fourcc_to_caps_prefix_has_expected_entries(self):
        """Test FOURCC_TO_CAPS_PREFIX has expected entries."""
        self.assertEqual(FOURCC_TO_CAPS_PREFIX["MJPG"], "image/jpeg")
        self.assertEqual(FOURCC_TO_CAPS_PREFIX["H264"], "video/x-h264")
        self.assertEqual(FOURCC_TO_CAPS_PREFIX["YUYV"], "video/x-raw,format=YUY2")

    def test_no_vaapi_elements_in_decoder_configs(self):
        """Test that no deprecated vaapi elements are used in decoder configs."""
        VideoDecoder._instance = None
        with patch("video_decoder.GstInspector"):
            decoder = VideoDecoder()
            for codec, devices in decoder.decoder_configs.items():
                for device, pairs in devices.items():
                    for search, result in pairs:
                        self.assertNotIn(
                            "vaapi",
                            search.lower(),
                            f"Found deprecated vaapi element '{search}' in {codec}/{device}",
                        )
                        self.assertNotIn(
                            "vaapi",
                            result.lower(),
                            f"Found deprecated vaapi element '{result}' in {codec}/{device}",
                        )
        VideoDecoder._instance = None


if __name__ == "__main__":
    unittest.main()
