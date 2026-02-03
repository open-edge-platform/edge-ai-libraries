"""
Camera discovery and management module.

This module provides camera discovery functionality for both USB and network (ONVIF) cameras.
"""

import json
import logging
import re
import socket
import subprocess
import time
import xml.etree.ElementTree as ET
from typing import List, Optional
from urllib.parse import urlparse
from onvif import ONVIFCamera 

from api.api_schemas import Camera, CameraType, CameraStatus, USBCameraDetails, NetworkCameraDetails, CameraProfileInfo

logger = logging.getLogger("camera")

class USBCameraDiscovery:
    """
    Singleton class for discovering USB cameras connected to the system.
    
    Uses v4l2-ctl to enumerate video devices on Linux systems and verify
    their video capture capabilities.
    """
    
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(USBCameraDiscovery, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize USB camera discovery."""
        if not hasattr(self, "initialized"):
            self.initialized = True
            logger.debug("USBCameraDiscovery initialized")

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
                logger.warning(
                    f"Failed to query capabilities for {device_path}"
                )
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

            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                current_device_name = None

                for line in lines:
                    line = line.strip()
                    if not line:
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
                            
                            # Create normalized device name for ID
                            device_name = current_device_name.lower().replace(" ", "_")

                            cameras.append(
                                Camera(
                                    device_name=current_device_name,
                                    device_type=CameraType.USB,
                                    device_id=f"usb_camera_{device_name}_{device_num}",
                                    status=CameraStatus.AVAILABLE,
                                    details=USBCameraDetails(
                                        device_path=device_path,
                                        resolution=None
                                    )
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
    Represents an ONVIF profile containing camera configuration details.

    This class encapsulates all configuration information for an ONVIF camera profile,
    including video source settings, video encoder parameters, PTZ (Pan-Tilt-Zoom) 
    configuration, and RTSP streaming URL. It provides a comprehensive interface for
    accessing and managing camera profile attributes through property decorators.

    The class stores three main configuration categories:
    - ONVIF Profile: Basic profile information (name, token, fixed status, RTSP URL)
    - Video Source Configuration (VSC): Video input settings and bounds
    - Video Encoder Configuration (VEC): Encoding parameters, resolution, quality, and multicast
    - PTZ Configuration: Pan-Tilt-Zoom control settings and node information

    Attributes:
        name (str): The profile name
        token (str): Unique profile identifier token
        fixed (bool): Whether the profile configuration is fixed/immutable
        video_source_configuration (str): Video source configuration identifier
        video_encoder_configuration (str): Video encoder configuration identifier
        rtsp_url (str): RTSP streaming URL for this profile
        vsc_name (str): Video source configuration name
        vsc_token (str): Video source configuration token
        vsc_source_token (str): Source token reference
        vsc_bounds (dict): Video source boundary settings
        vec_name (str): Video encoder configuration name
        vec_token (str): Video encoder configuration token
        vec_encoding (str): Video encoding format (e.g., H264, H265)
        vec_resolution (dict): Video resolution settings (width, height)
        vec_quality (int): Video quality setting
        vec_rate_control (dict): Rate control parameters
        vec_multicast (dict): Multicast configuration settings
        ptz_name (str): PTZ configuration name
        ptz_token (str): PTZ configuration token
        ptz_node_token (str): PTZ node identifier token
    """

    def __init__(self):
        # ONVIF Profile details
        self._name = ""
        self._token = ""
        self._fixed = False
        self._video_source_configuration = ""
        self._video_encoder_configuration = ""
        self._rtsp_url = ""

        # Video Source Configuration details
        self._vsc_name = ""
        self._vsc_token = ""
        self._vsc_source_token = ""
        self._vsc_bounds = {}

        # Video Encoder Configuration details
        self._vec_name = ""
        self._vec_token = ""
        self._vec_encoding = ""
        self._vec_resolution = {}
        self._vec_quality = 0
        self._vec_rate_control = {}
        self._vec_multicast = {}

        # PTZ Configuration details
        self._ptz_name = ""
        self._ptz_token = ""
        self._ptz_node_token = ""

        # Audio Encoder Configuration details
        self._aec_name = ""
        self._aec_token = ""
        self._aec_encoding = ""
        self._aec_bitrate = 0
        self._aec_sample_rate = 0

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
    def fixed(self) -> bool:
        """Get if the ONVIF profile is fixed."""
        return self._fixed
    @fixed.setter
    def fixed(self, fixed: bool):
        """Set if the ONVIF profile is fixed."""
        self._fixed = fixed

    @property
    def video_source_configuration(self) -> str:
        """Get the video source configuration of the ONVIF profile."""
        return self._video_source_configuration
    @video_source_configuration.setter
    def video_source_configuration(self, video_source_configuration: str):
        """Set the video source configuration of the ONVIF profile."""
        self._video_source_configuration = video_source_configuration

    @property
    def video_encoder_configuration(self) -> str:
        """Get the video encoder configuration of the ONVIF profile."""
        return self._video_encoder_configuration
    @video_encoder_configuration.setter
    def video_encoder_configuration(self, video_encoder_configuration: str):
        """Set the video encoder configuration of the ONVIF profile."""
        self._video_encoder_configuration = video_encoder_configuration

    @property
    def rtsp_url(self) -> str:
        """Get the RTSP URL of the ONVIF profile."""
        return self._rtsp_url
    @rtsp_url.setter
    def rtsp_url(self, rtsp_url: str):
        """Set the RTSP URL of the ONVIF profile."""
        self._rtsp_url = rtsp_url

    # Video Source Configuration details
    @property
    def vsc_name(self) -> str:
        """Get the name of the Video Source Configuration."""
        return self._vsc_name
    @vsc_name.setter
    def vsc_name(self, vsc_name: str):
        """Set the name of the Video Source Configuration."""
        self._vsc_name = vsc_name

    @property
    def vsc_token(self) -> str:
        """Get the token of the Video Source Configuration."""
        return self._vsc_token
    @vsc_token.setter
    def vsc_token(self, vsc_token: str):
        """Set the token of the Video Source Configuration."""
        self._vsc_token = vsc_token

    @property
    def vsc_source_token(self) -> str:
        """Get the source token of the Video Source Configuration."""
        return self._vsc_source_token
    @vsc_source_token.setter
    def vsc_source_token(self, vsc_source_token: str):
        """Set the source token of the Video Source Configuration."""
        self._vsc_source_token = vsc_source_token

    @property
    def vsc_bounds(self) -> dict:
        """Get the bounds of the Video Source Configuration."""
        return self._vsc_bounds
    @vsc_bounds.setter
    def vsc_bounds(self, vsc_bounds: dict):
        """Set the bounds of the Video Source Configuration."""
        self._vsc_bounds = vsc_bounds

    # Video Encoder Configuration details
    @property
    def vec_name(self) -> str:
        """Get the name of the Video Encoder Configuration."""
        return self._vec_name
    @vec_name.setter
    def vec_name(self, vec_name: str):
        """Set the name of the Video Encoder Configuration."""
        self._vec_name = vec_name

    @property
    def vec_token(self) -> str:
        """Get the token of the Video Encoder Configuration."""
        return self._vec_token
    @vec_token.setter
    def vec_token(self, vec_token: str):
        """Set the token of the Video Encoder Configuration."""
        self._vec_token = vec_token

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
    def vec_quality(self) -> int:
        """Get the quality of the Video Encoder Configuration."""
        return self._vec_quality
    @vec_quality.setter
    def vec_quality(self, vec_quality: int):
        """Set the quality of the Video Encoder Configuration."""
        self._vec_quality = vec_quality

    @property
    def vec_rate_control(self) -> dict:
        """Get the rate control of the Video Encoder Configuration."""
        return self._vec_rate_control
    @vec_rate_control.setter
    def vec_rate_control(self, vec_rate_control: dict):
        """Set the rate control of the Video Encoder Configuration."""
        self._vec_rate_control = vec_rate_control

    @property
    def vec_multicast(self) -> dict:
        """Get the multicast of the Video Encoder Configuration."""
        return self._vec_multicast
    @vec_multicast.setter
    def vec_multicast(self, vec_multicast: dict):
        """Set the multicast of the Video Encoder Configuration."""
        self._vec_multicast = vec_multicast

    # PTZ Configuration details
    @property
    def ptz_name(self) -> str:
        """Get the name of the PTZ Configuration."""
        return self._ptz_name
    @ptz_name.setter
    def ptz_name(self, ptz_name: str):
        """Set the name of the PTZ Configuration."""
        self._ptz_name = ptz_name

    @property
    def ptz_token(self) -> str:
        """Get the token of the PTZ Configuration."""
        return self._ptz_token
    @ptz_token.setter
    def ptz_token(self, ptz_token: str):
        """Set the token of the PTZ Configuration."""
        self._ptz_token = ptz_token

    @property
    def ptz_node_token(self) -> str:
        """Get the node token of the PTZ Configuration."""
        return self._ptz_node_token
    @ptz_node_token.setter
    def ptz_node_token(self, ptz_node_token: str):
        """Set the node token of the PTZ Configuration."""
        self._ptz_node_token = ptz_node_token

    @property
    def aec_name(self) -> str:
        """Get the name of the Audio Encoder Configuration."""
        return self._aec_name
    @aec_name.setter
    def aec_name(self, aec_name: str):
        """Set the name of the Audio Encoder Configuration."""
        self._aec_name = aec_name

    @property
    def aec_token(self) -> str:
        """Get the token of the Audio Encoder Configuration."""
        return self._aec_token
    @aec_token.setter
    def aec_token(self, aec_token: str):
        """Set the token of the Audio Encoder Configuration."""
        self._aec_token = aec_token

    @property
    def aec_encoding(self) -> str:
        """Get the encoding of the Audio Encoder Configuration."""
        return self._aec_encoding
    @aec_encoding.setter
    def aec_encoding(self, aec_encoding: str):
        """Set the encoding of the Audio Encoder Configuration."""
        self._aec_encoding = aec_encoding

    @property
    def aec_bitrate(self) -> int:
        """Get the bitrate of the Audio Encoder Configuration."""
        return self._aec_bitrate
    @aec_bitrate.setter
    def aec_bitrate(self, aec_bitrate: int):
        """Set the bitrate of the Audio Encoder Configuration."""
        self._aec_bitrate = aec_bitrate

    @property
    def aec_sample_rate(self) -> int:
        """Get the sample rate of the Audio Encoder Configuration."""
        return self._aec_sample_rate
    
    @aec_sample_rate.setter
    def aec_sample_rate(self, aec_sample_rate: int):
        """Set the sample rate of the Audio Encoder Configuration."""
        self._aec_sample_rate = aec_sample_rate


class ONVIFCameraDiscovery:
    """
    Singleton class for discovering ONVIF network cameras.
    
    Uses WS-Discovery protocol to find ONVIF-compliant cameras on the local network.
    """
    
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ONVIFCameraDiscovery, cls).__new__(cls)
        return cls._instance

    def __init__(self, json_file_path: str = None):
        """Initialize ONVIF camera discovery.
        
        Args:
            json_file_path: Path to the onvif_cameras.json file. If None, uses default path.
        """
        if not hasattr(self, "initialized"):
            self.initialized = True
            if json_file_path is None:
                # Default path relative to the tool's shared directory
                self.json_file_path = "/onvif/onvif_cameras.json"
            else:
                self.json_file_path = json_file_path
            logger.debug(f"ONVIFCameraDiscovery initialized with JSON file: {self.json_file_path}")

    def discover_cameras(self, verbose: bool = False) -> List[Camera]:
        """
        Retrieve discovered ONVIF cameras from the JSON file written by onvif_discovery_agent.
        
        Returns cameras with basic information (IP, port) without authentication.
        
        Args:
            verbose: Deprecated parameter, kept for backwards compatibility.
            
        Returns:
            List[Camera]: List of discovered cameras with IP and port information.
        """
        cameras = []
        
        try:
            with open(self.json_file_path, 'r') as f:
                data = json.load(f)
            
            discovered_cameras = data.get('cameras', [])
            
            logger.debug(f"Loaded {len(discovered_cameras)} camera(s) from {self.json_file_path}")
            
            for camera_data in discovered_cameras:
                ip = camera_data.get('ip')
                port = camera_data.get('port')
                
                if not ip or not port:
                    logger.warning(f"Skipping invalid camera entry: {camera_data}")
                    continue
                
                cameras.append(
                    Camera(
                        device_name=f"ONVIF Camera {ip}",
                        device_type=CameraType.NETWORK,
                        device_id=f"network_camera_{ip}_{port}",
                        status=CameraStatus.AVAILABLE,
                        details=NetworkCameraDetails(
                            ip=ip,
                            port=port,
                            authenticated=False,
                            profiles=[]
                        )
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

    def get_camera_profiles(self, camera_id: str, username: str, password: str) -> tuple[Camera, List['ONVIFProfile']]:
        """
        Authenticate with a specific ONVIF camera and retrieve its profiles.
        
        Args:
            camera_id: Camera identifier (e.g., "network_camera_192.168.1.100_80").
            username: ONVIF username for authentication.
            password: ONVIF password for authentication.
            verbose: Deprecated parameter, kept for backwards compatibility.
            
        Returns:
            Tuple of (Camera object with authenticated=True, List of ONVIFProfile objects).
            
        Raises:
            ValueError: If camera_id is invalid or camera not found.
            ConnectionError: If unable to connect to camera.
            Exception: For authentication or profile retrieval failures.
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
            profiles = self._camera_profiles(camera_obj, False)
            
            # Convert ONVIFProfile objects to CameraProfileInfo
            profile_infos = []
            for profile in profiles:
                resolution = None
                if profile.vec_resolution:
                    width = profile.vec_resolution.get('width')
                    height = profile.vec_resolution.get('height')
                    if width and height:
                        resolution = f"{width}x{height}"
                
                profile_infos.append(
                    CameraProfileInfo(
                        name=profile.name,
                        token=profile.token,
                        rtsp_url=profile.rtsp_url,
                        resolution=resolution,
                        encoding=profile.vec_encoding,
                        framerate=profile.vec_framerate_limit,
                        bitrate=profile.vec_bitrate_limit,
                        quality=profile.vec_quality,
                    )
                )
            
            # Create Camera object with authenticated=True and populated profiles
            camera = Camera(
                device_name=f"ONVIF Camera {ip}",
                device_type=CameraType.NETWORK,
                device_id=camera_id,
                status=CameraStatus.AVAILABLE,
                details=NetworkCameraDetails(
                    ip=ip,
                    port=port,
                    authenticated=True,
                    profiles=profile_infos
                )
            )
            
            logger.info(f"Successfully authenticated with camera {ip}:{port} and retrieved {len(profiles)} profile(s)")
            return camera, profiles
            
        except Exception as e:
            logger.error(f"Failed to authenticate with camera {ip}:{port}: {e}", exc_info=True)
            raise

    def _camera_profiles(self, client, verbose = False) -> list[ONVIFProfile]: # pylint: disable=too-many-statements, too-many-locals, too-many-branches
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

            # Fixed profile indicator
            if hasattr(profile, 'fixed') and profile.fixed is not None:
                onvif_profile.fixed = profile.fixed

            # Video Source Configuration
            if hasattr(profile, 'VideoSourceConfiguration') and profile.VideoSourceConfiguration:
                vsc = profile.VideoSourceConfiguration
                onvif_profile.vsc_name = vsc.Name
                onvif_profile.vsc_token = vsc.token
                onvif_profile.vsc_source_token = vsc.SourceToken
                if hasattr(vsc, 'Bounds') and vsc.Bounds:
                    onvif_profile.vsc_bounds = {
                        'x': vsc.Bounds.x,
                        'y': vsc.Bounds.y,
                        'width': vsc.Bounds.width,
                        'height': vsc.Bounds.height
                    }

            # Video Encoder Configuration
            if hasattr(profile, 'VideoEncoderConfiguration') and profile.VideoEncoderConfiguration:
                vec = profile.VideoEncoderConfiguration
                onvif_profile.vec_name = vec.Name
                onvif_profile.vec_token = vec.token
                onvif_profile.vec_encoding = vec.Encoding
                logger.debug("    Video Encoder:")
                logger.debug(f"      Name: {vec.Name}")
                logger.debug(f"      Token: {vec.token}")
                logger.debug(f"      Encoding: {vec.Encoding}")
                if hasattr(vec, 'Resolution') and vec.Resolution:
                    onvif_profile.vec_resolution = {
                        'width': vec.Resolution.Width,
                        'height': vec.Resolution.Height}
                    logger.debug(f"      Resolution: {vec.Resolution.Width}x{vec.Resolution.Height}")
                if hasattr(vec, 'Quality'):
                    onvif_profile.vec_quality = vec.Quality
                    logger.debug(f"      Quality: {vec.Quality}")
                if hasattr(vec, 'RateControl') and vec.RateControl:
                    onvif_profile.vec_framerate_limit = vec.RateControl.FrameRateLimit
                    onvif_profile.vec_bitrate_limit = vec.RateControl.BitrateLimit
                    logger.debug(f"      FrameRate Limit: {vec.RateControl.FrameRateLimit}")
                    logger.debug(f"      Bitrate Limit: {vec.RateControl.BitrateLimit}")
                    if hasattr(vec.RateControl, 'EncodingInterval'):
                        onvif_profile.vec_encoding_interval = vec.RateControl.EncodingInterval
                        logger.debug(f"      Encoding Interval: {vec.RateControl.EncodingInterval}")
                if hasattr(vec, 'H264') and vec.H264:
                    onvif_profile.vec_h264_profile = vec.H264.H264Profile
                    onvif_profile.vec_h264_gop_length = vec.H264.GovLength
                    logger.debug(f"      H264 Profile: {vec.H264.H264Profile}")
                    logger.debug(f"      GOP Size: {vec.H264.GovLength}")
                elif hasattr(vec, 'MPEG4') and vec.MPEG4:
                    onvif_profile.vec_mpeg4_profile = vec.MPEG4.Mpeg4Profile
                    onvif_profile.vec_mpeg4_gop_length = vec.MPEG4.Gov
                    logger.debug(f"      MPEG4 Profile: {vec.MPEG4.Mpeg4Profile}")
                    logger.debug(f"      GOP Size: {vec.MPEG4.GovLength}")

            # Audio Source Configuration
            if hasattr(profile, 'AudioSourceConfiguration') and profile.AudioSourceConfiguration:
                asc = profile.AudioSourceConfiguration
                onvif_profile.asc_name = asc.Name
                onvif_profile.asc_token = asc.token
                onvif_profile.asc_source_token = asc.SourceToken
                logger.debug(f"      Name: {asc.Name}")
                logger.debug(f"      Token: {asc.token}")
                logger.debug(f"      SourceToken: {asc.SourceToken}")

            # Audio Encoder Configuration
            if hasattr(profile, 'AudioEncoderConfiguration') and profile.AudioEncoderConfiguration:
                aec = profile.AudioEncoderConfiguration
                onvif_profile.aec_name = aec.Name
                onvif_profile.aec_token = aec.token
                onvif_profile.aec_encoding = aec.Encoding
                logger.debug("    Audio Encoder:")
                logger.debug(f"      Name: {aec.Name}")
                logger.debug(f"      Token: {aec.token}")
                logger.debug(f"      Encoding: {aec.Encoding}")
                if hasattr(aec, 'Bitrate'):
                    onvif_profile.aec_bitrate = aec.Bitrate
                    logger.debug(f"      Bitrate: {aec.Bitrate}")
                if hasattr(aec, 'SampleRate'):
                    onvif_profile.aec_sample_rate = aec.SampleRate
                    logger.debug(f"      SampleRate: {aec.SampleRate}")

            # PTZ Configuration
            if hasattr(profile, 'PTZConfiguration') and profile.PTZConfiguration:
                ptz = profile.PTZConfiguration
                onvif_profile.ptz_name = ptz.Name
                onvif_profile.ptz_token = ptz.token
                onvif_profile.ptz_node_token = ptz.NodeToken
                logger.debug("    PTZ:")
                logger.debug(f"      Name: {ptz.Name}")
                logger.debug(f"      Token: {ptz.token}")
                logger.debug(f"      NodeToken: {ptz.NodeToken}")

            # Get Stream URI for this profile
            try:
                stream_setup = {'Stream': 'RTP-Unicast', 'Transport': {'Protocol': 'RTSP'}}
                rtsp_uri = media_service.GetStreamUri({'StreamSetup': stream_setup,
                                    'ProfileToken': profile.token})
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

