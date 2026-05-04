import json
import os
import shutil
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from videos import (
    VIDEO_EXTENSIONS,
    Video,
    VideoFileInfo,
    VideosManager,
    collect_video_outputs_from_dirs,
)


@contextmanager
def _patch_video_dirs(auto_dir: str, uploaded_dir: str):
    """Patch both AUTO_VIDEO_DIR and UPLOADED_VIDEO_DIR on the videos module.

    The manager scans both subdirs, so tests must override them together to
    avoid hitting the production paths under /videos/input.
    """
    with (
        patch("videos.AUTO_VIDEO_DIR", auto_dir),
        patch("videos.UPLOADED_VIDEO_DIR", uploaded_dir),
    ):
        yield


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
            source="uploaded",
            path="uploaded/test.mp4",
        )
        self.assertEqual(video.filename, "test.mp4")
        self.assertEqual(video.width, 1920)
        self.assertEqual(video.height, 1080)
        self.assertEqual(video.fps, 30.0)
        self.assertEqual(video.frame_count, 900)
        self.assertEqual(video.codec, "h264")
        self.assertEqual(video.duration, 30.0)
        self.assertEqual(video.source, "uploaded")
        self.assertEqual(video.path, "uploaded/test.mp4")

    def test_video_default_source_and_path(self):
        """Video defaults to 'auto' source and empty path when not given."""
        video = Video(
            filename="t.mp4",
            width=1,
            height=1,
            fps=1.0,
            frame_count=1,
            codec="h264",
            duration=1.0,
        )
        self.assertEqual(video.source, "auto")
        self.assertEqual(video.path, "")

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
            source="auto",
            path="auto/test.mp4",
        )
        video_dict = video.to_dict()
        self.assertEqual(video_dict["filename"], "test.mp4")
        self.assertEqual(video_dict["width"], 1920)
        self.assertEqual(video_dict["height"], 1080)
        self.assertEqual(video_dict["fps"], 30.0)
        self.assertEqual(video_dict["frame_count"], 900)
        self.assertEqual(video_dict["codec"], "h264")
        self.assertEqual(video_dict["duration"], 30.0)
        self.assertEqual(video_dict["source"], "auto")
        self.assertEqual(video_dict["path"], "auto/test.mp4")

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
            "source": "uploaded",
            "path": "uploaded/test.mp4",
        }
        video = Video.from_dict(data)
        self.assertEqual(video.filename, "test.mp4")
        self.assertEqual(video.width, 1920)
        self.assertEqual(video.height, 1080)
        self.assertEqual(video.fps, 30.0)
        self.assertEqual(video.frame_count, 900)
        self.assertEqual(video.codec, "h264")
        self.assertEqual(video.duration, 30.0)
        self.assertEqual(video.source, "uploaded")
        self.assertEqual(video.path, "uploaded/test.mp4")

    def test_video_from_dict_missing_source_and_path(self):
        """from_dict tolerates legacy JSON without source/path fields."""
        data = {
            "filename": "legacy.mp4",
            "width": 640,
            "height": 480,
            "fps": 24.0,
            "frame_count": 240,
            "codec": "h264",
            "duration": 10.0,
        }
        video = Video.from_dict(data)
        self.assertEqual(video.source, "auto")
        self.assertEqual(video.path, "")

    def test_video_from_dict_invalid_source_falls_back_to_auto(self):
        """Unknown source values are coerced to 'auto' for safety."""
        data = {
            "filename": "bad.mp4",
            "width": 1,
            "height": 1,
            "fps": 1.0,
            "frame_count": 1,
            "codec": "h264",
            "duration": 1.0,
            "source": "bogus",
            "path": "auto/bad.mp4",
        }
        video = Video.from_dict(data)
        self.assertEqual(video.source, "auto")

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
            source="uploaded",
            path="uploaded/test.mp4",
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
        self.assertEqual(original.source, restored.source)
        self.assertEqual(original.path, restored.path)


class TestVideosManager(unittest.TestCase):
    def setUp(self):
        """Create isolated auto/uploaded subdirs and reset the singleton.

        VideosManager scans both AUTO_VIDEO_DIR and UPLOADED_VIDEO_DIR, so
        each test gets a dedicated pair of directories under a temp root.
        """
        self.temp_dir = tempfile.mkdtemp()
        self.auto_dir = os.path.join(self.temp_dir, "auto")
        self.uploaded_dir = os.path.join(self.temp_dir, "uploaded")
        os.makedirs(self.auto_dir)
        os.makedirs(self.uploaded_dir)
        # Reset singleton state before each test
        VideosManager._instance = None

    def tearDown(self):
        """Clean up temporary directory and reset singleton."""
        shutil.rmtree(self.temp_dir)
        # Reset singleton state after each test
        VideosManager._instance = None

    def _patch_dirs(self):
        """Shortcut for patching both input directories in one go."""
        return _patch_video_dirs(self.auto_dir, self.uploaded_dir)

    def test_singleton_returns_same_instance(self):
        """VideosManager() should return the same instance on multiple calls."""
        with self._patch_dirs():
            with patch.object(VideosManager, "_ensure_all_ts_conversions"):
                with patch.object(VideosManager, "_download_default_videos"):
                    instance1 = VideosManager()
                    instance2 = VideosManager()
                    self.assertIs(instance1, instance2)

    def test_videos_manager_invalid_directory(self):
        """VideosManager raises RuntimeError when subdirs cannot be created."""
        with self._patch_dirs():
            with patch("videos.os.makedirs", side_effect=OSError("boom")):
                with self.assertRaises(RuntimeError) as context:
                    VideosManager()
        self.assertIn("Failed to create video subdirectory", str(context.exception))

    @patch("cv2.VideoCapture")
    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_scan_with_video_files(
        self, mock_download, mock_ensure_ts, mock_videocap
    ):
        """Test scanning directory with video files and extracting metadata."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        # Create dummy video file in the auto subdir
        video_file = os.path.join(self.auto_dir, "test.mp4")
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

        with self._patch_dirs():
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
        # source/path should be populated from the subdir the file lives in
        self.assertEqual(video.source, "auto")
        self.assertEqual(video.path, "auto/test.mp4")

        # Check that JSON metadata was created next to the video file
        json_path = os.path.join(self.auto_dir, "test.mp4.json")
        self.assertTrue(os.path.exists(json_path))

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_load_from_json(self, mock_download, mock_ensure_ts):
        """Test loading video metadata from existing JSON file."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        # Create dummy video file and JSON metadata in the auto subdir
        video_file = os.path.join(self.auto_dir, "test.mp4")
        with open(video_file, "w") as f:
            f.write("dummy video content")

        json_path = os.path.join(self.auto_dir, "test.mp4.json")
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

        with self._patch_dirs():
            manager = VideosManager()
            videos = manager.get_all_videos()

        self.assertEqual(len(videos), 1)
        video = videos["test.mp4"]
        self.assertEqual(video.codec, "h265")
        self.assertEqual(video.width, 1280)
        self.assertEqual(video.height, 720)
        # source/path are always refreshed from on-disk location
        self.assertEqual(video.source, "auto")
        self.assertEqual(video.path, "auto/test.mp4")

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_invalid_json(self, mock_download, mock_ensure_ts):
        """Test handling of corrupted JSON metadata file."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        # Create dummy video file
        video_file = os.path.join(self.auto_dir, "test.mp4")
        with open(video_file, "w") as f:
            f.write("dummy video content")

        # Create invalid JSON metadata
        json_path = os.path.join(self.auto_dir, "test.mp4.json")
        with open(json_path, "w") as f:
            f.write("invalid json content")

        # Should skip the file due to invalid JSON
        with self._patch_dirs():
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

        video_file = os.path.join(self.auto_dir, "test.mp4")
        with open(video_file, "w") as f:
            f.write("dummy video content")

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_videocap.return_value = mock_cap

        with self._patch_dirs():
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

        video_file = os.path.join(self.auto_dir, "test.mp4")
        with open(video_file, "w") as f:
            f.write("dummy video content")

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        fourcc = ord("v") | (ord("p") << 8) | (ord("8") << 16) | (ord("0") << 24)
        mock_cap.get.side_effect = lambda prop: {
            3: 1920,
            4: 1080,
            5: 30.0,
            7: 900,
            6: fourcc,
        }.get(prop, 0)
        mock_videocap.return_value = mock_cap

        with self._patch_dirs():
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

        video_file = os.path.join(self.auto_dir, "test.mp4")
        with open(video_file, "w") as f:
            f.write("dummy video content")

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        fourcc = ord("h") | (ord("e") << 8) | (ord("v") << 16) | (ord("c") << 24)
        mock_cap.get.side_effect = lambda prop: {
            3: 1920,
            4: 1080,
            5: 30.0,
            7: 900,
            6: fourcc,
        }.get(prop, 0)
        mock_videocap.return_value = mock_cap

        with self._patch_dirs():
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

        txt_file = os.path.join(self.auto_dir, "readme.txt")
        with open(txt_file, "w") as f:
            f.write("text content")

        with self._patch_dirs():
            manager = VideosManager()
            videos = manager.get_all_videos()

        self.assertEqual(len(videos), 0)

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_skip_directories(self, mock_download, mock_ensure_ts):
        """Test that directories are skipped during scanning."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        subdir = os.path.join(self.auto_dir, "subdir")
        os.makedirs(subdir)

        with self._patch_dirs():
            manager = VideosManager()
            videos = manager.get_all_videos()

        self.assertEqual(len(videos), 0)

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_get_video(self, mock_download, mock_ensure_ts):
        """Test retrieving a specific video by filename."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        video_file = os.path.join(self.auto_dir, "test.mp4")
        json_path = os.path.join(self.auto_dir, "test.mp4.json")
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

        with self._patch_dirs():
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

        with self._patch_dirs():
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

        video_file = os.path.join(self.auto_dir, "test.mp4")
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

        with self._patch_dirs():
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

        video_file = os.path.join(self.auto_dir, "test.mp4")
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

        with self._patch_dirs():
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
            video_file = os.path.join(self.auto_dir, f"test.{ext}")
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

        with self._patch_dirs():
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

        # Create video file and JSON metadata in auto subdir
        video_file = os.path.join(self.auto_dir, "test.mp4")
        ts_file = os.path.join(self.auto_dir, "test.ts")
        json_path = os.path.join(self.auto_dir, "test.mp4.json")
        ts_json_path = os.path.join(self.auto_dir, "test.ts.json")
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

        with self._patch_dirs():
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

        with self._patch_dirs():
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

        video_file = os.path.join(self.auto_dir, "test.mp4")
        json_path = os.path.join(self.auto_dir, "test.mp4.json")
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

        with self._patch_dirs():
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

        video_file = os.path.join(self.auto_dir, "test.mp4")
        json_path = os.path.join(self.auto_dir, "test.mp4.json")
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

        with self._patch_dirs():
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

        video_file = os.path.join(self.auto_dir, "test.mp4")
        json_path = os.path.join(self.auto_dir, "test.mp4.json")
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

        with self._patch_dirs():
            manager = VideosManager()

            # Call ensure_ts_file
            ts_path = manager.ensure_ts_file(video_file)

            # Verify _convert_to_ts was called
            mock_convert.assert_called_once()
            # TS file should sit next to the source video (same subdir).
            expected_ts_path = os.path.join(self.auto_dir, "test.ts")
            self.assertEqual(ts_path, expected_ts_path)

    # ------------------------------------------------------------------
    # New functionality: auto vs uploaded routing and helpers.
    # ------------------------------------------------------------------

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_scans_uploaded_subdir(self, mock_download, mock_ensure_ts):
        """Videos placed under UPLOADED_VIDEO_DIR are tagged source=uploaded."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        # Pre-seed a metadata JSON so cv2 is not invoked during the scan.
        video_file = os.path.join(self.uploaded_dir, "mine.mp4")
        json_path = os.path.join(self.uploaded_dir, "mine.mp4.json")
        metadata = {
            "filename": "mine.mp4",
            "width": 640,
            "height": 480,
            "fps": 24.0,
            "frame_count": 240,
            "codec": "h264",
            "duration": 10.0,
            # Intentionally stale values to confirm the scan overrides them.
            "source": "auto",
            "path": "auto/mine.mp4",
        }
        with open(video_file, "w") as f:
            f.write("dummy")
        with open(json_path, "w") as f:
            json.dump(metadata, f)

        with self._patch_dirs():
            manager = VideosManager()
            video = manager.get_video("mine.mp4")

        self.assertIsNotNone(video)
        assert video is not None
        self.assertEqual(video.source, "uploaded")
        self.assertEqual(video.path, "uploaded/mine.mp4")

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_uploaded_overrides_auto_duplicate(
        self, mock_download, mock_ensure_ts
    ):
        """When the same filename is in both subdirs, 'uploaded' wins."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        # Same filename in both auto and uploaded with valid metadata.
        for subdir in (self.auto_dir, self.uploaded_dir):
            video_file = os.path.join(subdir, "clash.mp4")
            json_path = os.path.join(subdir, "clash.mp4.json")
            with open(video_file, "w") as f:
                f.write("dummy")
            with open(json_path, "w") as f:
                json.dump(
                    {
                        "filename": "clash.mp4",
                        "width": 1,
                        "height": 1,
                        "fps": 1.0,
                        "frame_count": 1,
                        "codec": "h264",
                        "duration": 1.0,
                    },
                    f,
                )

        with self._patch_dirs():
            manager = VideosManager()
            video = manager.get_video("clash.mp4")
            path = manager.get_video_path("clash.mp4")

        assert video is not None
        self.assertEqual(video.source, "uploaded")
        self.assertEqual(path, os.path.join(self.uploaded_dir, "clash.mp4"))

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_filename_exists(self, mock_download, mock_ensure_ts):
        """filename_exists returns True for files in either subdir."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        # File known to the in-memory map via the scan.
        video_file = os.path.join(self.auto_dir, "known.mp4")
        json_path = os.path.join(self.auto_dir, "known.mp4.json")
        with open(video_file, "w") as f:
            f.write("dummy")
        with open(json_path, "w") as f:
            json.dump(
                {
                    "filename": "known.mp4",
                    "width": 1,
                    "height": 1,
                    "fps": 1.0,
                    "frame_count": 1,
                    "codec": "h264",
                    "duration": 1.0,
                },
                f,
            )

        with self._patch_dirs():
            manager = VideosManager()

            # In the in-memory map.
            self.assertTrue(manager.filename_exists("known.mp4"))

            # File appears on disk after the scan -> fallback hits it.
            stray = os.path.join(self.uploaded_dir, "stray.mp4")
            with open(stray, "w") as f:
                f.write("dummy")
            self.assertTrue(manager.filename_exists("stray.mp4"))

            # Unknown filename.
            self.assertFalse(manager.filename_exists("missing.mp4"))
            # Empty filename is rejected.
            self.assertFalse(manager.filename_exists(""))

            # Path traversal components are stripped via basename.
            traversal = os.path.join(self.auto_dir, "known.mp4")
            self.assertTrue(manager.filename_exists(f"../../{traversal}"))

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_source_for_path(self, mock_download, mock_ensure_ts):
        """_source_for_path classifies files by their parent directory."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        with self._patch_dirs():
            # Need an instance so the patched module-level constants apply.
            VideosManager()

            auto_path = os.path.join(self.auto_dir, "a.mp4")
            uploaded_path = os.path.join(self.uploaded_dir, "u.mp4")
            other_path = os.path.join(self.temp_dir, "other.mp4")

            self.assertEqual(VideosManager._source_for_path(auto_path), "auto")
            self.assertEqual(VideosManager._source_for_path(uploaded_path), "uploaded")
            # Unknown parents default to 'auto'.
            self.assertEqual(VideosManager._source_for_path(other_path), "auto")

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    @patch.object(VideosManager, "_convert_to_ts")
    def test_videos_manager_ensure_ts_file_uploaded(
        self, mock_convert, mock_download, mock_ensure_ts
    ):
        """TS files land next to uploaded videos (not next to auto videos)."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None
        mock_convert.return_value = True

        video_file = os.path.join(self.uploaded_dir, "upload.mp4")
        json_path = os.path.join(self.uploaded_dir, "upload.mp4.json")
        with open(video_file, "w") as f:
            f.write("dummy")
        with open(json_path, "w") as f:
            json.dump(
                {
                    "filename": "upload.mp4",
                    "width": 1,
                    "height": 1,
                    "fps": 1.0,
                    "frame_count": 1,
                    "codec": "h264",
                    "duration": 1.0,
                },
                f,
            )

        with self._patch_dirs():
            manager = VideosManager()
            ts_path = manager.ensure_ts_file(video_file)

        expected_ts_path = os.path.join(self.uploaded_dir, "upload.ts")
        self.assertEqual(ts_path, expected_ts_path)

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_register_uploaded_video(
        self, mock_download, mock_ensure_ts
    ):
        """register_uploaded_video moves the temp file and records TS entry."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        # Create a "temp" file that will be moved into UPLOADED_VIDEO_DIR.
        temp_path = os.path.join(self.temp_dir, ".upload-abc.mp4")
        with open(temp_path, "w") as f:
            f.write("dummy")

        # Pre-seed metadata JSON the final target will inherit after move.
        # _ensure_video_metadata creates the JSON itself via _extract, so we
        # mock that helper to avoid invoking cv2 on a fake file.
        def fake_extract(file_path):
            return VideoFileInfo(
                width=1280,
                height=720,
                fps=30.0,
                frame_count=300,
                fourcc=ord("a") | (ord("v") << 8) | (ord("c") << 16) | (ord("1") << 24),
            )

        with self._patch_dirs():
            with patch.object(
                VideosManager, "_extract_video_file_info", side_effect=fake_extract
            ):
                with patch.object(VideosManager, "_convert_to_ts", return_value=True):
                    # Simulate the TS file actually appearing on disk after
                    # conversion so ensure_ts_file registers it.
                    def write_ts_after_convert(*args, **kwargs):
                        ts_path = args[1]
                        with open(ts_path, "w") as f:
                            f.write("ts")
                        return True

                    with patch.object(
                        VideosManager,
                        "_convert_to_ts",
                        side_effect=write_ts_after_convert,
                    ):
                        manager = VideosManager()
                        original, ts_video = manager.register_uploaded_video(
                            temp_path, "myclip.mp4"
                        )

        # Original file moved into place and tracked by the manager.
        target_path = os.path.join(self.uploaded_dir, "myclip.mp4")
        self.assertTrue(os.path.isfile(target_path))
        self.assertEqual(original.filename, "myclip.mp4")
        self.assertEqual(original.source, "uploaded")
        self.assertEqual(original.path, "uploaded/myclip.mp4")

        # TS companion created next to it and also tracked.
        self.assertIsNotNone(ts_video)
        assert ts_video is not None
        self.assertEqual(ts_video.filename, "myclip.ts")
        self.assertEqual(ts_video.source, "uploaded")

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_register_uploaded_video_already_ts(
        self, mock_download, mock_ensure_ts
    ):
        """Uploading a .ts file skips the conversion step."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        temp_path = os.path.join(self.temp_dir, ".upload-xyz.ts")
        with open(temp_path, "w") as f:
            f.write("dummy")

        def fake_extract(file_path):
            return VideoFileInfo(
                width=640,
                height=480,
                fps=24.0,
                frame_count=240,
                fourcc=ord("h") | (ord("e") << 8) | (ord("v") << 16) | (ord("c") << 24),
            )

        with self._patch_dirs():
            with patch.object(
                VideosManager, "_extract_video_file_info", side_effect=fake_extract
            ):
                with patch.object(VideosManager, "_convert_to_ts") as mock_convert:
                    manager = VideosManager()
                    original, ts_video = manager.register_uploaded_video(
                        temp_path, "already.ts"
                    )
                    # No conversion should have been attempted.
                    mock_convert.assert_not_called()

        self.assertEqual(original.filename, "already.ts")
        self.assertIsNone(ts_video)

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    @patch.object(VideosManager, "_download_default_videos")
    def test_videos_manager_register_uploaded_video_metadata_failure(
        self, mock_download, mock_ensure_ts
    ):
        """Failure to extract metadata rolls back and cleans artifacts."""
        mock_ensure_ts.return_value = None
        mock_download.return_value = None

        temp_path = os.path.join(self.temp_dir, ".upload-bad.mp4")
        with open(temp_path, "w") as f:
            f.write("dummy")

        # _extract_video_file_info returns None -> _ensure_video_metadata
        # returns None -> register_uploaded_video raises.
        with self._patch_dirs():
            with patch.object(
                VideosManager, "_extract_video_file_info", return_value=None
            ):
                manager = VideosManager()
                with self.assertRaises(RuntimeError):
                    manager.register_uploaded_video(temp_path, "bad.mp4")

        # No leftover on disk after the failure.
        self.assertFalse(os.path.isfile(os.path.join(self.uploaded_dir, "bad.mp4")))
        self.assertFalse(
            os.path.isfile(os.path.join(self.uploaded_dir, "bad.mp4.json"))
        )


class TestDownloadDefaultVideos(unittest.TestCase):
    """Tests for VideosManager._download_default_videos and its helpers."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.auto_dir = os.path.join(self.temp_dir, "auto")
        self.uploaded_dir = os.path.join(self.temp_dir, "uploaded")
        os.makedirs(self.auto_dir)
        os.makedirs(self.uploaded_dir)
        VideosManager._instance = None

    def tearDown(self):
        shutil.rmtree(self.temp_dir)
        VideosManager._instance = None

    def _patch_dirs(self):
        return _patch_video_dirs(self.auto_dir, self.uploaded_dir)

    def _make_manager(self):
        """Instantiate a manager with download/TS phases disabled."""
        with (
            patch.object(VideosManager, "_download_default_videos"),
            patch.object(VideosManager, "_ensure_all_ts_conversions"),
        ):
            return VideosManager()

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    def test_missing_recordings_file_is_logged_and_skipped(self, _mock_ensure_ts):
        """Missing DEFAULT_RECORDINGS_FILE logs an error and returns."""
        with self._patch_dirs():
            with patch(
                "videos.DEFAULT_RECORDINGS_FILE",
                os.path.join(self.temp_dir, "no-such.yaml"),
            ):
                with self.assertLogs("videos", level="ERROR") as cm:
                    VideosManager()
        self.assertTrue(
            any("Default recordings file" in msg for msg in cm.output),
            cm.output,
        )

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    def test_empty_recordings_file_is_skipped(self, _mock_ensure_ts):
        """An empty recordings list short-circuits with a debug log."""
        yaml_path = os.path.join(self.temp_dir, "rec.yaml")
        with open(yaml_path, "w") as f:
            f.write("[]\n")

        with self._patch_dirs():
            with patch("videos.DEFAULT_RECORDINGS_FILE", yaml_path):
                with patch.object(VideosManager, "_download_video") as mock_dl:
                    VideosManager()
        mock_dl.assert_not_called()

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    def test_invalid_recording_entry_is_skipped(self, _mock_ensure_ts):
        """Entries missing url/filename are skipped with a warning."""
        yaml_path = os.path.join(self.temp_dir, "rec.yaml")
        with open(yaml_path, "w") as f:
            f.write(
                "- filename: only-name.mp4\n"
                "- url: https://example.test/only-url.mp4\n"
                "- url: https://example.test/good.mp4\n"
                "  filename: good.mp4\n"
            )

        with self._patch_dirs():
            with patch("videos.DEFAULT_RECORDINGS_FILE", yaml_path):
                with patch.object(VideosManager, "_download_video") as mock_dl:
                    with self.assertLogs("videos", level="WARNING") as cm:
                        VideosManager()

        # Only the valid entry triggers a download attempt.
        mock_dl.assert_called_once_with("https://example.test/good.mp4", "good.mp4")
        self.assertTrue(any("Invalid recording entry" in m for m in cm.output))

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    def test_load_recordings_rejects_non_list(self, _mock_ensure_ts):
        """A YAML document that isn't a list is rejected with an error log."""
        yaml_path = os.path.join(self.temp_dir, "rec.yaml")
        with open(yaml_path, "w") as f:
            f.write("name: not-a-list\n")

        with self._patch_dirs():
            with patch("videos.DEFAULT_RECORDINGS_FILE", yaml_path):
                with self.assertLogs("videos", level="ERROR") as cm:
                    VideosManager()
        self.assertTrue(any("expected list" in m for m in cm.output))

    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    def test_load_recordings_handles_exception(self, _mock_ensure_ts):
        """An unreadable YAML file is logged and treated as empty."""
        yaml_path = os.path.join(self.temp_dir, "rec.yaml")
        # Non-existent via open() in _load_recordings_yaml after the
        # existence check -> simulate by removing read permission.
        with open(yaml_path, "w") as f:
            f.write(": : not valid yaml\n{{{")

        with self._patch_dirs():
            with patch("videos.DEFAULT_RECORDINGS_FILE", yaml_path):
                with self.assertLogs("videos", level="ERROR") as cm:
                    VideosManager()
        self.assertTrue(
            any("Failed to load recordings YAML" in m for m in cm.output),
            cm.output,
        )


class TestDownloadVideo(unittest.TestCase):
    """Tests for VideosManager._download_video and related helpers."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.auto_dir = os.path.join(self.temp_dir, "auto")
        self.uploaded_dir = os.path.join(self.temp_dir, "uploaded")
        os.makedirs(self.auto_dir)
        os.makedirs(self.uploaded_dir)
        VideosManager._instance = None

    def tearDown(self):
        shutil.rmtree(self.temp_dir)
        VideosManager._instance = None

    def _patch_dirs(self):
        return _patch_video_dirs(self.auto_dir, self.uploaded_dir)

    def _make_manager(self):
        with (
            patch.object(VideosManager, "_download_default_videos"),
            patch.object(VideosManager, "_ensure_all_ts_conversions"),
        ):
            return VideosManager()

    def test_skip_when_file_already_exists(self):
        """Existing target files short-circuit the download."""
        target = os.path.join(self.auto_dir, "already.mp4")
        with open(target, "w") as f:
            f.write("x")

        with self._patch_dirs():
            manager = self._make_manager()
            with patch("videos.urllib.request.urlopen") as mock_urlopen:
                result = manager._download_video("http://x", "already.mp4")

        self.assertEqual(result, target)
        mock_urlopen.assert_not_called()

    def test_http_non_200_returns_none(self):
        """A non-200 HTTP response aborts the download."""
        with self._patch_dirs():
            manager = self._make_manager()

            fake_response = MagicMock()
            fake_response.status = 404
            fake_response.__enter__.return_value = fake_response
            fake_response.__exit__.return_value = False

            with patch("videos.urllib.request.urlopen", return_value=fake_response):
                with self.assertLogs("videos", level="ERROR") as cm:
                    result = manager._download_video("http://x", "missing.mp4")

        self.assertIsNone(result)
        self.assertTrue(any("HTTP 404" in m for m in cm.output))

    def test_move_failure_after_download_returns_none(self):
        """A failed move after a successful download propagates as None."""
        with self._patch_dirs():
            manager = self._make_manager()

            fake_response = MagicMock()
            fake_response.status = 200
            fake_response.read.side_effect = [b"data", b""]
            fake_response.__enter__.return_value = fake_response
            fake_response.__exit__.return_value = False

            with patch("videos.urllib.request.urlopen", return_value=fake_response):
                with patch.object(VideosManager, "_move_file", return_value=False):
                    result = manager._download_video("http://x", "broken.mp4")

        self.assertIsNone(result)

    def test_http_error_is_caught_and_cleaned_up(self):
        """HTTPError triggers a warning and removes the temp file."""
        import urllib.error

        with self._patch_dirs():
            manager = self._make_manager()

            def raise_http_error(*_a, **_kw):
                from email.message import Message

                raise urllib.error.HTTPError(
                    "http://x",
                    500,
                    "Internal",
                    Message(),
                    None,  # type: ignore[arg-type]
                )

            with patch("videos.urllib.request.urlopen", side_effect=raise_http_error):
                with self.assertLogs("videos", level="ERROR") as cm:
                    result = manager._download_video("http://x", "boom.mp4")

        self.assertIsNone(result)
        self.assertTrue(any("HTTP 500" in m for m in cm.output))

    def test_url_error_is_caught_and_cleaned_up(self):
        """URLError triggers a warning and removes the temp file."""
        import urllib.error

        with self._patch_dirs():
            manager = self._make_manager()

            with patch(
                "videos.urllib.request.urlopen",
                side_effect=urllib.error.URLError("no dns"),
            ):
                with self.assertLogs("videos", level="ERROR") as cm:
                    result = manager._download_video("http://x", "dns.mp4")

        self.assertIsNone(result)
        self.assertTrue(any("URL error" in m for m in cm.output))

    def test_timeout_error_is_caught(self):
        """TimeoutError is translated into a timeout log line."""
        with self._patch_dirs():
            manager = self._make_manager()

            with patch(
                "videos.urllib.request.urlopen", side_effect=TimeoutError("slow")
            ):
                with self.assertLogs("videos", level="ERROR") as cm:
                    result = manager._download_video("http://x", "slow.mp4")

        self.assertIsNone(result)
        self.assertTrue(any("Download timeout" in m for m in cm.output))

    def test_generic_exception_is_caught(self):
        """Any other exception is logged and swallowed."""
        with self._patch_dirs():
            manager = self._make_manager()

            with patch(
                "videos.urllib.request.urlopen",
                side_effect=RuntimeError("boom"),
            ):
                with self.assertLogs("videos", level="ERROR") as cm:
                    result = manager._download_video("http://x", "g.mp4")

        self.assertIsNone(result)
        self.assertTrue(any("Failed to download" in m for m in cm.output))


class TestStaticHelpers(unittest.TestCase):
    """Unit tests for the small static helpers on VideosManager."""

    def test_move_file_success(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "src")
            dst = os.path.join(d, "dst")
            with open(src, "w") as f:
                f.write("x")
            self.assertTrue(VideosManager._move_file(src, dst))
            self.assertTrue(os.path.isfile(dst))

    def test_move_file_failure_logs_and_returns_false(self):
        with self.assertLogs("videos", level="ERROR") as cm:
            ok = VideosManager._move_file(
                "/tmp/does-not-exist-abcdef", "/tmp/also-does-not-exist-xyz/target"
            )
        self.assertFalse(ok)
        self.assertTrue(any("Failed to move" in m for m in cm.output))

    def test_cleanup_file_missing_is_silent(self):
        """Cleaning up a missing file must not raise."""
        VideosManager._cleanup_file("/tmp/definitely-missing-xyz")

    def test_cleanup_file_swallows_os_error(self):
        """A permission error during cleanup is swallowed silently."""
        with patch("videos.os.path.isfile", return_value=True):
            with patch("videos.os.remove", side_effect=OSError("denied")):
                # Must not raise.
                VideosManager._cleanup_file("/tmp/any-path")


class TestScanEdgeCases(unittest.TestCase):
    """Edge cases in VideosManager._scan_and_load_all_videos."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.auto_dir = os.path.join(self.temp_dir, "auto")
        self.uploaded_dir = os.path.join(self.temp_dir, "uploaded")
        # Intentionally do NOT create both dirs: we want to exercise the
        # "missing subdir" warning branch.
        os.makedirs(self.auto_dir)
        VideosManager._instance = None

    def tearDown(self):
        shutil.rmtree(self.temp_dir)
        VideosManager._instance = None

    @patch.object(VideosManager, "_download_default_videos")
    @patch.object(VideosManager, "_ensure_all_ts_conversions")
    def test_missing_subdir_logs_warning_and_continues(self, _ensure, _dl):
        """A missing UPLOADED_VIDEO_DIR is skipped with a warning."""
        with _patch_video_dirs(self.auto_dir, self.uploaded_dir):
            # _ensure_subdirs will recreate the missing subdir - stub it out
            # so the warning branch in _scan_and_load_all_videos actually
            # fires.
            with patch.object(VideosManager, "_ensure_subdirs"):
                with self.assertLogs("videos", level="WARNING") as cm:
                    VideosManager()
        self.assertTrue(any("is missing, skipping scan" in m for m in cm.output))


class TestEnsureTsFilePaths(unittest.TestCase):
    """Tests covering the branches inside ensure_ts_file and get_ts_path."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.auto_dir = os.path.join(self.temp_dir, "auto")
        self.uploaded_dir = os.path.join(self.temp_dir, "uploaded")
        os.makedirs(self.auto_dir)
        os.makedirs(self.uploaded_dir)
        VideosManager._instance = None

    def tearDown(self):
        shutil.rmtree(self.temp_dir)
        VideosManager._instance = None

    def _patch_dirs(self):
        return _patch_video_dirs(self.auto_dir, self.uploaded_dir)

    def _make_manager(self):
        with (
            patch.object(VideosManager, "_download_default_videos"),
            patch.object(VideosManager, "_ensure_all_ts_conversions"),
        ):
            return VideosManager()

    def test_ensure_ts_file_returns_as_is_for_ts_source(self):
        """A .ts source is returned unchanged without conversion."""
        ts_path = os.path.join(self.auto_dir, "already.ts")
        with open(ts_path, "w") as f:
            f.write("ts")

        with self._patch_dirs():
            manager = self._make_manager()
            with patch.object(VideosManager, "_convert_to_ts") as mock_convert:
                result = manager.ensure_ts_file(ts_path)
        self.assertEqual(result, ts_path)
        mock_convert.assert_not_called()

    def test_ensure_ts_file_extracts_info_when_source_unknown(self):
        """When the source is not in _videos, codec is probed from the file."""
        mp4_path = os.path.join(self.auto_dir, "fresh.mp4")
        with open(mp4_path, "w") as f:
            f.write("bin")

        with self._patch_dirs():
            manager = self._make_manager()

            info = VideoFileInfo(
                width=640,
                height=480,
                fps=24.0,
                frame_count=240,
                fourcc=ord("a") | (ord("v") << 8) | (ord("c") << 16) | (ord("1") << 24),
            )

            with patch.object(
                VideosManager, "_extract_video_file_info", return_value=info
            ):
                with patch.object(
                    VideosManager, "_convert_to_ts", return_value=True
                ) as mock_convert:
                    with patch.object(VideosManager, "_ensure_ts_metadata"):
                        ts_path = manager.ensure_ts_file(mp4_path)

        self.assertEqual(ts_path, os.path.join(self.auto_dir, "fresh.ts"))
        # Codec was derived from the probe (h264) and passed to the converter.
        mock_convert.assert_called_once()
        _, _, _, codec = mock_convert.call_args.args
        self.assertEqual(codec, "h264")

    def test_ensure_ts_file_returns_none_when_extract_fails(self):
        """When cv2 cannot open the source we log and return None."""
        mp4_path = os.path.join(self.auto_dir, "bad.mp4")
        with open(mp4_path, "w") as f:
            f.write("bin")

        with self._patch_dirs():
            manager = self._make_manager()
            with patch.object(
                VideosManager, "_extract_video_file_info", return_value=None
            ):
                with self.assertLogs("videos", level="WARNING") as cm:
                    result = manager.ensure_ts_file(mp4_path)
        self.assertIsNone(result)
        self.assertTrue(any("Cannot open source video" in m for m in cm.output))

    def test_ensure_ts_file_returns_none_when_conversion_fails(self):
        """A failed _convert_to_ts short-circuits ensure_ts_file."""
        mp4_path = os.path.join(self.auto_dir, "fail.mp4")
        with open(mp4_path, "w") as f:
            f.write("bin")

        with self._patch_dirs():
            manager = self._make_manager()
            info = VideoFileInfo(
                width=1,
                height=1,
                fps=1.0,
                frame_count=1,
                fourcc=ord("a") | (ord("v") << 8) | (ord("c") << 16) | (ord("1") << 24),
            )
            with patch.object(
                VideosManager, "_extract_video_file_info", return_value=info
            ):
                with patch.object(VideosManager, "_convert_to_ts", return_value=False):
                    result = manager.ensure_ts_file(mp4_path)
        self.assertIsNone(result)

    def test_ensure_all_ts_conversions_skips_ts_files(self):
        """_ensure_all_ts_conversions must not convert .ts entries."""
        with self._patch_dirs():
            manager = self._make_manager()
            manager._videos["already.ts"] = Video(
                filename="already.ts",
                width=1,
                height=1,
                fps=1.0,
                frame_count=1,
                codec="h264",
                duration=1.0,
                source="auto",
                path="auto/already.ts",
            )
            manager._video_paths["already.ts"] = os.path.join(
                self.auto_dir, "already.ts"
            )
            with patch.object(VideosManager, "ensure_ts_file") as mock_ensure:
                manager._ensure_all_ts_conversions()
            mock_ensure.assert_not_called()

    def test_ensure_all_ts_conversions_skips_when_path_missing(self):
        """An orphan entry without a path is skipped silently."""
        with self._patch_dirs():
            manager = self._make_manager()
            manager._videos["ghost.mp4"] = Video(
                filename="ghost.mp4",
                width=1,
                height=1,
                fps=1.0,
                frame_count=1,
                codec="h264",
                duration=1.0,
                source="auto",
                path="auto/ghost.mp4",
            )
            # Intentionally do not populate _video_paths for this filename.
            with patch.object(VideosManager, "ensure_ts_file") as mock_ensure:
                manager._ensure_all_ts_conversions()
            mock_ensure.assert_not_called()

    def test_get_ts_path_with_full_path(self):
        """When the caller provides a full path, we trust it."""
        mp4_path = os.path.join(self.auto_dir, "full.mp4")
        with open(mp4_path, "w") as f:
            f.write("bin")

        with self._patch_dirs():
            manager = self._make_manager()
            with patch.object(
                VideosManager, "ensure_ts_file", return_value="/tmp/out.ts"
            ) as mock_ensure:
                result = manager.get_ts_path(mp4_path)
        self.assertEqual(result, "/tmp/out.ts")
        mock_ensure.assert_called_once_with(mp4_path)


class TestConvertToTs(unittest.TestCase):
    """Tests for the GStreamer-based _convert_to_ts helper."""

    def test_unsupported_codec_is_rejected(self):
        with self.assertLogs("videos", level="WARNING") as cm:
            ok = VideosManager._convert_to_ts("/tmp/x.mp4", "/tmp/x.ts", "mp4", "vp9")
        self.assertFalse(ok)
        self.assertTrue(any("unsupported codec" in m for m in cm.output))

    def test_unknown_extension_with_non_raw_codec_is_rejected(self):
        """No demuxer + not a raw elementary stream -> rejection."""
        with self.assertLogs("videos", level="WARNING") as cm:
            ok = VideosManager._convert_to_ts("/tmp/x.xyz", "/tmp/x.ts", "xyz", "h264")
        self.assertFalse(ok)
        self.assertTrue(any("No demuxer configured" in m for m in cm.output))

    def test_raw_stream_extension_goes_through_parser_only(self):
        """Raw elementary streams build a pipeline without a demuxer."""
        with patch("videos.PipelineRunner") as mock_runner_cls:
            runner = MagicMock()
            mock_runner_cls.return_value = runner
            ok = VideosManager._convert_to_ts("/tmp/x.264", "/tmp/x.ts", "264", "h264")
        self.assertTrue(ok)
        # The command must not contain any demuxer element.
        _, kwargs = runner.run.call_args
        cmd = runner.run.call_args.args[0]
        self.assertNotIn("qtdemux", cmd)
        self.assertNotIn("matroskademux", cmd)
        self.assertIn("h264parse", cmd)

    def test_runner_exception_is_caught(self):
        """An exception from PipelineRunner is logged and returns False."""
        with patch("videos.PipelineRunner") as mock_runner_cls:
            runner = MagicMock()
            runner.run.side_effect = RuntimeError("pipeline crashed")
            mock_runner_cls.return_value = runner
            with self.assertLogs("videos", level="ERROR") as cm:
                ok = VideosManager._convert_to_ts(
                    "/tmp/x.mp4", "/tmp/x.ts", "mp4", "h264"
                )
        self.assertFalse(ok)
        self.assertTrue(any("Failed to convert" in m for m in cm.output))


class TestRegisterUploadedVideoFailures(unittest.TestCase):
    """Extra failure branches in VideosManager.register_uploaded_video."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.auto_dir = os.path.join(self.temp_dir, "auto")
        self.uploaded_dir = os.path.join(self.temp_dir, "uploaded")
        os.makedirs(self.auto_dir)
        os.makedirs(self.uploaded_dir)
        VideosManager._instance = None

    def tearDown(self):
        shutil.rmtree(self.temp_dir)
        VideosManager._instance = None

    def _patch_dirs(self):
        return _patch_video_dirs(self.auto_dir, self.uploaded_dir)

    def _make_manager(self):
        with (
            patch.object(VideosManager, "_download_default_videos"),
            patch.object(VideosManager, "_ensure_all_ts_conversions"),
        ):
            return VideosManager()

    def test_move_failure_raises_runtime_error(self):
        """A failed move during registration raises RuntimeError."""
        temp_path = os.path.join(self.temp_dir, ".upload-move.mp4")
        with open(temp_path, "w") as f:
            f.write("x")

        with self._patch_dirs():
            manager = self._make_manager()
            with patch.object(VideosManager, "_move_file", return_value=False):
                with self.assertRaises(RuntimeError) as ctx:
                    manager.register_uploaded_video(temp_path, "x.mp4")
        self.assertIn("Failed to move", str(ctx.exception))

    def test_chmod_failure_is_logged_and_non_fatal(self):
        """An OSError from chmod is logged but doesn't fail the upload."""
        temp_path = os.path.join(self.temp_dir, ".upload-chmod.mp4")
        with open(temp_path, "w") as f:
            f.write("x")

        with self._patch_dirs():
            manager = self._make_manager()
            info = VideoFileInfo(
                width=1,
                height=1,
                fps=1.0,
                frame_count=1,
                fourcc=ord("a") | (ord("v") << 8) | (ord("c") << 16) | (ord("1") << 24),
            )
            with patch.object(
                VideosManager, "_extract_video_file_info", return_value=info
            ):
                # Simulate TS creation by touching the expected file.
                def fake_convert(src, ts_path, *a, **kw):
                    with open(ts_path, "w") as f:
                        f.write("ts")
                    return True

                with patch.object(
                    VideosManager, "_convert_to_ts", side_effect=fake_convert
                ):
                    with patch("videos.os.chmod", side_effect=OSError("denied")):
                        with self.assertLogs("videos", level="WARNING") as cm:
                            original, _ts = manager.register_uploaded_video(
                                temp_path, "chmod.mp4"
                            )

        self.assertEqual(original.filename, "chmod.mp4")
        self.assertTrue(any("Could not set permissions" in m for m in cm.output))

    def test_ts_conversion_failure_rolls_back(self):
        """A failed TS conversion rolls the entry back and cleans artifacts."""
        temp_path = os.path.join(self.temp_dir, ".upload-ts-fail.mp4")
        with open(temp_path, "w") as f:
            f.write("x")

        with self._patch_dirs():
            manager = self._make_manager()
            info = VideoFileInfo(
                width=1,
                height=1,
                fps=1.0,
                frame_count=1,
                fourcc=ord("a") | (ord("v") << 8) | (ord("c") << 16) | (ord("1") << 24),
            )
            with patch.object(
                VideosManager, "_extract_video_file_info", return_value=info
            ):
                # ensure_ts_file returns None -> RuntimeError with rollback.
                with patch.object(VideosManager, "ensure_ts_file", return_value=None):
                    with self.assertRaises(RuntimeError) as ctx:
                        manager.register_uploaded_video(temp_path, "rb.mp4")

        self.assertIn("Failed to create TS companion", str(ctx.exception))
        # Rollback cleaned the in-memory entry and files from disk.
        self.assertNotIn("rb.mp4", manager._videos)
        self.assertFalse(os.path.isfile(os.path.join(self.uploaded_dir, "rb.mp4")))


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
