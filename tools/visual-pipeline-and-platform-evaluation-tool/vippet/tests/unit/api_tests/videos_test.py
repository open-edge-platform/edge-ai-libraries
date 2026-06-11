import io
import os
import shutil
import tempfile
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

import api.routes.videos as videos_route
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
        source="auto",
        path=None,
    ):
        """Build a lightweight mock matching the internal videos.Video shape.

        ``source`` must be a literal "auto"/"uploaded" because the route
        coerces it to the ``schemas.VideoSource`` enum. ``path`` defaults
        to ``<source>/<filename>`` to mirror what VideosManager produces.
        """
        v = MagicMock()
        v.filename = filename
        v.width = width
        v.height = height
        v.fps = fps
        v.frame_count = frame_count
        v.codec = codec
        v.duration = duration
        v.source = source
        v.path = path if path is not None else f"{source}/{filename}"
        return v

    def test_get_videos_returns_list(self):
        mock_videos = {
            "video1.mp4": self._make_video(
                "video1.mp4", 1920, 1080, 30.0, 300, "h264", 10.0
            ),
            "video2.mkv": self._make_video(
                "video2.mkv",
                1280,
                720,
                25.0,
                250,
                "h265",
                10.0,
                source="uploaded",
            ),
        }
        with patch("api.routes.videos.VideosManager") as mock_videos_manager_cls:
            mock_manager_instance = MagicMock()
            mock_manager_instance.get_all_videos.return_value = mock_videos
            mock_videos_manager_cls.return_value = mock_manager_instance

            response = self.client.get("/videos")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIsInstance(data, list)
            self.assertEqual(len(data), 2)
            # Order from dict iteration is insertion order (Python 3.7+).
            self.assertEqual(data[0]["filename"], "video1.mp4")
            self.assertEqual(data[0]["width"], 1920)
            self.assertEqual(data[0]["height"], 1080)
            self.assertEqual(data[0]["fps"], 30.0)
            self.assertEqual(data[0]["frame_count"], 300)
            self.assertEqual(data[0]["codec"], "h264")
            self.assertEqual(data[0]["duration"], 10.0)
            self.assertEqual(data[0]["source"], "auto")
            self.assertEqual(data[0]["path"], "auto/video1.mp4")
            # Second entry carries the uploaded source.
            self.assertEqual(data[1]["source"], "uploaded")
            self.assertEqual(data[1]["path"], "uploaded/video2.mkv")

    def test_get_videos_empty_list(self):
        with patch("api.routes.videos.VideosManager") as mock_videos_manager_cls:
            mock_manager_instance = MagicMock()
            mock_manager_instance.get_all_videos.return_value = {}
            mock_videos_manager_cls.return_value = mock_manager_instance

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
        with patch("api.routes.videos.VideosManager") as mock_videos_manager_cls:
            mock_manager_instance = MagicMock()
            mock_manager_instance.get_all_videos.return_value = mock_videos
            mock_videos_manager_cls.return_value = mock_manager_instance

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
            self.assertIsInstance(video["source"], str)
            self.assertIsInstance(video["path"], str)

    def test_get_videos_runtime_error_returns_500(self):
        """Unexpected errors from VideosManager are surfaced as HTTP 500."""
        with patch("api.routes.videos.VideosManager") as mock_videos_manager_cls:
            mock_videos_manager_cls.side_effect = RuntimeError("boom")

            response = self.client.get("/videos")
            self.assertEqual(response.status_code, 500)
            body = response.json()
            self.assertIn("message", body)

    def test_check_video_input_exists_true(self):
        """check-video-input-exists reports presence from VideosManager."""
        with patch("api.routes.videos.VideosManager") as mock_videos_manager_cls:
            mock_manager_instance = MagicMock()
            mock_manager_instance.filename_exists.return_value = True
            mock_videos_manager_cls.return_value = mock_manager_instance

            response = self.client.get(
                "/videos/check-video-input-exists",
                params={"filename": "clip.mp4"},
            )
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["exists"], True)
            self.assertEqual(body["filename"], "clip.mp4")
            mock_manager_instance.filename_exists.assert_called_once_with("clip.mp4")

    def test_check_video_input_exists_false(self):
        """check-video-input-exists returns False for unknown filenames."""
        with patch("api.routes.videos.VideosManager") as mock_videos_manager_cls:
            mock_manager_instance = MagicMock()
            mock_manager_instance.filename_exists.return_value = False
            mock_videos_manager_cls.return_value = mock_manager_instance

            response = self.client.get(
                "/videos/check-video-input-exists",
                params={"filename": "missing.mp4"},
            )
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["exists"], False)
            self.assertEqual(body["filename"], "missing.mp4")


class TestEnvParsingHelpers(unittest.TestCase):
    """Unit tests for the small env-variable helpers in the route module."""

    def test_parse_int_env_missing_returns_default(self):
        """Absent env var falls through to the supplied default."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("__VIPPET_TEST_INT__", None)
            value = videos_route._parse_int_env("__VIPPET_TEST_INT__", 42)
            self.assertEqual(value, 42)

    def test_parse_int_env_empty_returns_default(self):
        """Empty/whitespace env var falls through to the default."""
        with patch.dict(os.environ, {"__VIPPET_TEST_INT__": "   "}):
            value = videos_route._parse_int_env("__VIPPET_TEST_INT__", 7)
            self.assertEqual(value, 7)

    def test_parse_int_env_valid_integer(self):
        """A well-formed integer is returned as-is."""
        with patch.dict(os.environ, {"__VIPPET_TEST_INT__": "123"}):
            value = videos_route._parse_int_env("__VIPPET_TEST_INT__", 0)
            self.assertEqual(value, 123)

    def test_parse_int_env_invalid_returns_default_and_warns(self):
        """A non-integer value logs a warning and falls back to the default."""
        with patch.dict(os.environ, {"__VIPPET_TEST_INT__": "not-a-number"}):
            with self.assertLogs("api.routes.videos", level="WARNING") as cm:
                value = videos_route._parse_int_env("__VIPPET_TEST_INT__", 99)
        self.assertEqual(value, 99)
        self.assertTrue(any("Invalid integer" in msg for msg in cm.output))

    def test_parse_csv_env_strips_and_lowercases(self):
        """CSV parsing trims whitespace, lowers case and drops empty entries."""
        with patch.dict(os.environ, {"__VIPPET_TEST_CSV__": " A ,b, ,C"}):
            tokens = videos_route._parse_csv_env("__VIPPET_TEST_CSV__", "x")
            self.assertEqual(tokens, ["a", "b", "c"])

    def test_parse_csv_env_uses_default_when_missing(self):
        """Missing env var falls through to the comma-separated default."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("__VIPPET_TEST_CSV__", None)
            tokens = videos_route._parse_csv_env("__VIPPET_TEST_CSV__", "x,Y")
            self.assertEqual(tokens, ["x", "y"])


class TestSanitiseFilename(unittest.TestCase):
    """Unit tests for the filename sanitiser used by the upload endpoint."""

    def test_none_is_rejected(self):
        self.assertIsNone(videos_route._sanitise_filename(None))

    def test_empty_string_is_rejected(self):
        self.assertIsNone(videos_route._sanitise_filename(""))

    def test_whitespace_only_is_rejected(self):
        self.assertIsNone(videos_route._sanitise_filename("   "))

    def test_dot_entries_are_rejected(self):
        self.assertIsNone(videos_route._sanitise_filename("."))
        self.assertIsNone(videos_route._sanitise_filename(".."))

    def test_unsafe_characters_are_rejected(self):
        self.assertIsNone(videos_route._sanitise_filename("clip$.mp4"))
        self.assertIsNone(videos_route._sanitise_filename("clip\nname.mp4"))

    def test_basename_is_extracted_from_path(self):
        """Any directory component is stripped before validation."""
        self.assertEqual(
            videos_route._sanitise_filename("/tmp/malicious/clip.mp4"),
            "clip.mp4",
        )
        self.assertEqual(
            videos_route._sanitise_filename("../../etc/passwd"),
            "passwd",
        )

    def test_safe_name_passes_through(self):
        self.assertEqual(
            videos_route._sanitise_filename("My Clip_01-a.mp4"),
            "My Clip_01-a.mp4",
        )


class TestProbeContainerAndCodec(unittest.TestCase):
    """Unit tests for _probe_container_and_codec()."""

    def test_returns_none_when_cv2_cannot_open(self):
        """When VideosManager._extract_video_file_info returns None, so do we."""
        with patch(
            "api.routes.videos.VideosManager._extract_video_file_info",
            return_value=None,
        ):
            container, codec = videos_route._probe_container_and_codec("/tmp/x.mp4")
        self.assertIsNone(container)
        self.assertIsNone(codec)

    def test_returns_container_and_codec_for_known_extension(self):
        """Known extensions are mapped to their container tag."""
        info = MagicMock()
        info.codec = "h264"
        with patch(
            "api.routes.videos.VideosManager._extract_video_file_info",
            return_value=info,
        ):
            container, codec = videos_route._probe_container_and_codec("/tmp/x.mp4")
        self.assertEqual(container, "mp4")
        self.assertEqual(codec, "h264")

    def test_returns_none_codec_when_fourcc_is_empty(self):
        """An empty codec string collapses to None so the caller can reject."""
        info = MagicMock()
        info.codec = ""
        with patch(
            "api.routes.videos.VideosManager._extract_video_file_info",
            return_value=info,
        ):
            container, codec = videos_route._probe_container_and_codec("/tmp/x.mp4")
        self.assertEqual(container, "mp4")
        self.assertIsNone(codec)

    def test_unknown_extension_maps_to_none_container(self):
        """Extensions that are not in the allow-list map to None container."""
        info = MagicMock()
        info.codec = "h264"
        with patch(
            "api.routes.videos.VideosManager._extract_video_file_info",
            return_value=info,
        ):
            container, codec = videos_route._probe_container_and_codec("/tmp/clip.xyz")
        self.assertIsNone(container)
        self.assertEqual(codec, "h264")


def _make_probe(container, codec):
    """Helper: build a patch target for _probe_container_and_codec."""

    def _probe(_path):
        return container, codec

    return _probe


class TestUploadVideoEndpoint(unittest.TestCase):
    """End-to-end tests for POST /videos/upload covering every branch."""

    @classmethod
    def setUpClass(cls):
        app = FastAPI()
        app.include_router(videos_router, prefix="/videos")
        cls.client = TestClient(app)

    def setUp(self):
        """Redirect UPLOADED_VIDEO_DIR to an isolated temp directory.

        The route writes the streamed payload into a temp file inside
        UPLOADED_VIDEO_DIR so the final shutil.move is a same-filesystem
        rename. Tests must therefore point that constant at a directory
        they can create and clean up.
        """
        self.upload_dir = tempfile.mkdtemp(prefix="vippet-upload-test-")
        self._upload_dir_patcher = patch(
            "api.routes.videos.UPLOADED_VIDEO_DIR", self.upload_dir
        )
        self._upload_dir_patcher.start()

    def tearDown(self):
        self._upload_dir_patcher.stop()
        shutil.rmtree(self.upload_dir, ignore_errors=True)

    def _post(
        self, filename, payload=b"data", content_type="video/mp4", extra_headers=None
    ):
        """Helper to POST a multipart upload. Returns the response."""
        files = {"file": (filename, io.BytesIO(payload), content_type)}
        headers = extra_headers or {}
        return self.client.post("/videos/upload", files=files, headers=headers)

    # -------- Stage 1: pre-write validation ---------------------------------

    def test_missing_filename_rejected(self):
        """An empty filename is rejected with missing_filename."""
        with patch("api.routes.videos.VideosManager") as mock_cls:
            mock_cls.return_value = MagicMock()
            # Force _sanitise_filename to return None by using an unsafe name.
            response = self._post("bad$name.mp4")
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"], "missing_filename")
        self.assertIn("detail", body)

    def test_unsupported_extension_rejected(self):
        """A disallowed extension is rejected with unsupported_extension."""
        with patch("api.routes.videos.VideosManager") as mock_cls:
            mock_cls.return_value = MagicMock()
            response = self._post("clip.webm")
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"], "unsupported_extension")
        self.assertEqual(body["found"], "webm")
        self.assertIsInstance(body["allowed"], list)

    def test_no_extension_rejected_as_unsupported(self):
        """A filename without an extension is rejected."""
        with patch("api.routes.videos.VideosManager") as mock_cls:
            mock_cls.return_value = MagicMock()
            response = self._post("noext")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "unsupported_extension")

    def test_duplicate_filename_rejected(self):
        """A filename already known to VideosManager is rejected."""
        mock_manager = MagicMock()
        mock_manager.filename_exists.return_value = True
        with patch("api.routes.videos.VideosManager", return_value=mock_manager):
            response = self._post("existing.mp4", payload=b"1234")
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"], "file_exists")
        self.assertEqual(body["found"], "existing.mp4")

    # -------- Stage 2: streaming size enforcement ---------------------------

    def test_file_too_large_mid_stream(self):
        """Bytes streamed past the per-chunk size limit produce file_too_large.

        The route no longer exposes a Content-Length header parameter (to keep
        it out of the OpenAPI schema - browsers are forbidden from setting
        Content-Length), so size enforcement happens exclusively mid-stream.
        An 8-byte payload with the limit lowered to 4 must be rejected.
        """
        mock_manager = MagicMock()
        mock_manager.filename_exists.return_value = False

        with patch("api.routes.videos.UPLOAD_MAX_SIZE_BYTES", 4):
            with patch("api.routes.videos.VideosManager", return_value=mock_manager):
                response = self._post("big.mp4", payload=b"12345678")

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"], "file_too_large")

    # -------- Stage 3: post-write cv2 validation ----------------------------

    def test_invalid_video_rejected(self):
        """When cv2 cannot open the file, return invalid_video."""
        mock_manager = MagicMock()
        mock_manager.filename_exists.return_value = False
        with patch("api.routes.videos.VideosManager", return_value=mock_manager):
            with patch(
                "api.routes.videos._probe_container_and_codec",
                side_effect=_make_probe(None, None),
            ):
                response = self._post("clip.mp4", payload=b"1234")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "invalid_video")

    def test_unsupported_container_rejected(self):
        """Containers not in the allow-list are rejected."""
        mock_manager = MagicMock()
        mock_manager.filename_exists.return_value = False
        with patch("api.routes.videos.VideosManager", return_value=mock_manager):
            with patch(
                "api.routes.videos._probe_container_and_codec",
                side_effect=_make_probe("flv", "h264"),
            ):
                response = self._post("clip.mp4", payload=b"1234")
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"], "unsupported_container")
        self.assertEqual(body["found"], "flv")

    def test_unsupported_codec_rejected(self):
        """Codecs not in the allow-list are rejected."""
        mock_manager = MagicMock()
        mock_manager.filename_exists.return_value = False
        with patch("api.routes.videos.VideosManager", return_value=mock_manager):
            with patch(
                "api.routes.videos._probe_container_and_codec",
                side_effect=_make_probe("mp4", "vp9"),
            ):
                response = self._post("clip.mp4", payload=b"1234")
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"], "unsupported_codec")
        self.assertEqual(body["found"], "vp9")

    # -------- Stage 4: successful commit and rollback -----------------------

    def test_successful_upload_returns_201(self):
        """A valid upload returns 201 with the resulting Video payload."""
        mock_manager = MagicMock()
        mock_manager.filename_exists.return_value = False

        # Build a domain Video mock that _domain_to_schema_video can read.
        domain_video = MagicMock()
        domain_video.filename = "clip.mp4"
        domain_video.width = 1920
        domain_video.height = 1080
        domain_video.fps = 30.0
        domain_video.frame_count = 300
        domain_video.codec = "h264"
        domain_video.duration = 10.0
        domain_video.source = "uploaded"
        domain_video.path = "uploaded/clip.mp4"

        mock_manager.register_uploaded_video.return_value = (domain_video, None)

        with patch("api.routes.videos.VideosManager", return_value=mock_manager):
            with patch(
                "api.routes.videos._probe_container_and_codec",
                side_effect=_make_probe("mp4", "h264"),
            ):
                response = self._post("clip.mp4", payload=b"1234")

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["filename"], "clip.mp4")
        self.assertEqual(body["source"], "uploaded")
        self.assertEqual(body["path"], "uploaded/clip.mp4")
        mock_manager.register_uploaded_video.assert_called_once()

    def test_register_runtime_error_returns_500(self):
        """A RuntimeError during register_uploaded_video becomes a 500."""
        mock_manager = MagicMock()
        mock_manager.filename_exists.return_value = False
        mock_manager.register_uploaded_video.side_effect = RuntimeError("boom")

        with patch("api.routes.videos.VideosManager", return_value=mock_manager):
            with patch(
                "api.routes.videos._probe_container_and_codec",
                side_effect=_make_probe("mp4", "h264"),
            ):
                response = self._post("clip.mp4", payload=b"1234")

        self.assertEqual(response.status_code, 500)
        body = response.json()
        self.assertIn("message", body)
        self.assertIn("boom", body["message"])

    def test_unexpected_exception_returns_500(self):
        """An unexpected exception during upload is logged and becomes a 500."""
        mock_manager = MagicMock()
        mock_manager.filename_exists.return_value = False

        with patch("api.routes.videos.VideosManager", return_value=mock_manager):
            with patch(
                "api.routes.videos._probe_container_and_codec",
                side_effect=RuntimeError("probe crashed"),
            ):
                response = self._post("clip.mp4", payload=b"1234")

        self.assertEqual(response.status_code, 500)
        body = response.json()
        self.assertIn("message", body)

    def test_temp_file_removed_after_rejection(self):
        """The temp file is removed when validation rejects the upload."""
        mock_manager = MagicMock()
        mock_manager.filename_exists.return_value = False

        created_temps: list[str] = []
        real_mkstemp = videos_route.tempfile.mkstemp

        def tracking_mkstemp(*args, **kwargs):
            fd, path = real_mkstemp(*args, **kwargs)
            created_temps.append(path)
            return fd, path

        with patch("api.routes.videos.VideosManager", return_value=mock_manager):
            with patch(
                "api.routes.videos.tempfile.mkstemp", side_effect=tracking_mkstemp
            ):
                with patch(
                    "api.routes.videos._probe_container_and_codec",
                    side_effect=_make_probe(None, None),
                ):
                    response = self._post("clip.mp4", payload=b"1234")

        self.assertEqual(response.status_code, 422)
        # Every temp file created must have been cleaned up.
        for path in created_temps:
            self.assertFalse(
                os.path.isfile(path),
                f"Temp file {path} was not removed after rejection",
            )

    def test_temp_file_cleanup_swallows_os_error(self):
        """An OSError during best-effort temp cleanup must not propagate."""
        mock_manager = MagicMock()
        mock_manager.filename_exists.return_value = False

        with patch("api.routes.videos.VideosManager", return_value=mock_manager):
            with patch(
                "api.routes.videos._probe_container_and_codec",
                side_effect=_make_probe(None, None),
            ):
                with patch(
                    "api.routes.videos.os.remove",
                    side_effect=OSError("denied"),
                ):
                    response = self._post("clip.mp4", payload=b"1234")

        # Validation still fails with 422; the cleanup error is swallowed.
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "invalid_video")


if __name__ == "__main__":
    unittest.main()
