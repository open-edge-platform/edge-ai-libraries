import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api.routes.videos import router as videos_router


class TestVideosAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = FastAPI()
        app.include_router(videos_router, prefix="/videos")
        cls.client = TestClient(app)

    @staticmethod
    def _make_video(
        filename,
        width,
        height,
        fps,
        frame_count,
        codec,
        duration,
    ):
        v = MagicMock()
        v.filename = filename
        v.width = width
        v.height = height
        v.fps = fps
        v.frame_count = frame_count
        v.codec = codec
        v.duration = duration
        return v

    def test_get_videos_returns_list(self):
        mock_videos = {
            "video1.mp4": self._make_video(
                "video1.mp4", 1920, 1080, 30.0, 300, "h264", 10.0
            ),
            "video2.mkv": self._make_video(
                "video2.mkv", 1280, 720, 25.0, 250, "h265", 10.0
            ),
        }
        with patch("api.routes.videos.get_videos_manager") as mock_get_manager:
            mock_manager_instance = mock_get_manager.return_value
            mock_manager_instance.get_all_videos.return_value = mock_videos
            response = self.client.get("/videos")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIsInstance(data, list)
            self.assertEqual(len(data), 2)
            self.assertEqual(data[0]["filename"], "video1.mp4")
            self.assertEqual(data[0]["width"], 1920)
            self.assertEqual(data[0]["height"], 1080)
            self.assertEqual(data[0]["fps"], 30.0)
            self.assertEqual(data[0]["frame_count"], 300)
            self.assertEqual(data[0]["codec"], "h264")
            self.assertEqual(data[0]["duration"], 10.0)

    def test_get_videos_empty_list(self):
        with patch("api.routes.videos.get_videos_manager") as mock_get_manager:
            mock_manager_instance = mock_get_manager.return_value
            mock_manager_instance.get_all_videos.return_value = {}
            response = self.client.get("/videos")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data, [])

    def test_get_videos_field_types(self):
        mock_videos = {
            "sample.mp4": self._make_video(
                "sample.mp4", 640, 480, 24.0, 240, "h264", 10.0
            ),
        }
        with patch("api.routes.videos.get_videos_manager") as mock_get_manager:
            mock_manager_instance = mock_get_manager.return_value
            mock_manager_instance.get_all_videos.return_value = mock_videos
            response = self.client.get("/videos")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            video = data[0]
            self.assertIsInstance(video["filename"], str)
            self.assertIsInstance(video["width"], int)
            self.assertIsInstance(video["height"], int)
            self.assertIsInstance(video["fps"], float)
            self.assertIsInstance(video["frame_count"], int)
            self.assertIsInstance(video["codec"], str)
            self.assertIsInstance(video["duration"], float)


if __name__ == "__main__":
    unittest.main()
