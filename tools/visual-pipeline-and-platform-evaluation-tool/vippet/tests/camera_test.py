import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch, MagicMock

from api.api_schemas import CameraType, USBCameraDetails, NetworkCameraDetails
from camera import (
    USBCameraDiscovery,
    ONVIFCameraDiscovery,
    ONVIFProfile,
    _score_capture_candidate,
    _select_best_from_v4l2_formats,
    _select_best_profile,
)
from api.api_schemas import (
    V4L2Format,
    V4L2FormatSize,
    CameraProfileInfo,
)


class TestScoringFunctions(unittest.TestCase):
    """Unit tests for the scoring helper functions."""

    def test_score_capture_candidate_h264_1080p_30fps(self):
        """H264 at 1080p 30fps should score high."""
        score = _score_capture_candidate("H264", 1920, 1080, 30.0)
        # fps_score = 1.0 * 0.3 = 0.3
        # resolution_score = 1.0 * 0.3 = 0.3
        # format_pref = 1.0 * 0.4 = 0.4
        # total = 1.0
        self.assertAlmostEqual(score, 1.0, places=2)

    def test_score_capture_candidate_mjpg_720p_15fps(self):
        """MJPG at 720p 15fps should score lower than H264."""
        score = _score_capture_candidate("MJPG", 1280, 720, 15.0)
        # fps_score = 0.5 * 0.3 = 0.15
        # resolution_score = (1280*720)/(1920*1080) * 0.3 ~ 0.133
        # format_pref = 0.7 * 0.4 = 0.28
        self.assertGreater(score, 0.5)
        self.assertLess(score, 0.7)

    def test_score_capture_candidate_yuyv_low_fps(self):
        """YUYV at low fps should score low."""
        score = _score_capture_candidate("YUYV", 640, 480, 5.0)
        self.assertLess(score, 0.4)

    def test_select_best_from_v4l2_formats_empty(self):
        """Empty formats list should return None."""
        result = _select_best_from_v4l2_formats([])
        self.assertIsNone(result)

    def test_select_best_from_v4l2_formats_single_format(self):
        """Single format should be selected."""
        formats = [
            V4L2Format(
                fourcc="MJPG",
                sizes=[V4L2FormatSize(width=1920, height=1080, fps_list=[30.0])],
            )
        ]
        result = _select_best_from_v4l2_formats(formats)
        self.assertIsNotNone(result)
        assert result is not None  # Type narrowing for static analysis
        self.assertEqual(result.fourcc, "MJPG")
        self.assertEqual(result.width, 1920)
        self.assertEqual(result.height, 1080)
        self.assertEqual(result.fps, 30.0)

    def test_select_best_from_v4l2_formats_prefers_h264(self):
        """H264 should be preferred over MJPG at same resolution and fps."""
        formats = [
            V4L2Format(
                fourcc="MJPG",
                sizes=[V4L2FormatSize(width=1920, height=1080, fps_list=[30.0])],
            ),
            V4L2Format(
                fourcc="H264",
                sizes=[V4L2FormatSize(width=1920, height=1080, fps_list=[30.0])],
            ),
        ]
        result = _select_best_from_v4l2_formats(formats)
        self.assertIsNotNone(result)
        assert result is not None  # Type narrowing for static analysis
        self.assertEqual(result.fourcc, "H264")

    def test_select_best_from_v4l2_formats_prefers_acceptable_fps(self):
        """Should prefer formats with fps >= 15 over higher scoring low fps."""
        formats = [
            V4L2Format(
                fourcc="H264",
                sizes=[V4L2FormatSize(width=1920, height=1080, fps_list=[5.0])],
            ),
            V4L2Format(
                fourcc="MJPG",
                sizes=[V4L2FormatSize(width=1280, height=720, fps_list=[30.0])],
            ),
        ]
        result = _select_best_from_v4l2_formats(formats)
        self.assertIsNotNone(result)
        assert result is not None  # Type narrowing for static analysis
        # MJPG at 30fps should be preferred over H264 at 5fps
        self.assertEqual(result.fourcc, "MJPG")
        self.assertEqual(result.fps, 30.0)

    def test_select_best_profile_empty(self):
        """Empty profiles list should return None."""
        result = _select_best_profile([])
        self.assertIsNone(result)

    def test_select_best_profile_skips_no_rtsp_url(self):
        """Profiles without rtsp_url should be skipped."""
        profiles = [
            CameraProfileInfo(
                name="Profile1",
                rtsp_url="",
                resolution="1920x1080",
                encoding="H264",
                framerate=30,
                bitrate=4096,
            )
        ]
        result = _select_best_profile(profiles)
        self.assertIsNone(result)

    def test_select_best_profile_selects_best(self):
        """Should select best profile based on scoring."""
        profiles = [
            CameraProfileInfo(
                name="LowRes",
                rtsp_url="rtsp://192.168.1.100/low",
                resolution="640x480",
                encoding="MJPEG",
                framerate=15,
                bitrate=1024,
            ),
            CameraProfileInfo(
                name="HighRes",
                rtsp_url="rtsp://192.168.1.100/high",
                resolution="1920x1080",
                encoding="H264",
                framerate=30,
                bitrate=4096,
            ),
        ]
        result = _select_best_profile(profiles)
        self.assertIsNotNone(result)
        assert result is not None  # Type narrowing for static analysis
        self.assertEqual(result.name, "HighRes")


class TestUSBCameraDiscovery(unittest.TestCase):
    """
    Unit tests for USBCameraDiscovery.

    The tests focus on:
      * singleton pattern implementation,
      * USB camera discovery using v4l2-ctl,
      * video capture capability verification,
      * V4L2 format parsing,
      * error handling for missing tools and timeouts.
    """

    def setUp(self):
        """Reset singleton state before each test."""
        USBCameraDiscovery._instance = None

    def tearDown(self):
        """Reset singleton state after each test."""
        USBCameraDiscovery._instance = None

    def test_singleton_returns_same_instance(self):
        """USBCameraDiscovery should return the same instance on multiple calls."""
        instance1 = USBCameraDiscovery()
        instance2 = USBCameraDiscovery()
        self.assertIs(instance1, instance2)

    def test_singleton_only_initializes_once(self):
        """Multiple calls should not re-initialize the singleton."""
        instance1 = USBCameraDiscovery()
        self.assertTrue(instance1.initialized)
        instance2 = USBCameraDiscovery()
        self.assertIs(instance1, instance2)

    def test_parse_formats_ext_output_single_format(self):
        """_parse_formats_ext_output should parse single format correctly."""
        output = """ioctl: VIDIOC_ENUM_FMT
    Type: Video Capture

    [0]: 'MJPG' (Motion-JPEG, compressed)
        Size: Discrete 1920x1080
            Interval: Discrete 0.033s (30.000 fps)
        Size: Discrete 1280x720
            Interval: Discrete 0.033s (30.000 fps)
"""
        formats = USBCameraDiscovery._parse_formats_ext_output(output)

        self.assertEqual(len(formats), 1)
        self.assertEqual(formats[0].fourcc, "MJPG")
        self.assertEqual(len(formats[0].sizes), 2)
        self.assertEqual(formats[0].sizes[0].width, 1920)
        self.assertEqual(formats[0].sizes[0].height, 1080)
        self.assertIn(30.0, formats[0].sizes[0].fps_list)

    def test_parse_formats_ext_output_multiple_formats(self):
        """_parse_formats_ext_output should parse multiple formats correctly."""
        output = """ioctl: VIDIOC_ENUM_FMT
    Type: Video Capture

    [0]: 'MJPG' (Motion-JPEG)
        Size: Discrete 1920x1080
            Interval: Discrete 0.033s (30.000 fps)

    [1]: 'YUYV' (YUYV 4:2:2)
        Size: Discrete 640x480
            Interval: Discrete 0.033s (30.000 fps)
            Interval: Discrete 0.067s (15.000 fps)
"""
        formats = USBCameraDiscovery._parse_formats_ext_output(output)

        self.assertEqual(len(formats), 2)
        self.assertEqual(formats[0].fourcc, "MJPG")
        self.assertEqual(formats[1].fourcc, "YUYV")
        self.assertEqual(len(formats[1].sizes[0].fps_list), 2)

    def test_parse_formats_ext_output_empty(self):
        """_parse_formats_ext_output should return empty list for empty output."""
        formats = USBCameraDiscovery._parse_formats_ext_output("")
        self.assertEqual(formats, [])

    @patch("camera.subprocess.run")
    def test_parse_v4l2_formats_success(self, mock_run):
        """_parse_v4l2_formats should call v4l2-ctl and parse output."""
        discovery = USBCameraDiscovery()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = """[0]: 'MJPG' (Motion-JPEG)
        Size: Discrete 1920x1080
            Interval: Discrete 0.033s (30.000 fps)
"""
        mock_run.return_value = mock_result

        formats = discovery._parse_v4l2_formats("/dev/video0")

        self.assertEqual(len(formats), 1)
        mock_run.assert_called_once_with(
            ["v4l2-ctl", "--device", "/dev/video0", "--list-formats-ext"],
            capture_output=True,
            text=True,
            timeout=5,
        )

    @patch("camera.subprocess.run")
    def test_parse_v4l2_formats_failure(self, mock_run):
        """_parse_v4l2_formats should return empty list on failure."""
        discovery = USBCameraDiscovery()

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        formats = discovery._parse_v4l2_formats("/dev/video0")
        self.assertEqual(formats, [])

    @patch("camera.subprocess.run")
    def test_parse_v4l2_formats_timeout(self, mock_run):
        """_parse_v4l2_formats should return empty list on timeout."""
        discovery = USBCameraDiscovery()
        mock_run.side_effect = subprocess.TimeoutExpired("v4l2-ctl", 5)

        formats = discovery._parse_v4l2_formats("/dev/video0")
        self.assertEqual(formats, [])

    @patch("camera.subprocess.run")
    def test_can_capture_video_returns_true_for_capture_device(self, mock_run):
        """_can_capture_video should return True for devices with Video Capture capability."""
        discovery = USBCameraDiscovery()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = """Driver Info:
        Driver name      : uvcvideo
        Card type        : Integrated Camera
        Bus info         : usb-0000:00:14.0-8
Device Caps      : 0x84a00001
        Video Capture
        Metadata Capture
        Streaming"""
        mock_run.return_value = mock_result

        can_capture = discovery._can_capture_video("/dev/video0")

        self.assertTrue(can_capture)

    @patch("camera.subprocess.run")
    def test_can_capture_video_returns_false_for_metadata_only(self, mock_run):
        """_can_capture_video should return False for metadata-only devices."""
        discovery = USBCameraDiscovery()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = """Driver Info:
        Driver name      : uvcvideo
        Card type        : Integrated Camera: IR Camera
        Bus info         : usb-0000:00:14.0-8
Device Caps      : 0x84a00000
        Metadata Capture
        Streaming"""
        mock_run.return_value = mock_result

        can_capture = discovery._can_capture_video("/dev/video1")

        self.assertFalse(can_capture)

    @patch("camera.subprocess.run")
    def test_can_capture_video_handles_timeout(self, mock_run):
        """_can_capture_video should handle timeout gracefully."""
        discovery = USBCameraDiscovery()

        mock_run.side_effect = subprocess.TimeoutExpired("v4l2-ctl", 3)

        can_capture = discovery._can_capture_video("/dev/video0")

        self.assertFalse(can_capture)

    @patch("camera.subprocess.run")
    def test_can_capture_video_handles_missing_tool(self, mock_run):
        """_can_capture_video should handle missing v4l2-ctl."""
        discovery = USBCameraDiscovery()

        mock_run.side_effect = FileNotFoundError()

        can_capture = discovery._can_capture_video("/dev/video0")

        self.assertFalse(can_capture)

    @patch("camera.subprocess.run")
    def test_discover_cameras_returns_valid_cameras_with_best_capture(self, mock_run):
        """discover_cameras should return cameras with best_capture from V4L2 formats."""
        discovery = USBCameraDiscovery()

        # Mock v4l2-ctl --list-devices
        list_devices_result = MagicMock()
        list_devices_result.returncode = 0
        list_devices_result.stdout = """Integrated Camera (usb-0000:00:14.0-8):
        /dev/video0
        /dev/video1
"""

        # Mock v4l2-ctl --all for capability check
        video0_caps = MagicMock()
        video0_caps.returncode = 0
        video0_caps.stdout = """Device Caps      : 0x84a00001
        Video Capture
        Streaming"""

        video1_caps = MagicMock()
        video1_caps.returncode = 0
        video1_caps.stdout = """Device Caps      : 0x84a00000
        Metadata Capture"""

        # Mock v4l2-ctl --list-formats-ext
        video0_formats = MagicMock()
        video0_formats.returncode = 0
        video0_formats.stdout = """[0]: 'MJPG' (Motion-JPEG)
        Size: Discrete 1920x1080
            Interval: Discrete 0.033s (30.000 fps)
"""

        def run_side_effect(*args, **kwargs):
            cmd = args[0]
            if "--list-devices" in cmd:
                return list_devices_result
            elif "--all" in cmd:
                device = cmd[2]
                if device == "/dev/video0":
                    return video0_caps
                elif device == "/dev/video1":
                    return video1_caps
            elif "--list-formats-ext" in cmd:
                return video0_formats
            return MagicMock(returncode=1, stdout="")

        mock_run.side_effect = run_side_effect

        cameras = discovery.discover_cameras()

        # Should find 1 camera with video capture capability
        self.assertEqual(len(cameras), 1)

        # Verify camera details
        camera = cameras[0]
        self.assertEqual(camera.device_type, CameraType.USB)
        self.assertEqual(camera.device_name, "Integrated Camera")

        usb_details = cast(USBCameraDetails, camera.details)
        self.assertEqual(usb_details.device_path, "/dev/video0")
        self.assertIsNotNone(usb_details.best_capture)
        assert (
            usb_details.best_capture is not None
        )  # Type narrowing for static analysis
        self.assertEqual(usb_details.best_capture.fourcc, "MJPG")
        self.assertEqual(usb_details.best_capture.width, 1920)
        self.assertEqual(usb_details.best_capture.height, 1080)
        self.assertEqual(usb_details.best_capture.fps, 30.0)

    @patch("camera.subprocess.run")
    def test_discover_cameras_handles_missing_tool(self, mock_run):
        """discover_cameras should return empty list when v4l2-ctl not found."""
        discovery = USBCameraDiscovery()

        mock_run.side_effect = FileNotFoundError()

        cameras = discovery.discover_cameras()

        self.assertEqual(cameras, [])

    @patch("camera.subprocess.run")
    def test_discover_cameras_handles_timeout(self, mock_run):
        """discover_cameras should return empty list on timeout."""
        discovery = USBCameraDiscovery()

        mock_run.side_effect = subprocess.TimeoutExpired("v4l2-ctl", 5)

        cameras = discovery.discover_cameras()

        self.assertEqual(cameras, [])

    @patch("camera.subprocess.run")
    def test_discover_cameras_filters_error_messages(self, mock_run):
        """discover_cameras should skip error messages in output."""
        discovery = USBCameraDiscovery()

        list_devices_result = MagicMock()
        list_devices_result.returncode = 0
        list_devices_result.stdout = """Cannot open device /dev/video3: Permission denied
Integrated Camera (usb-0000:00:14.0-8):
        /dev/video0
Failed to query device
"""

        video0_caps = MagicMock()
        video0_caps.returncode = 0
        video0_caps.stdout = """Device Caps      : 0x84a00001
        Video Capture"""

        video0_formats = MagicMock()
        video0_formats.returncode = 0
        video0_formats.stdout = """[0]: 'MJPG' (Motion-JPEG)
        Size: Discrete 1920x1080
            Interval: Discrete 0.033s (30.000 fps)
"""

        def run_side_effect(*args, **kwargs):
            cmd = args[0]
            if "--list-devices" in cmd:
                return list_devices_result
            elif "--all" in cmd:
                return video0_caps
            elif "--list-formats-ext" in cmd:
                return video0_formats
            return MagicMock(returncode=1, stdout="")

        mock_run.side_effect = run_side_effect

        cameras = discovery.discover_cameras()

        # Should find only 1 camera, ignoring error lines
        self.assertEqual(len(cameras), 1)
        self.assertEqual(cameras[0].device_id, "usb-camera-integrated-camera-0")

    @patch("camera.subprocess.run")
    def test_discover_cameras_normalizes_device_names_for_url(self, mock_run):
        """discover_cameras should normalize device names to be URL-safe."""
        discovery = USBCameraDiscovery()

        list_devices_result = MagicMock()
        list_devices_result.returncode = 0
        list_devices_result.stdout = """Thronmax StreamGo Webcam: Thron (usb-0000:00:14.0-8):
        /dev/video0
"""

        video_caps = MagicMock()
        video_caps.returncode = 0
        video_caps.stdout = """Device Caps      : 0x84a00001
        Video Capture
        Streaming"""

        video_formats = MagicMock()
        video_formats.returncode = 0
        video_formats.stdout = """[0]: 'MJPG' (Motion-JPEG)
        Size: Discrete 1920x1080
            Interval: Discrete 0.033s (30.000 fps)
"""

        def run_side_effect(*args, **kwargs):
            cmd = args[0]
            if "--list-devices" in cmd:
                return list_devices_result
            elif "--all" in cmd:
                return video_caps
            elif "--list-formats-ext" in cmd:
                return video_formats
            return MagicMock(returncode=1, stdout="")

        mock_run.side_effect = run_side_effect

        cameras = discovery.discover_cameras()

        self.assertEqual(len(cameras), 1)

        # Verify device ID is URL-safe (no colons)
        device_id = cameras[0].device_id
        self.assertIn("usb-camera-thronmax-streamgo-webcam-thron-0", device_id)
        self.assertNotIn(":", device_id)

        # Verify device_name is preserved
        self.assertEqual(cameras[0].device_name, "Thronmax StreamGo Webcam: Thron")


class TestONVIFProfile(unittest.TestCase):
    """
    Unit tests for ONVIFProfile.

    The tests focus on:
      * property getters and setters,
      * correct initialization.
    """

    def test_onvif_profile_initialization(self):
        """ONVIFProfile should initialize with empty values."""
        profile = ONVIFProfile()

        self.assertEqual(profile.name, "")
        self.assertEqual(profile.token, "")
        self.assertEqual(profile.rtsp_url, "")
        self.assertEqual(profile.vec_encoding, "")
        self.assertEqual(profile.vec_resolution, {})
        self.assertEqual(profile.vec_framerate_limit, 0)
        self.assertEqual(profile.vec_bitrate_limit, 0)

    def test_onvif_profile_property_setters(self):
        """ONVIFProfile properties should be settable."""
        profile = ONVIFProfile()

        profile.name = "Profile_1"
        profile.token = "token123"
        profile.rtsp_url = "rtsp://192.168.1.100:554/stream1"
        profile.vec_encoding = "H264"
        profile.vec_resolution = {"width": 1920, "height": 1080}
        profile.vec_framerate_limit = 30
        profile.vec_bitrate_limit = 4096

        self.assertEqual(profile.name, "Profile_1")
        self.assertEqual(profile.token, "token123")
        self.assertEqual(profile.rtsp_url, "rtsp://192.168.1.100:554/stream1")
        self.assertEqual(profile.vec_encoding, "H264")
        self.assertEqual(profile.vec_resolution, {"width": 1920, "height": 1080})
        self.assertEqual(profile.vec_framerate_limit, 30)
        self.assertEqual(profile.vec_bitrate_limit, 4096)


class TestONVIFCameraDiscovery(unittest.TestCase):
    """
    Unit tests for ONVIFCameraDiscovery.

    The tests focus on:
      * singleton pattern implementation,
      * reading discovered cameras from JSON file,
      * authenticating and loading camera profiles,
      * error handling for missing files and invalid data.
    """

    def setUp(self):
        """Reset singleton state before each test."""
        ONVIFCameraDiscovery._instance = None

    def tearDown(self):
        """Reset singleton state after each test."""
        ONVIFCameraDiscovery._instance = None

    def test_singleton_returns_same_instance(self):
        """ONVIFCameraDiscovery should return the same instance on multiple calls."""
        with tempfile.TemporaryDirectory() as td:
            json_file = Path(td) / "cameras.json"
            json_file.write_text('{"cameras": []}')

            instance1 = ONVIFCameraDiscovery(str(json_file))
            instance2 = ONVIFCameraDiscovery(str(json_file))
            self.assertIs(instance1, instance2)

    def test_singleton_only_initializes_once(self):
        """Multiple calls should not re-initialize the singleton."""
        with tempfile.TemporaryDirectory() as td:
            json_file = Path(td) / "cameras.json"
            json_file.write_text('{"cameras": []}')

            instance1 = ONVIFCameraDiscovery(str(json_file))
            original_path = instance1.json_file_path
            instance2 = ONVIFCameraDiscovery(str(json_file))
            self.assertEqual(instance2.json_file_path, original_path)

    def test_discover_cameras_loads_from_json(self):
        """discover_cameras should load cameras from JSON file."""
        with tempfile.TemporaryDirectory() as td:
            json_file = Path(td) / "cameras.json"
            cameras_data = {
                "cameras": [
                    {"ip": "192.168.1.100", "port": 80},
                    {"ip": "192.168.1.101", "port": 8080},
                ]
            }
            json_file.write_text(json.dumps(cameras_data))

            discovery = ONVIFCameraDiscovery(str(json_file))
            cameras = discovery.discover_cameras()

            self.assertEqual(len(cameras), 2)

            # Verify first camera
            cam1 = cameras[0]
            self.assertEqual(cam1.device_id, "network-camera-192.168.1.100-80")
            self.assertEqual(cam1.device_name, "ONVIF Camera 192.168.1.100")
            self.assertEqual(cam1.device_type, CameraType.NETWORK)
            net_details1 = cast(NetworkCameraDetails, cam1.details)
            self.assertEqual(net_details1.ip, "192.168.1.100")
            self.assertEqual(net_details1.port, 80)
            self.assertEqual(net_details1.profiles, [])

            # Verify second camera
            cam2 = cameras[1]
            self.assertEqual(cam2.device_id, "network-camera-192.168.1.101-8080")
            net_details2 = cast(NetworkCameraDetails, cam2.details)
            self.assertEqual(net_details2.ip, "192.168.1.101")
            self.assertEqual(net_details2.port, 8080)

    def test_discover_cameras_handles_missing_file(self):
        """discover_cameras should return empty list when JSON file not found."""
        discovery = ONVIFCameraDiscovery("/nonexistent/cameras.json")
        cameras = discovery.discover_cameras()

        self.assertEqual(cameras, [])

    def test_discover_cameras_handles_invalid_json(self):
        """discover_cameras should return empty list for invalid JSON."""
        with tempfile.TemporaryDirectory() as td:
            json_file = Path(td) / "invalid.json"
            json_file.write_text("{ invalid json")

            discovery = ONVIFCameraDiscovery(str(json_file))
            cameras = discovery.discover_cameras()

            self.assertEqual(cameras, [])

    def test_discover_cameras_skips_invalid_entries(self):
        """discover_cameras should skip entries with missing ip or port."""
        with tempfile.TemporaryDirectory() as td:
            json_file = Path(td) / "cameras.json"
            cameras_data = {
                "cameras": [
                    {"ip": "192.168.1.100", "port": 80},
                    {"ip": "192.168.1.101"},  # Missing port
                    {"port": 8080},  # Missing ip
                    {"ip": "192.168.1.102", "port": 80},
                ]
            }
            json_file.write_text(json.dumps(cameras_data))

            discovery = ONVIFCameraDiscovery(str(json_file))
            cameras = discovery.discover_cameras()

            # Should only load valid entries
            self.assertEqual(len(cameras), 2)
            device_ids = {cam.device_id for cam in cameras}
            self.assertIn("network-camera-192.168.1.100-80", device_ids)
            self.assertIn("network-camera-192.168.1.102-80", device_ids)

    def test_discover_cameras_handles_empty_cameras_list(self):
        """discover_cameras should handle empty cameras list."""
        with tempfile.TemporaryDirectory() as td:
            json_file = Path(td) / "cameras.json"
            json_file.write_text('{"cameras": []}')

            discovery = ONVIFCameraDiscovery(str(json_file))
            cameras = discovery.discover_cameras()

            self.assertEqual(cameras, [])

    def test_load_camera_profiles_invalid_camera_id_format(self):
        """load_camera_profiles should raise ValueError for invalid camera_id format."""
        with tempfile.TemporaryDirectory() as td:
            json_file = Path(td) / "cameras.json"
            json_file.write_text('{"cameras": []}')

            discovery = ONVIFCameraDiscovery(str(json_file))

            with self.assertRaises(ValueError) as ctx:
                discovery.load_camera_profiles("invalid_id", "admin", "password")

            self.assertIn("Invalid camera_id format", str(ctx.exception))

    def test_load_camera_profiles_invalid_port_in_camera_id(self):
        """load_camera_profiles should raise ValueError for non-numeric port."""
        with tempfile.TemporaryDirectory() as td:
            json_file = Path(td) / "cameras.json"
            json_file.write_text('{"cameras": []}')

            discovery = ONVIFCameraDiscovery(str(json_file))

            with self.assertRaises(ValueError) as ctx:
                discovery.load_camera_profiles(
                    "network-camera-192.168.1.100-abc", "admin", "password"
                )

            self.assertIn("Invalid port in camera_id", str(ctx.exception))

    @patch("camera.ONVIFCamera")
    def test_load_camera_profiles_successful_authentication(self, mock_onvif_camera):
        """load_camera_profiles should authenticate and return camera with profiles and best_profile."""
        with tempfile.TemporaryDirectory() as td:
            json_file = Path(td) / "cameras.json"
            json_file.write_text('{"cameras": []}')

            discovery = ONVIFCameraDiscovery(str(json_file))

            # Mock ONVIF camera and media service
            mock_camera = MagicMock()
            mock_media_service = MagicMock()
            mock_camera.create_media_service.return_value = mock_media_service

            # Mock profiles
            mock_profile = MagicMock()
            mock_profile.Name = "Profile_1"
            mock_profile.token = "token123"
            mock_profile.VideoEncoderConfiguration = MagicMock()
            mock_profile.VideoEncoderConfiguration.Encoding = "H264"
            mock_profile.VideoEncoderConfiguration.Resolution = MagicMock()
            mock_profile.VideoEncoderConfiguration.Resolution.Width = 1920
            mock_profile.VideoEncoderConfiguration.Resolution.Height = 1080
            mock_profile.VideoEncoderConfiguration.RateControl = MagicMock()
            mock_profile.VideoEncoderConfiguration.RateControl.FrameRateLimit = 30
            mock_profile.VideoEncoderConfiguration.RateControl.BitrateLimit = 4096

            mock_media_service.GetProfiles.return_value = [mock_profile]

            # Mock GetStreamUri
            mock_stream_uri = MagicMock()
            mock_stream_uri.Uri = "rtsp://192.168.1.100:554/stream1"
            mock_media_service.GetStreamUri.return_value = mock_stream_uri

            mock_onvif_camera.return_value = mock_camera

            camera = discovery.load_camera_profiles(
                "network-camera-192.168.1.100-80", "admin", "password"
            )

            # Verify camera details
            self.assertEqual(camera.device_id, "network-camera-192.168.1.100-80")
            self.assertEqual(camera.device_name, "ONVIF Camera 192.168.1.100")
            self.assertEqual(camera.device_type, CameraType.NETWORK)
            net_details = cast(NetworkCameraDetails, camera.details)
            self.assertEqual(net_details.ip, "192.168.1.100")
            self.assertEqual(net_details.port, 80)

            # Verify profiles
            self.assertEqual(len(net_details.profiles), 1)
            profile = net_details.profiles[0]
            self.assertEqual(profile.name, "Profile_1")
            self.assertEqual(profile.rtsp_url, "rtsp://192.168.1.100:554/stream1")
            self.assertEqual(profile.resolution, "1920x1080")
            self.assertEqual(profile.encoding, "H264")
            self.assertEqual(profile.framerate, 30)
            self.assertEqual(profile.bitrate, 4096)

            # Verify best_profile is selected
            self.assertIsNotNone(net_details.best_profile)
            assert (
                net_details.best_profile is not None
            )  # Type narrowing for static analysis
            self.assertEqual(net_details.best_profile.name, "Profile_1")

            # Verify ONVIFCamera was called with correct credentials
            mock_onvif_camera.assert_called_once_with(
                "192.168.1.100", 80, "admin", "password"
            )

    @patch("camera.ONVIFCamera")
    def test_load_camera_profiles_handles_connection_error(self, mock_onvif_camera):
        """load_camera_profiles should propagate connection errors."""
        with tempfile.TemporaryDirectory() as td:
            json_file = Path(td) / "cameras.json"
            json_file.write_text('{"cameras": []}')

            discovery = ONVIFCameraDiscovery(str(json_file))

            mock_onvif_camera.side_effect = ConnectionError("Unable to connect")

            with self.assertRaises(ConnectionError):
                discovery.load_camera_profiles(
                    "network-camera-192.168.1.100-80", "admin", "password"
                )

    @patch("camera.ONVIFCamera")
    def test_camera_profiles_extracts_multiple_profiles(self, mock_onvif_camera):
        """_camera_profiles should extract multiple profiles correctly."""
        with tempfile.TemporaryDirectory() as td:
            json_file = Path(td) / "cameras.json"
            json_file.write_text('{"cameras": []}')

            discovery = ONVIFCameraDiscovery(str(json_file))

            # Mock camera with multiple profiles
            mock_camera = MagicMock()
            mock_media_service = MagicMock()
            mock_camera.create_media_service.return_value = mock_media_service

            # Profile 1
            mock_profile1 = MagicMock()
            mock_profile1.Name = "Profile_1"
            mock_profile1.token = "token1"
            mock_profile1.VideoEncoderConfiguration = MagicMock()
            mock_profile1.VideoEncoderConfiguration.Encoding = "H264"
            mock_profile1.VideoEncoderConfiguration.Resolution = MagicMock()
            mock_profile1.VideoEncoderConfiguration.Resolution.Width = 1920
            mock_profile1.VideoEncoderConfiguration.Resolution.Height = 1080
            mock_profile1.VideoEncoderConfiguration.RateControl = MagicMock()
            mock_profile1.VideoEncoderConfiguration.RateControl.FrameRateLimit = 30
            mock_profile1.VideoEncoderConfiguration.RateControl.BitrateLimit = 4096

            # Profile 2
            mock_profile2 = MagicMock()
            mock_profile2.Name = "Profile_2"
            mock_profile2.token = "token2"
            mock_profile2.VideoEncoderConfiguration = MagicMock()
            mock_profile2.VideoEncoderConfiguration.Encoding = "H265"
            mock_profile2.VideoEncoderConfiguration.Resolution = MagicMock()
            mock_profile2.VideoEncoderConfiguration.Resolution.Width = 1280
            mock_profile2.VideoEncoderConfiguration.Resolution.Height = 720
            mock_profile2.VideoEncoderConfiguration.RateControl = MagicMock()
            mock_profile2.VideoEncoderConfiguration.RateControl.FrameRateLimit = 15
            mock_profile2.VideoEncoderConfiguration.RateControl.BitrateLimit = 2048

            mock_media_service.GetProfiles.return_value = [mock_profile1, mock_profile2]

            # Mock GetStreamUri responses
            def get_stream_uri_side_effect(*args, **kwargs):
                token = kwargs.get("ProfileToken") or args[0].get("ProfileToken")
                mock_uri = MagicMock()
                if token == "token1":
                    mock_uri.Uri = "rtsp://192.168.1.100:554/stream1"
                else:
                    mock_uri.Uri = "rtsp://192.168.1.100:554/stream2"
                return mock_uri

            mock_media_service.GetStreamUri.side_effect = get_stream_uri_side_effect

            profiles = discovery._camera_profiles(mock_camera)

            self.assertEqual(len(profiles), 2)

            # Verify profile 1
            self.assertEqual(profiles[0].name, "Profile_1")
            self.assertEqual(profiles[0].token, "token1")
            self.assertEqual(profiles[0].rtsp_url, "rtsp://192.168.1.100:554/stream1")
            self.assertEqual(profiles[0].vec_encoding, "H264")
            self.assertEqual(
                profiles[0].vec_resolution, {"width": 1920, "height": 1080}
            )
            self.assertEqual(profiles[0].vec_framerate_limit, 30)
            self.assertEqual(profiles[0].vec_bitrate_limit, 4096)

            # Verify profile 2
            self.assertEqual(profiles[1].name, "Profile_2")
            self.assertEqual(profiles[1].token, "token2")
            self.assertEqual(profiles[1].rtsp_url, "rtsp://192.168.1.100:554/stream2")
            self.assertEqual(profiles[1].vec_encoding, "H265")
            self.assertEqual(profiles[1].vec_resolution, {"width": 1280, "height": 720})
            self.assertEqual(profiles[1].vec_framerate_limit, 15)
            self.assertEqual(profiles[1].vec_bitrate_limit, 2048)

    @patch("camera.ONVIFCamera")
    def test_camera_profiles_handles_missing_stream_uri(self, mock_onvif_camera):
        """_camera_profiles should handle profiles without stream URI gracefully."""
        with tempfile.TemporaryDirectory() as td:
            json_file = Path(td) / "cameras.json"
            json_file.write_text('{"cameras": []}')

            discovery = ONVIFCameraDiscovery(str(json_file))

            mock_camera = MagicMock()
            mock_media_service = MagicMock()
            mock_camera.create_media_service.return_value = mock_media_service

            mock_profile = MagicMock()
            mock_profile.Name = "Profile_1"
            mock_profile.token = "token1"
            mock_profile.VideoEncoderConfiguration = MagicMock()
            mock_profile.VideoEncoderConfiguration.Encoding = "H264"
            mock_profile.VideoEncoderConfiguration.Resolution = MagicMock()
            mock_profile.VideoEncoderConfiguration.Resolution.Width = 1920
            mock_profile.VideoEncoderConfiguration.Resolution.Height = 1080
            mock_profile.VideoEncoderConfiguration.RateControl = MagicMock()
            mock_profile.VideoEncoderConfiguration.RateControl.FrameRateLimit = 30
            mock_profile.VideoEncoderConfiguration.RateControl.BitrateLimit = 4096

            mock_media_service.GetProfiles.return_value = [mock_profile]
            mock_media_service.GetStreamUri.side_effect = Exception("Stream URI failed")

            profiles = discovery._camera_profiles(mock_camera)

            # Should still return profile with empty rtsp_url
            self.assertEqual(len(profiles), 1)
            self.assertEqual(profiles[0].name, "Profile_1")
            self.assertEqual(profiles[0].rtsp_url, "")

    @patch("camera.ONVIFCamera")
    def test_camera_profiles_handles_missing_video_encoder_config(
        self, mock_onvif_camera
    ):
        """_camera_profiles should handle profiles without VideoEncoderConfiguration."""
        with tempfile.TemporaryDirectory() as td:
            json_file = Path(td) / "cameras.json"
            json_file.write_text('{"cameras": []}')

            discovery = ONVIFCameraDiscovery(str(json_file))

            mock_camera = MagicMock()
            mock_media_service = MagicMock()
            mock_camera.create_media_service.return_value = mock_media_service

            mock_profile = MagicMock()
            mock_profile.Name = "Profile_1"
            mock_profile.token = "token1"
            mock_profile.VideoEncoderConfiguration = None

            mock_media_service.GetProfiles.return_value = [mock_profile]

            mock_stream_uri = MagicMock()
            mock_stream_uri.Uri = "rtsp://192.168.1.100:554/stream1"
            mock_media_service.GetStreamUri.return_value = mock_stream_uri

            profiles = discovery._camera_profiles(mock_camera)

            # Should still return profile with empty encoding/resolution
            self.assertEqual(len(profiles), 1)
            self.assertEqual(profiles[0].name, "Profile_1")
            self.assertEqual(profiles[0].vec_encoding, "")
            self.assertEqual(profiles[0].vec_resolution, {})

    def test_init_with_default_json_path(self):
        """ONVIFCameraDiscovery should use default path when not provided."""
        discovery = ONVIFCameraDiscovery()

        self.assertEqual(discovery.json_file_path, "/onvif/onvif_cameras.json")


if __name__ == "__main__":
    unittest.main()
