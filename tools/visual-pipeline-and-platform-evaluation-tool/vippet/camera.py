import json
import logging
import subprocess
import threading
from typing import List, Optional
from onvif import ONVIFCamera

from api.api_schemas import (
    Camera,
    CameraType,
    USBCameraDetails,
    NetworkCameraDetails,
    CameraProfileInfo,
)
from utils import normalize_device_name_for_url

DEFAULT_ONVIF_JSON_PATH = "/onvif/onvif_cameras.json"

logger = logging.getLogger("camera")


class USBCameraDiscovery:
    """
    Singleton class for discovering USB cameras connected to the system.

    Uses v4l2-ctl to enumerate video devices on Linux systems and verify
    their video capture capabilities.
    """

    _instance: Optional["USBCameraDiscovery"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking
                if cls._instance is None:
                    cls._instance = super(USBCameraDiscovery, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize USB camera discovery."""
        if not hasattr(self, "initialized"):
            self.initialized = True
            logger.debug("USBCameraDiscovery initialized")

    def _get_camera_resolution(self, device_path: str) -> Optional[str]:
        """
        Get the current resolution of a USB camera.

        Args:
            device_path: Path to the video device (e.g., /dev/video0).

        Returns:
            Optional[str]: Resolution as a string (e.g., "1920x1080"), or None if unable to determine.
        """
        try:
            result = subprocess.run(
                ["v4l2-ctl", "-d", device_path, "--get-fmt-video"],
                capture_output=True,
                text=True,
                timeout=3,
            )

            if result.returncode == 0:
                output = result.stdout
                width = None
                height = None

                # Parse output for Width and Height
                for line in output.split("\n"):
                    line = line.strip()
                    if "Width/Height" in line:
                        # Format: "Width/Height      : 1920/1080"
                        parts = line.split(":")
                        if len(parts) == 2:
                            dimensions = parts[1].strip().split("/")
                            if len(dimensions) == 2:
                                try:
                                    width = int(dimensions[0])
                                    height = int(dimensions[1])
                                except ValueError:
                                    pass

                if width and height:
                    return f"{width}x{height}"

            logger.debug(f"Could not determine resolution for {device_path}")
            return None

        except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
            logger.debug(f"Error getting resolution for {device_path}: {e}")
            return None

    def _can_capture_video(self, device_path: str) -> bool:
        """
        Check if a video device supports video capture (streaming).

        Uses v4l2-ctl to query device capabilities and verify it supports
        video capture operations, not just metadata or other functions.

        Specifically checks that "Video Capture" is present in the
        "Device Caps" section of the v4l2-ctl output.

        Args:
            device_path: Path to the video device (e.g., /dev/video0).

        Returns:
            bool: True if device supports video capture, False otherwise.
        """
        try:
            # Query device capabilities using v4l2-ctl
            result = subprocess.run(
                ["v4l2-ctl", "-d", device_path, "--all"],
                capture_output=True,
                text=True,
                timeout=3,
            )

            if result.returncode == 0:
                output = result.stdout

                # Parse output to find Device Caps section
                has_device_caps_video_capture = False

                lines = output.split("\n")
                in_device_caps_section = False

                for line in lines:
                    line_stripped = line.strip()

                    # Identify Device Caps section
                    if line_stripped.startswith("Device Caps"):
                        in_device_caps_section = True
                        # Check if Video Capture is on the same line
                        if "Video Capture" in line:
                            has_device_caps_video_capture = True
                            break
                    elif in_device_caps_section:
                        # Check if this is a continuation line (indented)
                        if line.startswith("\t") or line.startswith(" " * 4):
                            if "Video Capture" in line:
                                has_device_caps_video_capture = True
                                break
                        elif line_stripped and ":" in line_stripped:
                            # New section started, stop looking
                            break

                # Device must have Video Capture in Device Caps
                if has_device_caps_video_capture:
                    return True
                else:
                    logger.debug(
                        f"{device_path} does not support video capture in Device Caps"
                    )
                    return False
            else:
                logger.warning(f"Failed to query capabilities for {device_path}")
                return False

        except FileNotFoundError:
            logger.error(
                f"v4l2-ctl not available, cannot verify {device_path} capabilities"
            )
            return False
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout querying {device_path} capabilities")
            return False
        except Exception as e:
            logger.error(
                f"Error checking {device_path} capabilities: {e}", exc_info=True
            )
            return False

    def discover_cameras(self) -> List[Camera]:
        """
        Discover USB cameras connected to the system.

        Uses v4l2-ctl to enumerate video devices on Linux systems.

        Returns:
            List[Camera]: List of discovered USB cameras.
        """
        cameras = []

        try:
            # Try using v4l2-ctl to list video devices
            result = subprocess.run(
                ["v4l2-ctl", "--list-devices"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.stdout:
                lines = result.stdout.strip().split("\n")
                current_device_name = None

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    # Skip error/warning messages
                    if any(
                        keyword in line.lower()
                        for keyword in [
                            "error",
                            "failed",
                            "cannot",
                            "permission denied",
                        ]
                    ):
                        continue

                    # Device name lines don't start with /dev/
                    if not line.startswith("/dev/"):
                        # Remove trailing colon and parentheses content
                        current_device_name = line.rstrip(":").split("(")[0].strip()
                    else:
                        # This is a device path
                        device_path = line
                        if current_device_name and "/dev/video" in device_path:
                            # Verify device supports video capture
                            if not self._can_capture_video(device_path):
                                logger.debug(
                                    f"Skipping {device_path} - no capture capability"
                                )
                                continue

                            # Extract video device number
                            device_num = device_path.replace("/dev/video", "")

                            # Create normalized device name for ID (URL-safe)
                            device_name = normalize_device_name_for_url(
                                current_device_name
                            )

                            # Get camera resolution
                            resolution = self._get_camera_resolution(device_path)

                            cameras.append(
                                Camera(
                                    device_name=current_device_name,
                                    device_type=CameraType.USB,
                                    device_id=f"usb_camera_{device_name}_{device_num}",
                                    details=USBCameraDetails(
                                        device_path=device_path, resolution=resolution
                                    ),
                                )
                            )

        except FileNotFoundError:
            logger.error("v4l2-ctl not found, cannot discover USB cameras")
        except subprocess.TimeoutExpired:
            logger.error("v4l2-ctl command timed out")
        except Exception as e:
            logger.error(f"Error discovering USB cameras: {e}", exc_info=True)
        logger.debug(f"Discovered {len(cameras)} USB camera(s)")
        return cameras


class ONVIFProfile:
    """
    Represents an ONVIF profile with essential information for GStreamer pipeline operation.

    This class stores only the attributes necessary for configuring and running
    GStreamer pipelines with RTSP streams.

    Attributes:
        name (str): The profile name
        token (str): Unique profile identifier token
        rtsp_url (str): RTSP streaming URL for this profile
        vec_encoding (str): Video encoding format (e.g., H264, H265)
        vec_resolution (dict): Video resolution settings (width, height)
        vec_framerate_limit (int): Maximum framerate limit
        vec_bitrate_limit (int): Maximum bitrate limit
    """

    def __init__(self):
        # Essential profile details for GStreamer pipeline
        self._name = ""
        self._token = ""
        self._rtsp_url = ""
        self._vec_encoding = ""
        self._vec_resolution = {}
        self._vec_framerate_limit = 0
        self._vec_bitrate_limit = 0

    @property
    def name(self) -> str:
        """Get the name of the ONVIF profile."""
        return self._name

    @name.setter
    def name(self, name: str):
        """Set the name of the ONVIF profile."""
        self._name = name

    @property
    def token(self) -> str:
        """Get the token of the ONVIF profile."""
        return self._token

    @token.setter
    def token(self, token: str):
        """Set the token of the ONVIF profile."""
        self._token = token

    @property
    def rtsp_url(self) -> str:
        """Get the RTSP URL of the ONVIF profile."""
        return self._rtsp_url

    @rtsp_url.setter
    def rtsp_url(self, rtsp_url: str):
        """Set the RTSP URL of the ONVIF profile."""
        self._rtsp_url = rtsp_url

    @property
    def vec_encoding(self) -> str:
        """Get the encoding of the Video Encoder Configuration."""
        return self._vec_encoding

    @vec_encoding.setter
    def vec_encoding(self, vec_encoding: str):
        """Set the encoding of the Video Encoder Configuration."""
        self._vec_encoding = vec_encoding

    @property
    def vec_resolution(self) -> dict:
        """Get the resolution of the Video Encoder Configuration."""
        return self._vec_resolution

    @vec_resolution.setter
    def vec_resolution(self, vec_resolution: dict):
        """Set the resolution of the Video Encoder Configuration."""
        self._vec_resolution = vec_resolution

    @property
    def vec_framerate_limit(self) -> int:
        """Get the framerate limit of the Video Encoder Configuration."""
        return self._vec_framerate_limit

    @vec_framerate_limit.setter
    def vec_framerate_limit(self, vec_framerate_limit: int):
        """Set the framerate limit of the Video Encoder Configuration."""
        self._vec_framerate_limit = vec_framerate_limit

    @property
    def vec_bitrate_limit(self) -> int:
        """Get the bitrate limit of the Video Encoder Configuration."""
        return self._vec_bitrate_limit

    @vec_bitrate_limit.setter
    def vec_bitrate_limit(self, vec_bitrate_limit: int):
        """Set the bitrate limit of the Video Encoder Configuration."""
        self._vec_bitrate_limit = vec_bitrate_limit


class ONVIFCameraDiscovery:
    """
    Singleton class for discovering ONVIF network cameras.

    Uses WS-Discovery protocol to find ONVIF-compliant cameras on the local network.
    """

    _instance: Optional["ONVIFCameraDiscovery"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking
                if cls._instance is None:
                    cls._instance = super(ONVIFCameraDiscovery, cls).__new__(cls)
        return cls._instance

    def __init__(self, json_file_path: str = ""):
        # Protect against multiple initialization
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        # Path to JSON file written by onvif_discovery_agent
        self.json_file_path = json_file_path or DEFAULT_ONVIF_JSON_PATH

        logger.debug(
            f"ONVIFCameraDiscovery initialized with JSON file: {self.json_file_path}"
        )

    def discover_cameras(self) -> List[Camera]:
        """
        Retrieve discovered ONVIF cameras from the JSON file written by onvif_discovery_agent.

        Returns cameras with basic information (IP, port) and empty profiles list.
        Profiles are populated after authentication via load_camera_profiles().

        Returns:
            List[Camera]: List of discovered cameras with IP and port information.
        """
        cameras = []

        try:
            with open(self.json_file_path, "r") as f:
                data = json.load(f)

            discovered_cameras = data.get("cameras", [])

            logger.debug(
                f"Loaded {len(discovered_cameras)} camera(s) from {self.json_file_path}"
            )

            for camera_data in discovered_cameras:
                ip = camera_data.get("ip")
                port = camera_data.get("port")

                if not ip or not port:
                    logger.warning(f"Skipping invalid camera entry: {camera_data}")
                    continue

                cameras.append(
                    Camera(
                        device_name=f"ONVIF Camera {ip}",
                        device_type=CameraType.NETWORK,
                        device_id=f"network_camera_{ip}_{port}",
                        details=NetworkCameraDetails(ip=ip, port=port, profiles=[]),
                    )
                )

            logger.debug(f"Discovered {len(cameras)} ONVIF camera(s) from JSON file")
            return cameras

        except FileNotFoundError:
            logger.warning(f"ONVIF cameras JSON file not found: {self.json_file_path}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse ONVIF cameras JSON file: {e}")
            return []
        except Exception as e:
            logger.error(f"Error reading ONVIF cameras from JSON: {e}", exc_info=True)
            return []

    def load_camera_profiles(
        self, camera_id: str, username: str, password: str
    ) -> Camera:
        """
        Authenticate with a specific ONVIF camera and load its profiles.

        Args:
            camera_id: Camera identifier (e.g., "network_camera_192.168.1.100_80").
            username: ONVIF username for authentication.
            password: ONVIF password for authentication.

        Returns:
            Camera: Updated Camera object with populated profiles in details.profiles.

        Raises:
            ValueError: If camera_id is invalid or camera not found.
            ConnectionError: If unable to connect to camera.
            Exception: For authentication or profile loading failures.
        """
        # Parse camera_id to extract IP and port
        # Expected format: "network_camera_{ip}_{port}"
        if not camera_id.startswith("network_camera_"):
            raise ValueError(f"Invalid camera_id format: {camera_id}")

        parts = camera_id.replace("network_camera_", "").rsplit("_", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid camera_id format: {camera_id}")

        ip = parts[0]
        try:
            port = int(parts[1])
        except ValueError:
            raise ValueError(f"Invalid port in camera_id: {camera_id}")

        logger.debug(f"Attempting to authenticate with camera at {ip}:{port}")

        try:
            # Create ONVIF camera object with provided credentials
            camera_obj = ONVIFCamera(ip, port, username, password)

            # Get camera profiles
            profiles = self._camera_profiles(camera_obj)

            # Convert ONVIFProfile objects to CameraProfileInfo
            profile_infos = []
            for profile in profiles:
                resolution = None
                if profile.vec_resolution:
                    width = profile.vec_resolution.get("width")
                    height = profile.vec_resolution.get("height")
                    if width and height:
                        resolution = f"{width}x{height}"

                profile_infos.append(
                    CameraProfileInfo(
                        name=profile.name,
                        rtsp_url=profile.rtsp_url,
                        resolution=resolution,
                        encoding=profile.vec_encoding,
                        framerate=profile.vec_framerate_limit,
                        bitrate=profile.vec_bitrate_limit,
                    )
                )

            # Create Camera object with populated profiles
            camera = Camera(
                device_name=f"ONVIF Camera {ip}",
                device_type=CameraType.NETWORK,
                device_id=camera_id,
                details=NetworkCameraDetails(ip=ip, port=port, profiles=profile_infos),
            )

            logger.debug(
                f"Successfully authenticated with camera {ip}:{port} and loaded {len(profiles)} profile(s)"
            )
            return camera

        except Exception as e:
            logger.error(
                f"Failed to authenticate with camera {ip}:{port}: {e}", exc_info=True
            )
            raise

    def _camera_profiles(self, client) -> list[ONVIFProfile]:  # pylint: disable=too-many-statements, too-many-locals, too-many-branches
        """
        This function queries an ONVIF camera for its available media profiles and extracts
        detailed configuration information including video encoder settings, audio configurations,
        PTZ capabilities, and RTSP streaming URIs.

        Args:
            client: An ONVIF client instance used to communicate with the camera device.
                Defaults to False.

        Returns:
            List[ONVIFProfile]: A list of ONVIFProfile objects containing the extracted profile
                information. Each profile includes:
                - Basic profile information (name, token, fixed status)
                - Video source configuration (name, token, source token, bounds)
                - Video encoder settings (resolution, quality, bitrate, framerate, codec details)
                - Audio source and encoder configurations (if available)
                - PTZ configuration (if available)
                - RTSP stream URI

        Raises:
            Exception: May raise exceptions related to ONVIF service communication failures,
                particularly when retrieving stream URIs.
        """

        media_service = client.create_media_service()

        profiles = media_service.GetProfiles()

        onvif_profiles: List[ONVIFProfile] = []

        for i, profile in enumerate(profiles, 1):
            onvif_profile: ONVIFProfile = ONVIFProfile()
            onvif_profile.name = profile.Name
            onvif_profile.token = profile.token
            logger.debug(f"  Profile {i}:")
            logger.debug(f"    Name: {onvif_profile.name}")
            logger.debug(f"    Token: {onvif_profile.token}")

            # Video Encoder Configuration - only essential attributes
            if (
                hasattr(profile, "VideoEncoderConfiguration")
                and profile.VideoEncoderConfiguration
            ):
                vec = profile.VideoEncoderConfiguration
                onvif_profile.vec_encoding = vec.Encoding
                logger.debug("    Video Encoder:")
                logger.debug(f"      Encoding: {vec.Encoding}")
                if hasattr(vec, "Resolution") and vec.Resolution:
                    onvif_profile.vec_resolution = {
                        "width": vec.Resolution.Width,
                        "height": vec.Resolution.Height,
                    }
                    logger.debug(
                        f"      Resolution: {vec.Resolution.Width}x{vec.Resolution.Height}"
                    )
                if hasattr(vec, "RateControl") and vec.RateControl:
                    onvif_profile.vec_framerate_limit = vec.RateControl.FrameRateLimit
                    onvif_profile.vec_bitrate_limit = vec.RateControl.BitrateLimit
                    logger.debug(
                        f"      FrameRate Limit: {vec.RateControl.FrameRateLimit}"
                    )
                    logger.debug(f"      Bitrate Limit: {vec.RateControl.BitrateLimit}")

            # Get Stream URI for this profile
            try:
                stream_setup = {
                    "Stream": "RTP-Unicast",
                    "Transport": {"Protocol": "RTSP"},
                }
                rtsp_uri = media_service.GetStreamUri(
                    {"StreamSetup": stream_setup, "ProfileToken": profile.token}
                )
                onvif_profile.rtsp_url = rtsp_uri.Uri
                logger.debug(f"        Stream URI: {rtsp_uri.Uri}")
            except AttributeError as e:
                # Profile or media service missing expected attributes
                logger.debug(f"    Stream URI: AttributeError - {e}")
            except KeyError as e:
                # Missing required keys in stream setup or response
                logger.debug(f"    Stream URI: KeyError - {e}")
            except TimeoutError as e:
                # Network timeout when contacting camera
                logger.debug(f"    Stream URI: TimeoutError - {e}")
            except ConnectionError as e:
                # Connection issues with the camera
                logger.debug(f"    Stream URI: ConnectionError - {e}")
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.debug(f"    Stream URI: Error - {e}")
            logger.debug("  ----------------------- ")

            onvif_profiles.append(onvif_profile)

        return onvif_profiles
