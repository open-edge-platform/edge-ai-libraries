import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from videos import (
    VIDEO_EXTENSIONS,
    Video,
    VideoFileInfo,
    VideosManager,
    collect_video_outputs_from_dirs,
)


class TestVideoFileInfo(unittest.TestCase):
    """Test cases for VideoFileInfo dataclass."""

    def test_video_file_info_codec_h264(self):
        """Test codec property returns h264 for avc fourcc."""
        # 'avc1' fourcc = 0x31637661
        fourcc = ord("a") | (ord("v") << 8) | (ord("c") << 16) | (ord("1") << 24)
        info = VideoFileInfo(
            width=1920,
            height=1080,
            fps=30.0,
            frame_count=900,
            fourcc=fourcc,
        )
        self.assertEqual(info.codec, "h264")

    def test_video_file_info_codec_h265(self):
        """Test codec property returns h265 for hevc fourcc."""
        # 'hevc' fourcc
        fourcc = ord("h") | (ord("e") << 8) | (ord("v") << 16) | (ord("c") << 24)
        info = VideoFileInfo(
            width=1920,
            height=1080,
            fps=30.0,
            frame_count=900,
            fourcc=fourcc,
        )
        self.assertEqual(info.codec, "h265")

    def test_video_file_info_codec_unknown(self):
        """Test codec property returns raw fourcc string for unknown codec."""
        # 'vp80' fourcc
        fourcc = ord("v") | (ord("p") << 8) | (ord("8") << 16) | (ord("0") << 24)
        info = VideoFileInfo(
            width=1920,
            height=1080,
            fps=30.0,
            frame_count=900,
            fourcc=fourcc,
        )
        self.assertEqual(info.codec, "vp80")

    def test_video_file_info_duration(self):
        """Test duration property calculation."""
        info = VideoFileInfo(
            width=1920,
            height=1080,
            fps=30.0,
            frame_count=900,
            fourcc=0,
        )
        self.assertEqual(info.duration, 30.0)

    def test_video_file_info_duration_zero_fps(self):
        """Test duration property returns 0 when fps is zero."""
        info = VideoFileInfo(
            width=1920,
            height=1080,
            fps=0.0,
            frame_count=900,
            fourcc=0,
        )
        self.assertEqual(info.duration, 0.0)


class TestVideo(unittest.TestCase):
    def test_video_initialization(self):
        """Test Video object initialization with all parameters."""
        video = Video(
            filename="test.mp4",
            width=1920,
            height=1080,
            fps=30.0,
            frame_count=900,
            codec="h264",
            duration=30.0,
        )
        self.assertEqual(video.filename, "test.mp4")
        self.assertEqual(video.width, 1920)
        self.assertEqual(video.height, 1080)
        self.assertEqual(video.fps, 30.0)
        self.assertEqual(video.frame_count, 900)
        self.assertEqual(video.codec, "h264")
        self.assertEqual(video.duration, 30.0)

    def test_video_to_dict(self):
        """Test serialization of Video object to dictionary."""
        video = Video(
            filename="test.mp4",
            width=1920,
            height=1080,
            fps=30.0,
            frame_count=900,
            codec="h264",
            duration=30.0,
        )
        video_dict = video.to_dict()
        self.assertEqual(video_dict["filename"], "test.mp4")
        self.assertEqual(video_dict["width"], 1920)
        self.assertEqual(video_dict["height"], 1080)
        self.assertEqual(video_dict["fps"], 30.0)
        self.assertEqual(video_dict["frame_count"], 900)
        self.assertEqual(video_dict["codec"], "h264")
        self.assertEqual(video_dict["duration"], 30.0)

    def test_video_from_dict(self):
        """Test deserialization of Video object from dictionary."""
        data = {
            "filename": "test.mp4",
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "frame_count": 900,
            "codec": "h264",
            "duration": 30.0,
        }
        video = Video.from_dict(data)
        self.assertEqual(video.filename, "test.mp4")
        self.assertEqual(video.width, 1920)
        self.assertEqual(video.height, 1080)
        self.assertEqual(video.fps, 30.0)
        self.assertEqual(video.frame_count, 900)
        self.assertEqual(video.codec, "h264")
        self.assertEqual(video.duration, 30.0)

    def test_video_roundtrip(self):
        """Test serialization and deserialization roundtrip."""
        original = Video(
            filename="test.mp4",
            width=1280,
            height=720,
            fps=25.0,
            frame_count=750,
            codec="h265",
            duration=30.0,
        )
        data = original.to_dict()
        restored = Video.from_dict(data)
        self.assertEqual(original.filename, restored.filename)
        self.assertEqual(original.width, restored.width)
        self.assertEqual(original.height, restored.height)
        self.assertEqual(original.fps, restored.fps)
        self.assertEqual(original.frame_count, restored.frame_count)
        self.assertEqual(original.codec, restored.codec)
        self.assertEqual(original.duration, restored.duration)


class TestVideosManager(unittest.TestCase):
    def setUp(self):
        """Create a temporary directory for testing and reset singleton."""
        self.temp_dir = tempfile.mkdtemp()
        # Reset singleton state before each test
        VideosManager._instance = None

    def tearDown(self):
        """Clean up temporary directory and reset singleton."""
        shutil.rmtree(self.temp_dir)
        # Reset singleton state after each test
        VideosManager._instance = None

    def test_singleton_returns_same_instance(self):
        """VideosManager() should return the same instance on multiple calls."""
        with patch("videos.INPUT_VIDEO_DIR", self.temp_dir):
            with patch.object(VideosManager, "_ensure_all_ts_conversions"):
                with patch.object(VideosManager, "_download_default_videos"):
                    instance1 = VideosManager()
                    instance2 = VideosManager()
                    self.assertIs(instance1, instance2)

    def test_videos_manager_invalid_directory(self):
        """Test VideosManager raises RuntimeError for invalid directory."""
        invalid_path = os.path.join(self.temp_dir, "nonexistent")
        with patch("videos.INPUT_VIDEO_DIR", invalid_path):
            with self.assertRaises(RuntimeError) as context:
                VideosManager()
            self.assertIn(
                "does not exist or is not a directory", str(context.exception)
            )

    @patch("videos.INPUT_VIDEO_DIR")
    @patch("cv2.VideoCapture")
    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_scan_with_video_files(
        self, mock_download, mock_ensure_ts, mock_videocap, mock_path
    ):
        """Test scanning directory with video files and extracting metadata."""
        mock_path.__str__ = lambda self: self.temp_dir
        mock_path.return_value = self.temp_dir
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        # Create dummy video files
        video_file = os.path.join(self.temp_dir, "test.mp4")
        with open(video_file, "w") as f:
            f.write("dummy video content")

        # Mock cv2.VideoCapture with avc fourcc for h264
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        fourcc = ord("a") | (ord("v") << 8) | (ord("c") << 16) | (ord("1") << 24)
        mock_cap.get.side_effect = lambda prop: {
            3: 1920,  # CAP_PROP_FRAME_WIDTH
            4: 1080,  # CAP_PROP_FRAME_HEIGHT
            5: 30.0,  # CAP_PROP_FPS
            7: 900,  # CAP_PROP_FRAME_COUNT
            6: fourcc,  # CAP_PROP_FOURCC (avc1)
        }.get(prop, 0)
        mock_videocap.return_value = mock_cap

        with patch("videos.INPUT_VIDEO_DIR", self.temp_dir):
            manager = VideosManager()
            videos = manager.get_all_videos()

        self.assertEqual(len(videos), 1)
        self.assertIn("test.mp4", videos)
        video = videos["test.mp4"]
        self.assertEqual(video.width, 1920)
        self.assertEqual(video.height, 1080)
        self.assertEqual(video.fps, 30.0)
        self.assertEqual(video.frame_count, 900)
        self.assertEqual(video.codec, "h264")
        self.assertEqual(video.duration, 30.0)

        # Check that JSON metadata was created
        json_path = os.path.join(self.temp_dir, "test.mp4.json")
        self.assertTrue(os.path.exists(json_path))

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_load_from_json(self, mock_download, mock_ensure_ts):
        """Test loading video metadata from existing JSON file."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        # Create dummy video file
        video_file = os.path.join(self.temp_dir, "test.mp4")
        with open(video_file, "w") as f:
            f.write("dummy video content")

        # Create JSON metadata
        json_path = os.path.join(self.temp_dir, "test.mp4.json")
        metadata = {
            "filename": "test.mp4",
            "width": 1280,
            "height": 720,
            "fps": 25.0,
            "frame_count": 750,
            "codec": "h265",
            "duration": 30.0,
        }
        with open(json_path, "w") as f:
            json.dump(metadata, f)

        with patch("videos.INPUT_VIDEO_DIR", self.temp_dir):
            manager = VideosManager()
            videos = manager.get_all_videos()

        self.assertEqual(len(videos), 1)
        video = videos["test.mp4"]
        self.assertEqual(video.codec, "h265")
        self.assertEqual(video.width, 1280)
        self.assertEqual(video.height, 720)

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_invalid_json(self, mock_download, mock_ensure_ts):
        """Test handling of corrupted JSON metadata file."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        # Create dummy video file
        video_file = os.path.join(self.temp_dir, "test.mp4")
        with open(video_file, "w") as f:
            f.write("dummy video content")

        # Create invalid JSON metadata
        json_path = os.path.join(self.temp_dir, "test.mp4.json")
        with open(json_path, "w") as f:
            f.write("invalid json content")

        # Should skip the file due to invalid JSON
        with patch("videos.INPUT_VIDEO_DIR", self.temp_dir):
            manager = VideosManager()
            videos = manager.get_all_videos()
        self.assertEqual(len(videos), 0)

    @patch("cv2.VideoCapture")
    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_unopenable_video(
        self, mock_download, mock_ensure_ts, mock_videocap
    ):
        """Test handling of video files that cannot be opened."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        video_file = os.path.join(self.temp_dir, "test.mp4")
        with open(video_file, "w") as f:
            f.write("dummy video content")

        # Mock cv2.VideoCapture to fail opening
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_videocap.return_value = mock_cap

        with patch("videos.INPUT_VIDEO_DIR", self.temp_dir):
            manager = VideosManager()
            videos = manager.get_all_videos()

        self.assertEqual(len(videos), 0)

    @patch("cv2.VideoCapture")
    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_unsupported_codec(
        self, mock_download, mock_ensure_ts, mock_videocap
    ):
        """Test handling of video files with unsupported codecs."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        video_file = os.path.join(self.temp_dir, "test.mp4")
        with open(video_file, "w") as f:
            f.write("dummy video content")

        # Mock cv2.VideoCapture with unsupported codec (vp80)
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        fourcc = ord("v") | (ord("p") << 8) | (ord("8") << 16) | (ord("0") << 24)
        mock_cap.get.side_effect = lambda prop: {
            3: 1920,
            4: 1080,
            5: 30.0,
            7: 900,
            6: fourcc,  # vp80
        }.get(prop, 0)
        mock_videocap.return_value = mock_cap

        with patch("videos.INPUT_VIDEO_DIR", self.temp_dir):
            manager = VideosManager()
            videos = manager.get_all_videos()

        self.assertEqual(len(videos), 0)

    @patch("cv2.VideoCapture")
    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_hevc_codec(
        self, mock_download, mock_ensure_ts, mock_videocap
    ):
        """Test handling of video files with HEVC/H.265 codec."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        video_file = os.path.join(self.temp_dir, "test.mp4")
        with open(video_file, "w") as f:
            f.write("dummy video content")

        # Mock cv2.VideoCapture with HEVC codec
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        fourcc = ord("h") | (ord("e") << 8) | (ord("v") << 16) | (ord("c") << 24)
        mock_cap.get.side_effect = lambda prop: {
            3: 1920,
            4: 1080,
            5: 30.0,
            7: 900,
            6: fourcc,  # hevc
        }.get(prop, 0)
        mock_videocap.return_value = mock_cap

        with patch("videos.INPUT_VIDEO_DIR", self.temp_dir):
            manager = VideosManager()
            videos = manager.get_all_videos()

        self.assertEqual(len(videos), 1)
        video = videos["test.mp4"]
        self.assertEqual(video.codec, "h265")

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_skip_non_video_files(self, mock_download, mock_ensure_ts):
        """Test that non-video files are skipped."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        # Create non-video files
        txt_file = os.path.join(self.temp_dir, "readme.txt")
        with open(txt_file, "w") as f:
            f.write("text content")

        with patch("videos.INPUT_VIDEO_DIR", self.temp_dir):
            manager = VideosManager()
            videos = manager.get_all_videos()

        self.assertEqual(len(videos), 0)

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_skip_directories(self, mock_download, mock_ensure_ts):
        """Test that directories are skipped during scanning."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        # Create a subdirectory
        subdir = os.path.join(self.temp_dir, "subdir")
        os.makedirs(subdir)

        with patch("videos.INPUT_VIDEO_DIR", self.temp_dir):
            manager = VideosManager()
            videos = manager.get_all_videos()

        self.assertEqual(len(videos), 0)

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_get_video(self, mock_download, mock_ensure_ts):
        """Test retrieving a specific video by filename."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        video_file = os.path.join(self.temp_dir, "test.mp4")
        json_path = os.path.join(self.temp_dir, "test.mp4.json")
        metadata = {
            "filename": "test.mp4",
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "frame_count": 900,
            "codec": "h264",
            "duration": 30.0,
        }
        with open(video_file, "w") as f:
            f.write("dummy")
        with open(json_path, "w") as f:
            json.dump(metadata, f)

        with patch("videos.INPUT_VIDEO_DIR", self.temp_dir):
            manager = VideosManager()
            video = manager.get_video("test.mp4")

        self.assertIsNotNone(video)
        assert video is not None  # Type narrowing for type checkers
        self.assertEqual(video.filename, "test.mp4")
        self.assertEqual(video.codec, "h264")

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_get_video_not_found(self, mock_download, mock_ensure_ts):
        """Test retrieving a non-existent video returns None."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        with patch("videos.INPUT_VIDEO_DIR", self.temp_dir):
            manager = VideosManager()
            video = manager.get_video("nonexistent.mp4")

        self.assertIsNone(video)

    @patch("cv2.VideoCapture")
    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_json_write_failure(
        self, mock_download, mock_ensure_ts, mock_videocap
    ):
        """Test handling of JSON write failures."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        video_file = os.path.join(self.temp_dir, "test.mp4")
        with open(video_file, "w") as f:
            f.write("dummy video content")

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        fourcc = ord("a") | (ord("v") << 8) | (ord("c") << 16) | (ord("1") << 24)
        mock_cap.get.side_effect = lambda prop: {
            3: 1920,
            4: 1080,
            5: 30.0,
            7: 900,
            6: fourcc,
        }.get(prop, 0)
        mock_videocap.return_value = mock_cap

        # Patch open to simulate write failure for JSON file
        original_open = open

        def mock_open_func(path, *args, **kwargs):
            if str(path).endswith(".json") and "w" in args:
                raise OSError("Permission denied")
            return original_open(path, *args, **kwargs)

        with patch("videos.INPUT_VIDEO_DIR", self.temp_dir):
            with patch("builtins.open", side_effect=mock_open_func):
                manager = VideosManager()
                videos = manager.get_all_videos()

        # Video should still be in memory even if JSON save failed
        self.assertEqual(len(videos), 1)

    @patch("cv2.VideoCapture")
    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_zero_fps(
        self, mock_download, mock_ensure_ts, mock_videocap
    ):
        """Test handling of video with zero FPS."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        video_file = os.path.join(self.temp_dir, "test.mp4")
        with open(video_file, "w") as f:
            f.write("dummy video content")

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        fourcc = ord("a") | (ord("v") << 8) | (ord("c") << 16) | (ord("1") << 24)
        mock_cap.get.side_effect = lambda prop: {
            3: 1920,
            4: 1080,
            5: 0.0,  # Zero FPS
            7: 0,
            6: fourcc,
        }.get(prop, 0)
        mock_videocap.return_value = mock_cap

        with patch("videos.INPUT_VIDEO_DIR", self.temp_dir):
            manager = VideosManager()
            videos = manager.get_all_videos()

        self.assertEqual(len(videos), 1)
        video = videos["test.mp4"]
        self.assertEqual(video.duration, 0.0)

    @patch("cv2.VideoCapture")
    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_multiple_video_extensions(
        self, mock_download, mock_ensure_ts, mock_videocap
    ):
        """Test scanning multiple video file extensions."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        for ext in ["mp4", "mkv", "avi"]:
            video_file = os.path.join(self.temp_dir, f"test.{ext}")
            with open(video_file, "w") as f:
                f.write("dummy video content")

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        fourcc = ord("a") | (ord("v") << 8) | (ord("c") << 16) | (ord("1") << 24)
        mock_cap.get.side_effect = lambda prop: {
            3: 1920,
            4: 1080,
            5: 30.0,
            7: 900,
            6: fourcc,
        }.get(prop, 0)
        mock_videocap.return_value = mock_cap

        with patch("videos.INPUT_VIDEO_DIR", self.temp_dir):
            manager = VideosManager()
            videos = manager.get_all_videos()

        self.assertEqual(len(videos), 3)
        self.assertIn("test.mp4", videos)
        self.assertIn("test.mkv", videos)
        self.assertIn("test.avi", videos)

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_get_ts_path_with_full_path(
        self, mock_download, mock_ensure_ts
    ):
        """Test get_ts_path returns full path to TS file."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        # Create video file and JSON metadata
        video_file = os.path.join(self.temp_dir, "test.mp4")
        ts_file = os.path.join(self.temp_dir, "test.ts")
        json_path = os.path.join(self.temp_dir, "test.mp4.json")
        ts_json_path = os.path.join(self.temp_dir, "test.ts.json")
        metadata = {
            "filename": "test.mp4",
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "frame_count": 900,
            "codec": "h264",
            "duration": 30.0,
        }
        ts_metadata = {
            "filename": "test.ts",
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "frame_count": 900,
            "codec": "h264",
            "duration": 30.0,
        }
        with open(video_file, "w") as f:
            f.write("dummy")
        with open(ts_file, "w") as f:
            f.write("dummy ts")
        with open(json_path, "w") as f:
            json.dump(metadata, f)
        with open(ts_json_path, "w") as f:
            json.dump(ts_metadata, f)

        with patch("videos.INPUT_VIDEO_DIR", self.temp_dir):
            manager = VideosManager()

            # Test mp4 to ts path conversion
            ts_path = manager.get_ts_path("test.mp4")
            self.assertEqual(ts_path, ts_file)

            # Test ts file returns full path
            ts_unchanged = manager.get_ts_path("test.ts")
            self.assertEqual(ts_unchanged, ts_file)

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_get_ts_path_unsupported(
        self, mock_download, mock_ensure_ts
    ):
        """Test get_ts_path returns None for unsupported extensions."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        with patch("videos.INPUT_VIDEO_DIR", self.temp_dir):
            manager = VideosManager()

            # Test unsupported extension
            unsupported_ts_path = manager.get_ts_path("test.xyz")
            self.assertIsNone(unsupported_ts_path)

            # Test empty string
            empty_ts_path = manager.get_ts_path("")
            self.assertIsNone(empty_ts_path)

    def test_videos_manager_demuxer_selection(self):
        """Test demuxer selection for video files."""
        self.assertEqual(VideosManager._get_demuxer_for_extension("mp4"), "qtdemux")
        self.assertEqual(VideosManager._get_demuxer_for_extension("mov"), "qtdemux")
        self.assertEqual(
            VideosManager._get_demuxer_for_extension("mkv"), "matroskademux"
        )
        self.assertEqual(VideosManager._get_demuxer_for_extension("avi"), "avidemux")
        self.assertEqual(VideosManager._get_demuxer_for_extension("flv"), "flvdemux")
        self.assertIsNone(VideosManager._get_demuxer_for_extension("xyz"))
        self.assertIsNone(VideosManager._get_demuxer_for_extension("ts"))

    def test_videos_manager_raw_stream_extension_detection(self):
        """Test raw stream extension detection."""
        self.assertTrue(VideosManager._is_raw_stream_extension("264"))
        self.assertTrue(VideosManager._is_raw_stream_extension("avc"))
        self.assertTrue(VideosManager._is_raw_stream_extension("h265"))
        self.assertTrue(VideosManager._is_raw_stream_extension("hevc"))
        self.assertFalse(VideosManager._is_raw_stream_extension("mp4"))
        self.assertFalse(VideosManager._is_raw_stream_extension("ts"))

    def test_video_extensions_constant(self):
        """Test VIDEO_EXTENSIONS constant."""
        self.assertIn("mp4", VIDEO_EXTENSIONS)
        self.assertIn("mkv", VIDEO_EXTENSIONS)
        self.assertIn("mov", VIDEO_EXTENSIONS)
        self.assertIn("avi", VIDEO_EXTENSIONS)
        self.assertIn("ts", VIDEO_EXTENSIONS)
        self.assertIn("264", VIDEO_EXTENSIONS)
        self.assertIn("avc", VIDEO_EXTENSIONS)
        self.assertIn("h265", VIDEO_EXTENSIONS)
        self.assertIn("hevc", VIDEO_EXTENSIONS)

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_get_video_filename(self, mock_download, mock_ensure_ts):
        """Test get_video_filename extracts filename from path."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        video_file = os.path.join(self.temp_dir, "test.mp4")
        json_path = os.path.join(self.temp_dir, "test.mp4.json")
        metadata = {
            "filename": "test.mp4",
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "frame_count": 900,
            "codec": "h264",
            "duration": 30.0,
        }
        with open(video_file, "w") as f:
            f.write("dummy")
        with open(json_path, "w") as f:
            json.dump(metadata, f)

        with patch("videos.INPUT_VIDEO_DIR", self.temp_dir):
            manager = VideosManager()

            # Test with full path
            filename = manager.get_video_filename("/some/path/test.mp4")
            self.assertEqual(filename, "test.mp4")

            # Test with just filename
            filename = manager.get_video_filename("test.mp4")
            self.assertEqual(filename, "test.mp4")

            # Test with non-existent video
            filename = manager.get_video_filename("nonexistent.mp4")
            self.assertIsNone(filename)

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_get_video_path(self, mock_download, mock_ensure_ts):
        """Test get_video_path returns full path for filename."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        video_file = os.path.join(self.temp_dir, "test.mp4")
        json_path = os.path.join(self.temp_dir, "test.mp4.json")
        metadata = {
            "filename": "test.mp4",
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "frame_count": 900,
            "codec": "h264",
            "duration": 30.0,
        }
        with open(video_file, "w") as f:
            f.write("dummy")
        with open(json_path, "w") as f:
            json.dump(metadata, f)

        with patch("videos.INPUT_VIDEO_DIR", self.temp_dir):
            manager = VideosManager()

            # Test existing video
            path = manager.get_video_path("test.mp4")
            self.assertEqual(path, video_file)

            # Test non-existent video
            path = manager.get_video_path("nonexistent.mp4")
            self.assertIsNone(path)

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    @patch.object(VideosManager, "_convert_to_ts")
    def test_videos_manager_ensure_ts_file(
        self, mock_convert, mock_download, mock_ensure_ts
    ):
        """Test ensure_ts_file creates TS file if not exists."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None
        mock_convert.return_value = True

        video_file = os.path.join(self.temp_dir, "test.mp4")
        json_path = os.path.join(self.temp_dir, "test.mp4.json")
        metadata = {
            "filename": "test.mp4",
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "frame_count": 900,
            "codec": "h264",
            "duration": 30.0,
        }
        with open(video_file, "w") as f:
            f.write("dummy")
        with open(json_path, "w") as f:
            json.dump(metadata, f)

        with patch("videos.INPUT_VIDEO_DIR", self.temp_dir):
            manager = VideosManager()

            # Call ensure_ts_file
            ts_path = manager.ensure_ts_file(video_file)

            # Verify _convert_to_ts was called
            mock_convert.assert_called_once()
            expected_ts_path = os.path.join(self.temp_dir, "test.ts")
            self.assertEqual(ts_path, expected_ts_path)


class TestCollectVideoOutputsFromDirs(unittest.TestCase):
    """Test cases for collect_video_outputs_from_dirs function."""

    def setUp(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_filters_only_video_extensions(self):
        """Test that only files with VIDEO_EXTENSIONS are returned."""
        pipeline_dir = os.path.join(self.temp_dir, "pipeline_1")
        os.makedirs(pipeline_dir)

        # Create files with various extensions
        for name in [
            "intermediate_stream000_out.mp4",
            "intermediate_stream000_out.avi",
            "intermediate_stream000_out.txt",
            "intermediate_stream000_out.json",
            "intermediate_stream000_out.log",
            "intermediate_stream000_out.ts",
        ]:
            with open(os.path.join(pipeline_dir, name), "w") as f:
                f.write("dummy")

        result = collect_video_outputs_from_dirs({"p1": pipeline_dir})

        self.assertEqual(len(result["p1"]), 3)
        extensions = {os.path.splitext(p)[1] for p in result["p1"]}
        self.assertEqual(extensions, {".mp4", ".avi", ".ts"})

    def test_main_output_placed_at_end(self):
        """Test that main_output files are placed at the end of the list."""
        pipeline_dir = os.path.join(self.temp_dir, "pipeline_1")
        os.makedirs(pipeline_dir)

        for name in [
            "main_output.mp4",
            "intermediate_stream000_recording.mp4",
            "intermediate_stream001_recording.mp4",
        ]:
            with open(os.path.join(pipeline_dir, name), "w") as f:
                f.write("dummy")

        result = collect_video_outputs_from_dirs({"p1": pipeline_dir})

        self.assertEqual(len(result["p1"]), 3)
        # main_output.mp4 must be last
        self.assertTrue(result["p1"][-1].endswith("main_output.mp4"))
        # Intermediate files come before
        for path in result["p1"][:-1]:
            self.assertIn("intermediate_stream", os.path.basename(path))

    def test_nonexistent_directory_returns_empty_list(self):
        """Test that a non-existent directory returns an empty list and logs a warning."""
        nonexistent = os.path.join(self.temp_dir, "does_not_exist")

        with self.assertLogs("videos", level="WARNING") as cm:
            result = collect_video_outputs_from_dirs({"p1": nonexistent})

        self.assertEqual(result["p1"], [])
        self.assertTrue(any("does not exist" in msg for msg in cm.output))

    def test_multiple_pipeline_directories(self):
        """Test scanning multiple pipeline directories independently."""
        dir_a = os.path.join(self.temp_dir, "pipeline_a")
        dir_b = os.path.join(self.temp_dir, "pipeline_b")
        os.makedirs(dir_a)
        os.makedirs(dir_b)

        with open(os.path.join(dir_a, "main_output.mp4"), "w") as f:
            f.write("dummy")
        with open(os.path.join(dir_a, "intermediate_stream000_rec.mp4"), "w") as f:
            f.write("dummy")

        with open(os.path.join(dir_b, "intermediate_stream000_out.avi"), "w") as f:
            f.write("dummy")

        result = collect_video_outputs_from_dirs({"a": dir_a, "b": dir_b})

        self.assertEqual(len(result["a"]), 2)
        self.assertTrue(result["a"][-1].endswith("main_output.mp4"))

        self.assertEqual(len(result["b"]), 1)
        self.assertTrue(result["b"][0].endswith("intermediate_stream000_out.avi"))

    def test_empty_directory_returns_empty_list(self):
        """Test that an empty directory returns an empty list."""
        empty_dir = os.path.join(self.temp_dir, "empty")
        os.makedirs(empty_dir)

        result = collect_video_outputs_from_dirs({"p1": empty_dir})

        self.assertEqual(result["p1"], [])

    def test_subdirectories_are_ignored(self):
        """Test that subdirectories inside the pipeline directory are not included."""
        pipeline_dir = os.path.join(self.temp_dir, "pipeline_1")
        os.makedirs(pipeline_dir)

        # Create a subdirectory with a video-like name
        subdir = os.path.join(pipeline_dir, "subdir.mp4")
        os.makedirs(subdir)

        # Create a regular video file
        with open(
            os.path.join(pipeline_dir, "intermediate_stream000_out.mp4"), "w"
        ) as f:
            f.write("dummy")

        result = collect_video_outputs_from_dirs({"p1": pipeline_dir})

        self.assertEqual(len(result["p1"]), 1)
        self.assertTrue(result["p1"][0].endswith("intermediate_stream000_out.mp4"))

    def test_empty_input_returns_empty_dict(self):
        """Test that an empty input dictionary returns an empty result."""
        result = collect_video_outputs_from_dirs({})
        self.assertEqual(result, {})

    def test_files_are_sorted_alphabetically(self):
        """Test that intermediate files are returned in alphabetical order."""
        pipeline_dir = os.path.join(self.temp_dir, "pipeline_1")
        os.makedirs(pipeline_dir)

        for name in [
            "intermediate_stream002_c.mp4",
            "intermediate_stream000_a.mp4",
            "intermediate_stream001_b.mp4",
        ]:
            with open(os.path.join(pipeline_dir, name), "w") as f:
                f.write("dummy")

        result = collect_video_outputs_from_dirs({"p1": pipeline_dir})

        basenames = [os.path.basename(p) for p in result["p1"]]
        self.assertEqual(
            basenames,
            [
                "intermediate_stream000_a.mp4",
                "intermediate_stream001_b.mp4",
                "intermediate_stream002_c.mp4",
            ],
        )

    def test_splitmuxsink_pattern_files_collected(self):
        """Test that files produced by splitmuxsink pattern naming are collected."""
        pipeline_dir = os.path.join(self.temp_dir, "pipeline_1")
        os.makedirs(pipeline_dir)

        for name in [
            "intermediate_stream000_recording_000.mp4",
            "intermediate_stream000_recording_001.mp4",
            "intermediate_stream000_recording_002.mp4",
            "main_output.mp4",
        ]:
            with open(os.path.join(pipeline_dir, name), "w") as f:
                f.write("dummy")

        result = collect_video_outputs_from_dirs({"p1": pipeline_dir})

        self.assertEqual(len(result["p1"]), 4)
        # main_output must be last
        self.assertTrue(result["p1"][-1].endswith("main_output.mp4"))
        # Splitmuxsink files should be in order
        basenames = [os.path.basename(p) for p in result["p1"][:-1]]
        self.assertEqual(
            basenames,
            [
                "intermediate_stream000_recording_000.mp4",
                "intermediate_stream000_recording_001.mp4",
                "intermediate_stream000_recording_002.mp4",
            ],
        )


if __name__ == "__main__":
    unittest.main()
