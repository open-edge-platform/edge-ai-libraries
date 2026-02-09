import re
import unittest

import utils


class TestUtils(unittest.TestCase):
    def test_generate_unique_id_format(self):
        # Test that the generated ID follows the expected format: prefix-hash
        prefix = "test"
        unique_id = utils.generate_unique_id(prefix)

        # Should start with the prefix
        self.assertTrue(unique_id.startswith(f"{prefix}-"))

        # Should have exactly 8 hexadecimal characters after the prefix and dash
        pattern = rf"^{re.escape(prefix)}-[0-9a-f]{{8}}$"
        self.assertIsNotNone(re.match(pattern, unique_id))

    def test_generate_unique_id_uniqueness(self):
        # Test that multiple calls generate different IDs
        prefix = "pipeline"
        ids = [utils.generate_unique_id(prefix) for _ in range(100)]

        # All IDs should be unique
        self.assertEqual(len(ids), len(set(ids)))

    def test_generate_unique_id_different_prefixes(self):
        # Test that different prefixes produce different IDs
        id1 = utils.generate_unique_id("prefix1")
        id2 = utils.generate_unique_id("prefix2")

        self.assertTrue(id1.startswith("prefix1-"))
        self.assertTrue(id2.startswith("prefix2-"))
        self.assertNotEqual(id1, id2)

    def test_generate_unique_id_empty_prefix(self):
        # Test with an empty prefix
        unique_id = utils.generate_unique_id("")

        # Should start with a dash and have 8 hex characters
        pattern = r"^-[0-9a-f]{8}$"
        self.assertIsNotNone(re.match(pattern, unique_id))

    def test_generate_unique_id_special_chars_prefix(self):
        # Test with special characters in prefix
        prefix = "test_prefix-123"
        unique_id = utils.generate_unique_id(prefix)

        self.assertTrue(unique_id.startswith(f"{prefix}-"))
        pattern = rf"^{re.escape(prefix)}-[0-9a-f]{{8}}$"
        self.assertIsNotNone(re.match(pattern, unique_id))

    def test_generate_unique_id_rapid_succession(self):
        # Test that IDs generated in rapid succession are still unique
        prefix = "rapid"
        ids = []
        for _ in range(10):
            ids.append(utils.generate_unique_id(prefix))
            # No sleep to test rapid generation

        # All should be unique despite being generated rapidly
        self.assertEqual(len(ids), len(set(ids)))

    def test_yolov10_model(self):
        # Test with a valid YOLO v10 model path
        self.assertTrue(utils.is_yolov10_model("/path/to/yolov10s_model.xml"))

    def test_non_yolov10_model(self):
        # Test with a non-YOLO v10 model path
        self.assertFalse(utils.is_yolov10_model("/path/to/other_model.xml"))

    def test_case_insensitivity(self):
        # Test with mixed-case YOLO v10 model path
        self.assertTrue(utils.is_yolov10_model("/path/to/YOLOv10m_model.xml"))

    def test_empty_path(self):
        # Test with an empty string
        self.assertFalse(utils.is_yolov10_model(""))

    def test_no_yolo_in_path(self):
        # Test with a path that does not contain "yolov10"
        self.assertFalse(utils.is_yolov10_model("/path/to/yolo_model.xml"))

    def test_make_tee_names_unique_single_tee(self):
        # Test with single tee element
        pipeline = "videotestsrc ! tee name=t0 ! queue t0. ! fakesink"
        result = utils.make_tee_names_unique(pipeline, 1, 0)

        # Should replace t0 with t1000
        self.assertIn("tee name=t1000", result)
        self.assertIn("t1000.", result)
        self.assertNotIn("t0.", result)

    def test_make_tee_names_unique_multiple_tees(self):
        # Test with multiple tee elements
        pipeline = "src ! tee name=t0 t0. ! queue ! sink1 t0. ! tee name=t1 t1. ! sink2"
        result = utils.make_tee_names_unique(pipeline, 2, 1)

        # Should replace both tees uniquely
        self.assertIn("tee name=t2100", result)  # t0 -> t2100
        self.assertIn("tee name=t2111", result)  # t1 -> t2111
        self.assertNotIn("name=t0", result)
        self.assertNotIn("name=t1", result)

    def test_make_tee_names_unique_no_tees(self):
        # Test with pipeline without tees
        pipeline = "videotestsrc ! queue ! fakesink"
        result = utils.make_tee_names_unique(pipeline, 0, 0)

        # Should return unchanged
        self.assertEqual(pipeline, result)

    def test_make_tee_names_unique_tee_references(self):
        # Test that all tee references are updated
        pipeline = "tee name=t0 t0. ! queue1 t0. ! queue2 t0. ! queue3"
        result = utils.make_tee_names_unique(pipeline, 0, 0)

        # All references should be updated
        self.assertEqual(result.count("t0000."), 3)
        self.assertNotIn("t0.", result)

    def test_make_tee_names_unique_different_indices(self):
        # Test with different pipeline and stream indices
        pipeline = "tee name=t5 "
        result1 = utils.make_tee_names_unique(pipeline, 1, 2)
        result2 = utils.make_tee_names_unique(pipeline, 3, 4)

        # Results should be different based on indices
        self.assertIn("t1205", result1)
        self.assertIn("t3405", result2)
        self.assertNotEqual(result1, result2)

    def test_generate_unique_filename_basic(self):
        # Test basic filename generation with extension
        filename = "video.mp4"
        result = utils.generate_unique_filename(filename)

        # Should start with "video_"
        self.assertTrue(result.startswith("video_"))

        # Should end with ".mp4"
        self.assertTrue(result.endswith(".mp4"))

        # Should match pattern: stem_YYYYMMDD_HHMMSS_<6hex>.mp4
        pattern = r"^video_\d{8}_\d{6}_[0-9a-f]{6}\.mp4$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_unique_filename_no_extension(self):
        # Test filename generation without extension (should default to .mp4)
        filename = "video"
        result = utils.generate_unique_filename(filename)

        # Should end with default ".mp4" extension
        self.assertTrue(result.endswith(".mp4"))

        # Should match pattern with default extension
        pattern = r"^video_\d{8}_\d{6}_[0-9a-f]{6}\.mp4$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_unique_filename_uniqueness(self):
        # Test that multiple calls generate unique filenames
        filename = "test.mp4"
        filenames = [utils.generate_unique_filename(filename) for _ in range(100)]

        # All filenames should be unique
        self.assertEqual(len(filenames), len(set(filenames)))

    def test_generate_unique_filename_with_path(self):
        # Test with a full path (should only use the filename part)
        filename = "/path/to/video.mp4"
        result = utils.generate_unique_filename(filename)

        # Should not include path separators
        self.assertNotIn("/", result)

        # Should start with "video_"
        self.assertTrue(result.startswith("video_"))

        # Should end with ".mp4"
        self.assertTrue(result.endswith(".mp4"))

    def test_generate_unique_filename_complex_name(self):
        # Test with complex filename containing underscores and numbers
        filename = "test_video_123.mp4"
        result = utils.generate_unique_filename(filename)

        # Should start with the original stem
        self.assertTrue(result.startswith("test_video_123_"))

        # Should match pattern
        pattern = r"^test_video_123_\d{8}_\d{6}_[0-9a-f]{6}\.mp4$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_unique_filename_special_characters(self):
        # Test with special characters in filename
        filename = "test-video.mp4"
        result = utils.generate_unique_filename(filename)

        # Should preserve special characters in stem
        self.assertTrue(result.startswith("test-video_"))

        # Should match pattern
        pattern = r"^test-video_\d{8}_\d{6}_[0-9a-f]{6}\.mp4$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_unique_filename_empty_string(self):
        # Test with empty string (edge case)
        filename = ""
        result = utils.generate_unique_filename(filename)

        # Should generate with default extension
        self.assertTrue(result.endswith(".mp4"))

        # Should match pattern with empty stem
        pattern = r"^_\d{8}_\d{6}_[0-9a-f]{6}\.mp4$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_unique_filename_hex_suffix_length(self):
        # Test that hex suffix is exactly 6 characters
        filename = "video.mp4"
        result = utils.generate_unique_filename(filename)

        # Extract the hex suffix
        match = re.search(r"_([0-9a-f]{6})\.mp4$", result)
        self.assertIsNotNone(match)
        assert match is not None  # Type narrowing for linter

        hex_suffix = match.group(1)
        self.assertEqual(len(hex_suffix), 6)

        # All characters should be valid hex
        self.assertTrue(all(c in "0123456789abcdef" for c in hex_suffix))

    def test_normalize_device_name_for_url_basic(self):
        # Test basic normalization with spaces
        device_name = "HD Pro Webcam C920"
        result = utils.normalize_device_name_for_url(device_name)

        self.assertEqual(result, "hd_pro_webcam_c920")

    def test_normalize_device_name_for_url_with_colon(self):
        # Test normalization with colon (critical case for URL safety)
        device_name = "Thronmax StreamGo Webcam: Thron"
        result = utils.normalize_device_name_for_url(device_name)

        # Colon should be replaced with underscore
        self.assertEqual(result, "thronmax_streamgo_webcam__thron")
        self.assertNotIn(":", result)

    def test_normalize_device_name_for_url_special_characters(self):
        # Test normalization with various special characters
        device_name = "Camera/Model-123 (v2.0) @ 1080p"
        result = utils.normalize_device_name_for_url(device_name)

        # All special characters should be replaced with underscores
        self.assertEqual(result, "camera_model_123__v2_0____1080p")
        # Verify no special characters remain
        for char in result:
            self.assertTrue(char.isalnum() or char == "_")

    def test_normalize_device_name_for_url_already_normalized(self):
        # Test with already normalized name
        device_name = "usb_camera_device_0"
        result = utils.normalize_device_name_for_url(device_name)

        self.assertEqual(result, "usb_camera_device_0")

    def test_normalize_device_name_for_url_empty_string(self):
        # Test with empty string
        device_name = ""
        result = utils.normalize_device_name_for_url(device_name)

        self.assertEqual(result, "")

    def test_normalize_device_name_for_url_uppercase(self):
        # Test that uppercase is converted to lowercase
        device_name = "LOGITECH WEBCAM"
        result = utils.normalize_device_name_for_url(device_name)

        self.assertEqual(result, "logitech_webcam")
        self.assertTrue(result.islower() or result == "")

    def test_normalize_device_name_for_url_numbers_and_letters(self):
        # Test that alphanumeric characters are preserved
        device_name = "Camera123Model456"
        result = utils.normalize_device_name_for_url(device_name)

        self.assertEqual(result, "camera123model456")

    def test_normalize_device_name_for_url_multiple_spaces(self):
        # Test with multiple consecutive spaces
        device_name = "Camera   With    Spaces"
        result = utils.normalize_device_name_for_url(device_name)

        # Multiple spaces should become multiple underscores
        self.assertEqual(result, "camera___with____spaces")

    def test_normalize_device_name_for_url_url_unsafe_chars(self):
        # Test with characters that require percent-encoding in URLs
        device_name = "Camera?Model#123&name=test"
        result = utils.normalize_device_name_for_url(device_name)

        # All unsafe characters should be replaced
        self.assertEqual(result, "camera_model_123_name_test")
        # Verify result is URL-safe
        for char in result:
            self.assertTrue(char.isalnum() or char == "_")

    def test_normalize_device_name_for_url_real_usb_camera_names(self):
        # Test with real USB camera names
        test_cases = [
            ("HD Pro Webcam C920", "hd_pro_webcam_c920"),
            ("Integrated Camera: Integrated C", "integrated_camera__integrated_c"),
            ("Logitech Webcam C930e", "logitech_webcam_c930e"),
            ("USB2.0 HD UVC WebCam: USB2.0 HD", "usb2_0_hd_uvc_webcam__usb2_0_hd"),
        ]

        for input_name, expected_output in test_cases:
            with self.subTest(input_name=input_name):
                result = utils.normalize_device_name_for_url(input_name)
                self.assertEqual(result, expected_output)


if __name__ == "__main__":
    unittest.main()
