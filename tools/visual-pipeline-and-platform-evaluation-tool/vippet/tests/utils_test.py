import base64
import os
import re
import tempfile
import unittest
from datetime import datetime, timezone

import utils


class TestGenerateUniqueId(unittest.TestCase):
    """Tests for generate_unique_id function."""

    def test_generate_unique_id_basic_slugify(self):
        # Test that text is properly slugified
        result = utils.generate_unique_id("My Test Pipeline", [])
        self.assertEqual(result, "my-test-pipeline")

    def test_generate_unique_id_with_prefix(self):
        # Test that prefix is prepended correctly
        result = utils.generate_unique_id("test", [], prefix="pipeline")
        self.assertEqual(result, "pipeline-test")

    def test_generate_unique_id_max_length(self):
        # Test that slugify respects max_length of 64 characters
        long_text = "This is a very long pipeline name that exceeds the limit"
        result = utils.generate_unique_id(long_text, [])
        # Slug part should be max 64 chars
        self.assertLessEqual(len(result), 64)

    def test_generate_unique_id_no_collision(self):
        # Test that ID is returned as-is when no collision
        result = utils.generate_unique_id("unique-name", ["other-name"])
        self.assertEqual(result, "unique-name")

    def test_generate_unique_id_with_collision(self):
        # Test that hash suffix is added on collision
        existing = ["test"]
        result = utils.generate_unique_id("test", existing)

        # Should start with "test-" and have 6 hex chars suffix
        self.assertTrue(result.startswith("test-"))
        self.assertNotEqual(result, "test")

        # Pattern: test-<6 hex chars>
        pattern = r"^test-[0-9a-f]{6}$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_unique_id_multiple_collisions(self):
        # Test that function handles multiple collisions
        # Create a list with many potential collisions
        existing = ["test", "test-000000", "test-111111"]
        result = utils.generate_unique_id("test", existing)

        # Result should not be in existing list
        self.assertNotIn(result, existing)

        # Should still match the expected pattern
        self.assertTrue(result.startswith("test-"))

    def test_generate_unique_id_special_chars(self):
        # Test that special characters are properly handled by slugify
        result = utils.generate_unique_id("Test@Pipeline#123!", [])
        # Slugify converts special characters to dashes and cleans up
        self.assertEqual(result, "test-pipeline-123")

    def test_generate_unique_id_unicode(self):
        # Test with unicode characters
        result = utils.generate_unique_id("Тест Pipeline", [])
        # Slugify handles unicode by transliterating or removing
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_generate_unique_id_empty_text(self):
        # Test with empty text
        result = utils.generate_unique_id("", [])
        # Empty slug should still work
        self.assertEqual(result, "")

    def test_generate_unique_id_whitespace(self):
        # Test that whitespace is converted to dashes
        result = utils.generate_unique_id("my test pipeline", [])
        self.assertEqual(result, "my-test-pipeline")

    def test_generate_unique_id_prefix_with_collision(self):
        # Test prefix with collision
        existing = ["pipeline-test"]
        result = utils.generate_unique_id("test", existing, prefix="pipeline")

        # Should have hash suffix due to collision
        self.assertTrue(result.startswith("pipeline-test-"))
        pattern = r"^pipeline-test-[0-9a-f]{6}$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_unique_id_collision_produces_unique(self):
        # Test that collision resolution produces unique results
        existing = ["test"]
        results = set()
        for _ in range(10):
            result = utils.generate_unique_id("test", existing)
            results.add(result)

        # All results should be unique (not equal to "test")
        self.assertNotIn("test", results)


class TestIsYolov10Model(unittest.TestCase):
    """Tests for is_yolov10_model function."""

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


class TestMakeTeeNamesUnique(unittest.TestCase):
    """Tests for make_tee_names_unique function."""

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


class TestGenerateUniqueFilename(unittest.TestCase):
    """Tests for generate_unique_filename function."""

    def test_generate_unique_filename_basic(self):
        # Test basic filename generation with extension
        filename = "video.mp4"
        result = utils.generate_unique_filename(filename)

        # Should start with "video-"
        self.assertTrue(result.startswith("video-"))

        # Should end with ".mp4"
        self.assertTrue(result.endswith(".mp4"))

        # Should match pattern: stem-YYYYMMDD_HHMMSS-<6hex>.mp4
        pattern = r"^video-\d{8}_\d{6}-[0-9a-f]{6}\.mp4$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_unique_filename_no_extension(self):
        # Test filename generation without extension (should default to .mp4)
        filename = "video"
        result = utils.generate_unique_filename(filename)

        # Should end with default ".mp4" extension
        self.assertTrue(result.endswith(".mp4"))

        # Should match pattern with default extension
        pattern = r"^video-\d{8}_\d{6}-[0-9a-f]{6}\.mp4$"
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

        # Should start with "video-"
        self.assertTrue(result.startswith("video-"))

        # Should end with ".mp4"
        self.assertTrue(result.endswith(".mp4"))

    def test_generate_unique_filename_complex_name(self):
        # Test with complex filename containing underscores and numbers
        filename = "test_video_123.mp4"
        result = utils.generate_unique_filename(filename)

        # Should start with the original stem
        self.assertTrue(result.startswith("test_video_123-"))

        # Should match pattern
        pattern = r"^test_video_123-\d{8}_\d{6}-[0-9a-f]{6}\.mp4$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_unique_filename_special_characters(self):
        # Test with special characters in filename
        filename = "test-video.mp4"
        result = utils.generate_unique_filename(filename)

        # Should preserve special characters in stem
        self.assertTrue(result.startswith("test-video-"))

        # Should match pattern
        pattern = r"^test-video-\d{8}_\d{6}-[0-9a-f]{6}\.mp4$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_unique_filename_empty_string(self):
        # Test with empty string (edge case)
        filename = ""
        result = utils.generate_unique_filename(filename)

        # Should generate with default extension
        self.assertTrue(result.endswith(".mp4"))

        # Should match pattern with empty stem
        pattern = r"^-\d{8}_\d{6}-[0-9a-f]{6}\.mp4$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_unique_filename_hex_suffix_length(self):
        # Test that hex suffix is exactly 6 characters
        filename = "video.mp4"
        result = utils.generate_unique_filename(filename)

        # Extract the hex suffix
        match = re.search(r"-([0-9a-f]{6})\.mp4$", result)
        assert match is not None  # Type narrowing for linter

        hex_suffix = match.group(1)
        self.assertEqual(len(hex_suffix), 6)

        # All characters should be valid hex
        self.assertTrue(all(c in "0123456789abcdef" for c in hex_suffix))


class TestGeneratePipelineGraphId(unittest.TestCase):
    """Tests for generate_pipeline_graph_id function.

    This function generates synthetic pipeline IDs from inline graph hashes.
    Used when pipelines are provided inline instead of referencing stored variants.
    """

    def test_generate_pipeline_graph_id_format(self):
        # Test that the generated ID follows the expected format: __graph-<16-char-hash>
        pipeline_graph = {
            "nodes": [{"id": "0", "type": "filesrc", "data": {}}],
            "edges": [],
        }
        result = utils.generate_pipeline_graph_id(pipeline_graph)

        # Should start with __graph- prefix
        self.assertTrue(result.startswith("__graph-"))

        # Should match pattern: __graph-<16 hex chars>
        pattern = r"^__graph-[0-9a-f]{16}$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_pipeline_graph_id_hash_length(self):
        # Test that hash part is exactly 16 characters
        pipeline_graph = {
            "nodes": [{"id": "0", "type": "videotestsrc", "data": {}}],
            "edges": [],
        }
        result = utils.generate_pipeline_graph_id(pipeline_graph)

        # Extract hash part after "__graph-"
        hash_part = result[len("__graph-") :]
        self.assertEqual(len(hash_part), 16)

        # All characters should be valid hex
        self.assertTrue(all(c in "0123456789abcdef" for c in hash_part))

    def test_generate_pipeline_graph_id_consistency(self):
        # Test that same input produces same output (deterministic)
        pipeline_graph = {
            "nodes": [
                {"id": "0", "type": "filesrc", "data": {"location": "/video.mp4"}},
                {"id": "1", "type": "fakesink", "data": {}},
            ],
            "edges": [{"id": "0", "source": "0", "target": "1"}],
        }

        # Generate ID multiple times
        result1 = utils.generate_pipeline_graph_id(pipeline_graph)
        result2 = utils.generate_pipeline_graph_id(pipeline_graph)
        result3 = utils.generate_pipeline_graph_id(pipeline_graph)

        # All should be identical
        self.assertEqual(result1, result2)
        self.assertEqual(result2, result3)

    def test_generate_pipeline_graph_id_different_inputs(self):
        # Test that different inputs produce different outputs
        graph1 = {
            "nodes": [{"id": "0", "type": "filesrc", "data": {}}],
            "edges": [],
        }
        graph2 = {
            "nodes": [{"id": "0", "type": "videotestsrc", "data": {}}],
            "edges": [],
        }
        graph3 = {
            "nodes": [
                {"id": "0", "type": "filesrc", "data": {}},
                {"id": "1", "type": "fakesink", "data": {}},
            ],
            "edges": [{"id": "0", "source": "0", "target": "1"}],
        }

        id1 = utils.generate_pipeline_graph_id(graph1)
        id2 = utils.generate_pipeline_graph_id(graph2)
        id3 = utils.generate_pipeline_graph_id(graph3)

        # All IDs should be different
        self.assertNotEqual(id1, id2)
        self.assertNotEqual(id2, id3)
        self.assertNotEqual(id1, id3)

    def test_generate_pipeline_graph_id_empty_graph(self):
        # Test with empty graph (edge case)
        empty_graph = {"nodes": [], "edges": []}
        result = utils.generate_pipeline_graph_id(empty_graph)

        # Should still return valid format
        pattern = r"^__graph-[0-9a-f]{16}$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_pipeline_graph_id_empty_dict(self):
        # Test with completely empty dict (edge case)
        empty_dict: dict = {}
        result = utils.generate_pipeline_graph_id(empty_dict)

        # Should still return valid format
        pattern = r"^__graph-[0-9a-f]{16}$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_pipeline_graph_id_complex_graph(self):
        # Test with complex graph structure similar to real pipelines
        complex_graph = {
            "nodes": [
                {
                    "id": "0",
                    "type": "filesrc",
                    "data": {"location": "/videos/input/test.mp4"},
                },
                {"id": "1", "type": "decodebin", "data": {}},
                {"id": "2", "type": "videoconvert", "data": {}},
                {
                    "id": "3",
                    "type": "gvadetect",
                    "data": {
                        "model": "/models/yolo.xml",
                        "device": "CPU",
                        "threshold": "0.5",
                    },
                },
                {"id": "4", "type": "gvawatermark", "data": {}},
                {"id": "5", "type": "fakesink", "data": {}},
            ],
            "edges": [
                {"id": "0", "source": "0", "target": "1"},
                {"id": "1", "source": "1", "target": "2"},
                {"id": "2", "source": "2", "target": "3"},
                {"id": "3", "source": "3", "target": "4"},
                {"id": "4", "source": "4", "target": "5"},
            ],
        }

        result = utils.generate_pipeline_graph_id(complex_graph)

        # Should return valid format
        pattern = r"^__graph-[0-9a-f]{16}$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_pipeline_graph_id_key_order_independence(self):
        # Test that key order in dict does not affect the hash (sorted keys)
        graph1 = {
            "nodes": [{"id": "0", "type": "src", "data": {}}],
            "edges": [],
        }
        graph2 = {
            "edges": [],
            "nodes": [{"data": {}, "id": "0", "type": "src"}],
        }

        id1 = utils.generate_pipeline_graph_id(graph1)
        id2 = utils.generate_pipeline_graph_id(graph2)

        # Both should produce the same ID because JSON is sorted
        self.assertEqual(id1, id2)

    def test_generate_pipeline_graph_id_with_special_chars_in_data(self):
        # Test with special characters in node data
        graph = {
            "nodes": [
                {
                    "id": "0",
                    "type": "filesrc",
                    "data": {"location": "/path/with spaces/file (1).mp4"},
                }
            ],
            "edges": [],
        }

        result = utils.generate_pipeline_graph_id(graph)

        # Should return valid format
        pattern = r"^__graph-[0-9a-f]{16}$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_pipeline_graph_id_with_unicode(self):
        # Test with unicode characters in data
        graph = {
            "nodes": [{"id": "0", "type": "src", "data": {"name": "тест"}}],
            "edges": [],
        }

        result = utils.generate_pipeline_graph_id(graph)

        # Should return valid format
        pattern = r"^__graph-[0-9a-f]{16}$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_pipeline_graph_id_small_data_change(self):
        # Test that small data changes produce different IDs
        graph1 = {
            "nodes": [{"id": "0", "type": "gvadetect", "data": {"threshold": "0.5"}}],
            "edges": [],
        }
        graph2 = {
            "nodes": [{"id": "0", "type": "gvadetect", "data": {"threshold": "0.6"}}],
            "edges": [],
        }

        id1 = utils.generate_pipeline_graph_id(graph1)
        id2 = utils.generate_pipeline_graph_id(graph2)

        # Different threshold values should produce different IDs
        self.assertNotEqual(id1, id2)


class TestGeneratePipelineDescriptionId(unittest.TestCase):
    """Tests for generate_pipeline_description_id function.

    This function generates synthetic pipeline IDs from pipeline description string hashes.
    Used when pipeline descriptions are provided instead of referencing stored variants.
    """

    def test_generate_pipeline_description_id_format(self):
        # Test that the generated ID follows the expected format: __description-<16-char-hash>
        pipeline_description = "videotestsrc ! videoconvert ! fakesink"
        result = utils.generate_pipeline_description_id(pipeline_description)

        # Should start with __description- prefix
        self.assertTrue(result.startswith("__description-"))

        # Should match pattern: __description-<16 hex chars>
        pattern = r"^__description-[0-9a-f]{16}$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_pipeline_description_id_hash_length(self):
        # Test that hash part is exactly 16 characters
        pipeline_description = "filesrc location=/test.mp4 ! decodebin ! fakesink"
        result = utils.generate_pipeline_description_id(pipeline_description)

        # Extract hash part after "__description-"
        hash_part = result[len("__description-") :]
        self.assertEqual(len(hash_part), 16)

        # All characters should be valid hex
        self.assertTrue(all(c in "0123456789abcdef" for c in hash_part))

    def test_generate_pipeline_description_id_consistency(self):
        # Test that same input produces same output (deterministic)
        pipeline_description = "videotestsrc ! queue ! videoconvert ! fakesink"

        # Generate ID multiple times
        result1 = utils.generate_pipeline_description_id(pipeline_description)
        result2 = utils.generate_pipeline_description_id(pipeline_description)
        result3 = utils.generate_pipeline_description_id(pipeline_description)

        # All should be identical
        self.assertEqual(result1, result2)
        self.assertEqual(result2, result3)

    def test_generate_pipeline_description_id_different_inputs(self):
        # Test that different inputs produce different outputs
        desc1 = "videotestsrc ! fakesink"
        desc2 = "filesrc location=/test.mp4 ! fakesink"
        desc3 = "videotestsrc ! videoconvert ! autovideosink"

        id1 = utils.generate_pipeline_description_id(desc1)
        id2 = utils.generate_pipeline_description_id(desc2)
        id3 = utils.generate_pipeline_description_id(desc3)

        # All IDs should be different
        self.assertNotEqual(id1, id2)
        self.assertNotEqual(id2, id3)
        self.assertNotEqual(id1, id3)

    def test_generate_pipeline_description_id_empty_string(self):
        # Test with empty string (edge case)
        empty_desc = ""
        result = utils.generate_pipeline_description_id(empty_desc)

        # Should still return valid format
        pattern = r"^__description-[0-9a-f]{16}$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_pipeline_description_id_whitespace_only(self):
        # Test with whitespace only string
        whitespace_desc = "   "
        result = utils.generate_pipeline_description_id(whitespace_desc)

        # Should return valid format
        pattern = r"^__description-[0-9a-f]{16}$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_pipeline_description_id_complex_pipeline(self):
        # Test with complex pipeline description
        complex_desc = (
            "filesrc location=/videos/input/test.mp4 ! decodebin ! videoconvert ! "
            "gvadetect model=/models/yolo.xml device=CPU threshold=0.5 ! "
            "gvawatermark ! videoconvert ! fakesink"
        )

        result = utils.generate_pipeline_description_id(complex_desc)

        # Should return valid format
        pattern = r"^__description-[0-9a-f]{16}$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_pipeline_description_id_with_special_chars(self):
        # Test with special characters in description
        special_desc = "filesrc location='/path with spaces/file (1).mp4' ! fakesink"

        result = utils.generate_pipeline_description_id(special_desc)

        # Should return valid format
        pattern = r"^__description-[0-9a-f]{16}$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_pipeline_description_id_with_unicode(self):
        # Test with unicode characters in description
        unicode_desc = "filesrc location=/путь/к/файлу.mp4 ! fakesink"

        result = utils.generate_pipeline_description_id(unicode_desc)

        # Should return valid format
        pattern = r"^__description-[0-9a-f]{16}$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_pipeline_description_id_small_change(self):
        # Test that small changes produce different IDs
        desc1 = "videotestsrc ! fakesink"
        desc2 = "videotestsrc  ! fakesink"  # Extra space

        id1 = utils.generate_pipeline_description_id(desc1)
        id2 = utils.generate_pipeline_description_id(desc2)

        # Different descriptions should produce different IDs
        self.assertNotEqual(id1, id2)

    def test_generate_pipeline_description_id_newlines(self):
        # Test with newlines in description
        desc_with_newlines = "videotestsrc !\n  videoconvert !\n  fakesink"

        result = utils.generate_pipeline_description_id(desc_with_newlines)

        # Should return valid format
        pattern = r"^__description-[0-9a-f]{16}$"
        self.assertIsNotNone(re.match(pattern, result))

    def test_generate_pipeline_description_id_long_description(self):
        # Test with very long pipeline description
        long_desc = " ! ".join(["queue"] * 100) + " ! fakesink"

        result = utils.generate_pipeline_description_id(long_desc)

        # Should return valid format
        pattern = r"^__description-[0-9a-f]{16}$"
        self.assertIsNotNone(re.match(pattern, result))


class TestGetCurrentTimestamp(unittest.TestCase):
    """Tests for get_current_timestamp function."""

    def test_get_current_timestamp_returns_datetime(self):
        # Test that result is a datetime object
        result = utils.get_current_timestamp()
        self.assertIsInstance(result, datetime)

    def test_get_current_timestamp_has_utc_timezone(self):
        # Test that timestamp has UTC timezone
        result = utils.get_current_timestamp()
        self.assertEqual(result.tzinfo, timezone.utc)

    def test_get_current_timestamp_is_recent(self):
        # Test that timestamp is close to current time
        before = datetime.now(timezone.utc)
        result = utils.get_current_timestamp()
        after = datetime.now(timezone.utc)

        self.assertGreaterEqual(result, before)
        self.assertLessEqual(result, after)

    def test_get_current_timestamp_uniqueness_over_time(self):
        # Test that timestamps change over time (not identical)
        import time

        timestamp1 = utils.get_current_timestamp()
        time.sleep(0.01)  # Sleep for 10ms
        timestamp2 = utils.get_current_timestamp()

        # Second timestamp should be later
        self.assertGreater(timestamp2, timestamp1)

    def test_get_current_timestamp_year_range(self):
        # Test that year is reasonable (2020-2100)
        result = utils.get_current_timestamp()
        self.assertGreaterEqual(result.year, 2020)
        self.assertLessEqual(result.year, 2100)

    def test_get_current_timestamp_month_range(self):
        # Test that month is valid (1-12)
        result = utils.get_current_timestamp()
        self.assertGreaterEqual(result.month, 1)
        self.assertLessEqual(result.month, 12)

    def test_get_current_timestamp_day_range(self):
        # Test that day is valid (1-31)
        result = utils.get_current_timestamp()
        self.assertGreaterEqual(result.day, 1)
        self.assertLessEqual(result.day, 31)

    def test_get_current_timestamp_hour_range(self):
        # Test that hour is valid (0-23)
        result = utils.get_current_timestamp()
        self.assertGreaterEqual(result.hour, 0)
        self.assertLessEqual(result.hour, 23)

    def test_get_current_timestamp_minute_range(self):
        # Test that minute is valid (0-59)
        result = utils.get_current_timestamp()
        self.assertGreaterEqual(result.minute, 0)
        self.assertLessEqual(result.minute, 59)

    def test_get_current_timestamp_second_range(self):
        # Test that second is valid (0-59)
        result = utils.get_current_timestamp()
        self.assertGreaterEqual(result.second, 0)
        self.assertLessEqual(result.second, 59)

    def test_get_current_timestamp_has_microseconds(self):
        # Test that timestamp includes microseconds
        result = utils.get_current_timestamp()
        # microsecond should be between 0 and 999999
        self.assertGreaterEqual(result.microsecond, 0)
        self.assertLessEqual(result.microsecond, 999999)


class TestLoadThumbnailAsBase64(unittest.TestCase):
    """Tests for load_thumbnail_as_base64 function."""

    def setUp(self):
        # Create a temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        # Clean up temporary files
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_temp_file(self, filename: str, content: bytes) -> str:
        """Helper to create a temporary file with given content."""
        filepath = os.path.join(self.temp_dir, filename)
        with open(filepath, "wb") as f:
            f.write(content)
        return filepath

    def test_load_thumbnail_as_base64_png(self):
        # Test loading a valid PNG file
        # PNG signature: 89 50 4E 47 (0x89 'P' 'N' 'G')
        png_content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        filepath = self._create_temp_file("test.png", png_content)

        result = utils.load_thumbnail_as_base64(filepath, "test-pipeline")

        assert result is not None  # Type narrowing for pyright
        # Verify it's a valid data URI with correct MIME type
        self.assertTrue(result.startswith("data:image/png;base64,"))
        # Extract and verify base64 content
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        self.assertEqual(decoded, png_content)

    def test_load_thumbnail_as_base64_jpeg(self):
        # Test loading a valid JPEG file
        # JPEG signature: FF D8 FF
        jpeg_content = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        filepath = self._create_temp_file("test.jpg", jpeg_content)

        result = utils.load_thumbnail_as_base64(filepath, "test-pipeline")

        assert result is not None  # Type narrowing for pyright
        # Verify it's a valid data URI with correct MIME type
        self.assertTrue(result.startswith("data:image/jpeg;base64,"))
        # Extract and verify base64 content
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        self.assertEqual(decoded, jpeg_content)

    def test_load_thumbnail_as_base64_gif(self):
        # Test loading a valid GIF file
        # GIF signature: 47 49 46 ('G' 'I' 'F')
        gif_content = b"GIF89a" + b"\x00" * 100
        filepath = self._create_temp_file("test.gif", gif_content)

        result = utils.load_thumbnail_as_base64(filepath, "test-pipeline")

        assert result is not None  # Type narrowing for pyright
        # Verify it's a valid data URI with correct MIME type
        self.assertTrue(result.startswith("data:image/gif;base64,"))
        # Extract and verify base64 content
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        self.assertEqual(decoded, gif_content)

    def test_load_thumbnail_as_base64_empty_path(self):
        # Test with empty thumbnail path
        result = utils.load_thumbnail_as_base64("", "test-pipeline")
        self.assertIsNone(result)

    def test_load_thumbnail_as_base64_nonexistent_file(self):
        # Test with non-existent file path
        result = utils.load_thumbnail_as_base64(
            "/nonexistent/path/image.png", "test-pipeline"
        )
        self.assertIsNone(result)

    def test_load_thumbnail_as_base64_invalid_format(self):
        # Test with file that is not a valid image
        invalid_content = b"This is not an image file"
        filepath = self._create_temp_file("test.txt", invalid_content)

        result = utils.load_thumbnail_as_base64(filepath, "test-pipeline")

        self.assertIsNone(result)

    def test_load_thumbnail_as_base64_partial_png_signature(self):
        # Test with file that has partial PNG signature (invalid)
        invalid_content = b"\x89PN" + b"\x00" * 100  # Missing 'G'
        filepath = self._create_temp_file("invalid.png", invalid_content)

        result = utils.load_thumbnail_as_base64(filepath, "test-pipeline")

        self.assertIsNone(result)

    def test_load_thumbnail_as_base64_partial_jpeg_signature(self):
        # Test with file that has partial JPEG signature (invalid)
        invalid_content = b"\xff\xd8" + b"\x00" * 100  # Missing third byte
        filepath = self._create_temp_file("invalid.jpg", invalid_content)

        result = utils.load_thumbnail_as_base64(filepath, "test-pipeline")

        self.assertIsNone(result)

    def test_load_thumbnail_as_base64_empty_file(self):
        # Test with empty file
        filepath = self._create_temp_file("empty.png", b"")

        result = utils.load_thumbnail_as_base64(filepath, "test-pipeline")

        self.assertIsNone(result)

    def test_load_thumbnail_as_base64_returns_string(self):
        # Test that result is a string
        png_content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        filepath = self._create_temp_file("test.png", png_content)

        result = utils.load_thumbnail_as_base64(filepath, "test-pipeline")

        assert result is not None  # Type narrowing for pyright
        self.assertIsInstance(result, str)
        # Verify data URI format
        self.assertTrue(result.startswith("data:image/"))

    def test_load_thumbnail_as_base64_valid_base64_encoding(self):
        # Test that result is valid data URI that can be decoded
        png_content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        filepath = self._create_temp_file("test.png", png_content)

        result = utils.load_thumbnail_as_base64(filepath, "test-pipeline")

        assert result is not None  # Type narrowing for pyright
        # Should be a valid data URI
        self.assertTrue(result.startswith("data:image/png;base64,"))
        try:
            base64_part = result.split(",", 1)[1]
            decoded = base64.b64decode(base64_part)
            self.assertEqual(decoded, png_content)
        except Exception as e:
            self.fail(f"Failed to decode base64 result: {e}")

    def test_load_thumbnail_as_base64_binary_content_preserved(self):
        # Test that binary content is preserved through base64 encoding
        # Create PNG with various byte values
        png_content = b"\x89PNG\r\n\x1a\n" + bytes(range(256))
        filepath = self._create_temp_file("binary.png", png_content)

        result = utils.load_thumbnail_as_base64(filepath, "test-pipeline")

        assert result is not None  # Type narrowing for pyright
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        self.assertEqual(decoded, png_content)

    def test_load_thumbnail_as_base64_large_file(self):
        # Test with a larger file (1MB)
        png_header = b"\x89PNG\r\n\x1a\n"
        large_content = png_header + b"\x00" * (1024 * 1024)  # 1MB of zeros
        filepath = self._create_temp_file("large.png", large_content)

        result = utils.load_thumbnail_as_base64(filepath, "test-pipeline")

        assert result is not None  # Type narrowing for pyright
        self.assertTrue(result.startswith("data:image/png;base64,"))
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        self.assertEqual(len(decoded), len(large_content))

    def test_load_thumbnail_as_base64_gif87a(self):
        # Test with GIF87a format
        gif_content = b"GIF87a" + b"\x00" * 100
        filepath = self._create_temp_file("test87a.gif", gif_content)

        result = utils.load_thumbnail_as_base64(filepath, "test-pipeline")

        assert result is not None  # Type narrowing for pyright
        self.assertTrue(result.startswith("data:image/gif;base64,"))

    def test_load_thumbnail_as_base64_gif89a(self):
        # Test with GIF89a format
        gif_content = b"GIF89a" + b"\x00" * 100
        filepath = self._create_temp_file("test89a.gif", gif_content)

        result = utils.load_thumbnail_as_base64(filepath, "test-pipeline")

        assert result is not None  # Type narrowing for pyright
        self.assertTrue(result.startswith("data:image/gif;base64,"))

    def test_load_thumbnail_as_base64_with_special_path_chars(self):
        # Test with path containing spaces
        subdir = os.path.join(self.temp_dir, "path with spaces")
        os.makedirs(subdir)
        png_content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        filepath = os.path.join(subdir, "test image.png")
        with open(filepath, "wb") as f:
            f.write(png_content)

        result = utils.load_thumbnail_as_base64(filepath, "test-pipeline")

        assert result is not None  # Type narrowing for pyright
        self.assertTrue(result.startswith("data:image/png;base64,"))

    def test_load_thumbnail_as_base64_with_base_path_relative(self):
        # Test loading thumbnail with relative path and base_path
        png_content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        # Create subdirectory structure
        subdir = os.path.join(self.temp_dir, "thumbnails")
        os.makedirs(subdir)
        filepath = os.path.join(subdir, "test.png")
        with open(filepath, "wb") as f:
            f.write(png_content)

        # Use relative path with base_path
        result = utils.load_thumbnail_as_base64(
            "thumbnails/test.png", "test-pipeline", base_path=self.temp_dir
        )

        assert result is not None  # Type narrowing for linter
        self.assertTrue(result.startswith("data:image/png;base64,"))
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        self.assertEqual(decoded, png_content)

    def test_load_thumbnail_as_base64_with_base_path_absolute_path_unchanged(self):
        # Test that absolute paths are not affected by base_path
        png_content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        filepath = self._create_temp_file("test.png", png_content)

        # Even with base_path, absolute path should work
        result = utils.load_thumbnail_as_base64(
            filepath, "test-pipeline", base_path="/some/other/path"
        )

        assert result is not None  # Type narrowing for linter
        self.assertTrue(result.startswith("data:image/png;base64,"))
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        self.assertEqual(decoded, png_content)

    def test_load_thumbnail_as_base64_with_base_path_nonexistent_relative(self):
        # Test with relative path that doesn't exist under base_path
        result = utils.load_thumbnail_as_base64(
            "nonexistent/image.png", "test-pipeline", base_path=self.temp_dir
        )

        self.assertIsNone(result)

    def test_load_thumbnail_as_base64_without_base_path_relative_fails(self):
        # Test that relative path without base_path fails (as expected)
        result = utils.load_thumbnail_as_base64(
            "relative/path/image.png", "test-pipeline"
        )

        self.assertIsNone(result)

    def test_load_thumbnail_as_base64_data_uri_format(self):
        """Test that the result follows the data URI format."""
        png_content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        filepath = self._create_temp_file("test.png", png_content)

        result = utils.load_thumbnail_as_base64(filepath, "test-pipeline")

        assert result is not None
        # Verify data URI format: data:{mime};base64,{data}
        self.assertRegex(result, r"^data:image/(png|jpeg|gif);base64,[A-Za-z0-9+/=]+")


class TestSlugifyText(unittest.TestCase):
    """Tests for slugify_text function."""

    def test_slugify_text_basic(self):
        # Test basic text slugification
        result = utils.slugify_text("My Test Pipeline")
        self.assertEqual(result, "my-test-pipeline")

    def test_slugify_text_with_special_chars(self):
        # Test with special characters
        result = utils.slugify_text("Test@Pipeline#123!")
        self.assertEqual(result, "test-pipeline-123")

    def test_slugify_text_with_max_length(self):
        # Test with max_length limit
        result = utils.slugify_text("This is a very long text", max_length=10)
        self.assertLessEqual(len(result), 10)

    def test_slugify_text_no_max_length(self):
        # Test without max_length (default 0)
        long_text = "This is a very long pipeline name that should not be truncated"
        result = utils.slugify_text(long_text)
        # Should contain the full slugified text
        self.assertIn("this-is-a-very-long", result)

    def test_slugify_text_already_slugified(self):
        # Test with already slugified text
        result = utils.slugify_text("my-test-pipeline")
        self.assertEqual(result, "my-test-pipeline")

    def test_slugify_text_uppercase(self):
        # Test that uppercase is converted to lowercase
        result = utils.slugify_text("MY-TEST-PIPELINE")
        self.assertEqual(result, "my-test-pipeline")

    def test_slugify_text_spaces(self):
        # Test that spaces are converted to dashes
        result = utils.slugify_text("my test pipeline")
        self.assertEqual(result, "my-test-pipeline")

    def test_slugify_text_empty_string(self):
        # Test with empty string
        result = utils.slugify_text("")
        self.assertEqual(result, "")

    def test_slugify_text_numbers(self):
        # Test with numbers
        result = utils.slugify_text("pipeline-123-test")
        self.assertEqual(result, "pipeline-123-test")

    def test_slugify_text_unicode(self):
        # Test with unicode characters
        result = utils.slugify_text("тест pipeline")
        # Should handle unicode (transliterate or remove)
        self.assertIsInstance(result, str)

    def test_slugify_text_max_length_zero(self):
        # Test that max_length=0 means no limit
        long_text = "a" * 200
        result = utils.slugify_text(long_text, max_length=0)
        self.assertEqual(len(result), 200)

    def test_slugify_text_consecutive_special_chars(self):
        # Test with consecutive special characters
        result = utils.slugify_text("test---pipeline")
        # Slugify typically collapses multiple dashes
        self.assertNotIn("---", result)


if __name__ == "__main__":
    unittest.main()
