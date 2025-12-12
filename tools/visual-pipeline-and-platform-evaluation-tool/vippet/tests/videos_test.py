import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from videos import Video, VideosManager, get_videos_manager


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
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_recordings_path = os.environ.get("RECORDINGS_PATH")

    def tearDown(self):
        """Clean up temporary directory and restore environment."""
        shutil.rmtree(self.temp_dir)
        if self.original_recordings_path:
            os.environ["RECORDINGS_PATH"] = self.original_recordings_path
        else:
            os.environ.pop("RECORDINGS_PATH", None)

    def test_videos_manager_invalid_directory(self):
        """Test VideosManager raises RuntimeError for invalid directory."""
        invalid_path = os.path.join(self.temp_dir, "nonexistent")
        with patch("videos.RECORDINGS_PATH", invalid_path):
            with self.assertRaises(RuntimeError) as context:
                VideosManager()
            self.assertIn(
                "does not exist or is not a directory", str(context.exception)
            )

    @patch("videos.RECORDINGS_PATH")
    @patch("cv2.VideoCapture")
    def test_videos_manager_scan_with_video_files(self, mock_videocap, mock_path):
        """Test scanning directory with video files and extracting metadata."""
        mock_path.__str__ = lambda self: self.temp_dir
        mock_path.return_value = self.temp_dir

        # Create dummy video files
        video_file = os.path.join(self.temp_dir, "test.mp4")
        with open(video_file, "w") as f:
            f.write("dummy video content")

        # Mock cv2.VideoCapture
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            3: 1920,  # CAP_PROP_FRAME_WIDTH
            4: 1080,  # CAP_PROP_FRAME_HEIGHT
            5: 30.0,  # CAP_PROP_FPS
            7: 900,  # CAP_PROP_FRAME_COUNT
            6: (ord("a"))
            | (ord("v") << 8)
            | (ord("c") << 16)
            | (ord(" ") << 24),  # CAP_PROP_FOURCC (avc)
        }.get(prop, 0)
        mock_videocap.return_value = mock_cap

        with patch("videos.RECORDINGS_PATH", self.temp_dir):
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

    def test_videos_manager_load_from_json(self):
        """Test loading video metadata from existing JSON file."""
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

        with patch("videos.RECORDINGS_PATH", self.temp_dir):
            manager = VideosManager()
            videos = manager.get_all_videos()

        self.assertEqual(len(videos), 1)
        video = videos["test.mp4"]
        self.assertEqual(video.codec, "h265")
        self.assertEqual(video.width, 1280)
        self.assertEqual(video.height, 720)

    def test_videos_manager_invalid_json(self):
        """Test handling of corrupted JSON metadata file."""
        # Create dummy video file
        video_file = os.path.join(self.temp_dir, "test.mp4")
        with open(video_file, "w") as f:
            f.write("dummy video content")

        # Create invalid JSON metadata
        json_path = os.path.join(self.temp_dir, "test.mp4.json")
        with open(json_path, "w") as f:
            f.write("invalid json content")

        # Should skip the file due to invalid JSON
        with patch("videos.RECORDINGS_PATH", self.temp_dir):
            manager = VideosManager()
            videos = manager.get_all_videos()
        self.assertEqual(len(videos), 0)

    @patch("cv2.VideoCapture")
    def test_videos_manager_unopenable_video(self, mock_videocap):
        """Test handling of video files that cannot be opened."""
        video_file = os.path.join(self.temp_dir, "test.mp4")
        with open(video_file, "w") as f:
            f.write("dummy video content")

        # Mock cv2.VideoCapture to fail opening
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_videocap.return_value = mock_cap

        with patch("videos.RECORDINGS_PATH", self.temp_dir):
            manager = VideosManager()
            videos = manager.get_all_videos()

        self.assertEqual(len(videos), 0)

    @patch("cv2.VideoCapture")
    def test_videos_manager_unsupported_codec(self, mock_videocap):
        """Test handling of video files with unsupported codecs."""
        video_file = os.path.join(self.temp_dir, "test.mp4")
        with open(video_file, "w") as f:
            f.write("dummy video content")

        # Mock cv2.VideoCapture with unsupported codec
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            3: 1920,
            4: 1080,
            5: 30.0,
            7: 900,
            6: (ord("v"))
            | (ord("p") << 8)
            | (ord("8") << 16)
            | (ord("0") << 24),  # vp80
        }.get(prop, 0)
        mock_videocap.return_value = mock_cap

        with patch("videos.RECORDINGS_PATH", self.temp_dir):
            manager = VideosManager()
            videos = manager.get_all_videos()

        self.assertEqual(len(videos), 0)

    @patch("cv2.VideoCapture")
    def test_videos_manager_hevc_codec(self, mock_videocap):
        """Test handling of video files with HEVC/H.265 codec."""
        video_file = os.path.join(self.temp_dir, "test.mp4")
        with open(video_file, "w") as f:
            f.write("dummy video content")

        # Mock cv2.VideoCapture with HEVC codec
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            3: 1920,
            4: 1080,
            5: 30.0,
            7: 900,
            6: (ord("h"))
            | (ord("e") << 8)
            | (ord("v") << 16)
            | (ord("c") << 24),  # hevc
        }.get(prop, 0)
        mock_videocap.return_value = mock_cap

        with patch("videos.RECORDINGS_PATH", self.temp_dir):
            manager = VideosManager()
            videos = manager.get_all_videos()

        self.assertEqual(len(videos), 1)
        video = videos["test.mp4"]
        self.assertEqual(video.codec, "h265")

    def test_videos_manager_skip_non_video_files(self):
        """Test that non-video files are skipped."""
        # Create non-video files
        txt_file = os.path.join(self.temp_dir, "readme.txt")
        with open(txt_file, "w") as f:
            f.write("text content")

        with patch("videos.RECORDINGS_PATH", self.temp_dir):
            manager = VideosManager()
            videos = manager.get_all_videos()

        self.assertEqual(len(videos), 0)

    def test_videos_manager_skip_directories(self):
        """Test that directories are skipped during scanning."""
        # Create a subdirectory
        subdir = os.path.join(self.temp_dir, "subdir")
        os.makedirs(subdir)

        with patch("videos.RECORDINGS_PATH", self.temp_dir):
            manager = VideosManager()
            videos = manager.get_all_videos()

        self.assertEqual(len(videos), 0)

    def test_videos_manager_get_video(self):
        """Test retrieving a specific video by filename."""
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

        with patch("videos.RECORDINGS_PATH", self.temp_dir):
            manager = VideosManager()
            video = manager.get_video("test.mp4")

        self.assertIsNotNone(video)
        assert video is not None  # Type narrowing for type checkers
        self.assertEqual(video.filename, "test.mp4")
        self.assertEqual(video.codec, "h264")

    def test_videos_manager_get_video_not_found(self):
        """Test retrieving a non-existent video returns None."""
        with patch("videos.RECORDINGS_PATH", self.temp_dir):
            manager = VideosManager()
            video = manager.get_video("nonexistent.mp4")

        self.assertIsNone(video)

    @patch("cv2.VideoCapture")
    def test_videos_manager_json_write_failure(self, mock_videocap):
        """Test handling of JSON write failures."""
        video_file = os.path.join(self.temp_dir, "test.mp4")
        with open(video_file, "w") as f:
            f.write("dummy video content")

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            3: 1920,
            4: 1080,
            5: 30.0,
            7: 900,
            6: (ord("a")) | (ord("v") << 8) | (ord("c") << 16) | (ord(" ") << 24),
        }.get(prop, 0)
        mock_videocap.return_value = mock_cap

        # Patch open to simulate write failure for JSON file
        original_open = open

        def mock_open_func(path, *args, **kwargs):
            if path.endswith(".json"):
                raise OSError("Permission denied")
            return original_open(path, *args, **kwargs)

        with patch("videos.RECORDINGS_PATH", self.temp_dir):
            with patch("builtins.open", side_effect=mock_open_func):
                manager = VideosManager()
                videos = manager.get_all_videos()

        # Video should still be in memory even if JSON save failed
        self.assertEqual(len(videos), 1)

    @patch("cv2.VideoCapture")
    def test_videos_manager_zero_fps(self, mock_videocap):
        """Test handling of video with zero FPS."""
        video_file = os.path.join(self.temp_dir, "test.mp4")
        with open(video_file, "w") as f:
            f.write("dummy video content")

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            3: 1920,
            4: 1080,
            5: 0.0,  # Zero FPS
            7: 0,
            6: (ord("a")) | (ord("v") << 8) | (ord("c") << 16) | (ord(" ") << 24),
        }.get(prop, 0)
        mock_videocap.return_value = mock_cap

        with patch("videos.RECORDINGS_PATH", self.temp_dir):
            manager = VideosManager()
            videos = manager.get_all_videos()

        self.assertEqual(len(videos), 1)
        video = videos["test.mp4"]
        self.assertEqual(video.duration, 0.0)

    @patch("cv2.VideoCapture")
    def test_videos_manager_multiple_video_extensions(self, mock_videocap):
        """Test scanning multiple video file extensions."""
        for ext in ["mp4", "mkv", "avi"]:
            video_file = os.path.join(self.temp_dir, f"test.{ext}")
            with open(video_file, "w") as f:
                f.write("dummy video content")

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            3: 1920,
            4: 1080,
            5: 30.0,
            7: 900,
            6: (ord("a")) | (ord("v") << 8) | (ord("c") << 16) | (ord(" ") << 24),
        }.get(prop, 0)
        mock_videocap.return_value = mock_cap

        with patch("videos.RECORDINGS_PATH", self.temp_dir):
            manager = VideosManager()
            videos = manager.get_all_videos()

        self.assertEqual(len(videos), 3)
        self.assertIn("test.mp4", videos)
        self.assertIn("test.mkv", videos)
        self.assertIn("test.avi", videos)


class TestGetVideosManager(unittest.TestCase):
    def setUp(self):
        """Create temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_recordings_path = os.environ.get("RECORDINGS_PATH")

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir)
        if self.original_recordings_path:
            os.environ["RECORDINGS_PATH"] = self.original_recordings_path
        else:
            os.environ.pop("RECORDINGS_PATH", None)

    def test_get_videos_manager_singleton(self):
        """Test that get_videos_manager returns the same instance."""
        with patch("videos.RECORDINGS_PATH", self.temp_dir):
            with patch("videos._videos_manager_instance", None):
                manager1 = get_videos_manager()
                manager2 = get_videos_manager()
                self.assertIs(manager1, manager2)

    @patch("videos.VideosManager")
    @patch("sys.exit")
    def test_get_videos_manager_initialization_failure(self, mock_exit, mock_vm):
        """Test that initialization failure causes sys.exit."""
        mock_vm.side_effect = Exception("Initialization failed")

        with patch("videos._videos_manager_instance", None):
            get_videos_manager()
            mock_exit.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
