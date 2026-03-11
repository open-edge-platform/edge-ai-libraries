import logging
import threading
from typing import List, Optional

from api.api_schemas import Camera, NetworkCameraDetails, USBCameraDetails
from camera import USBCameraDiscovery, ONVIFCameraDiscovery

logger = logging.getLogger("camera_manager")


class CameraManager:
    """
    Manager for camera device discovery and information retrieval.

    Implements singleton pattern using __new__ with double-checked locking.
    Create instances with CameraManager() to get the shared singleton instance.

    Responsibilities:
    * Discover USB cameras connected to the system
    * Discover network cameras on the local network
    * Provide unified access to all camera devices
    """

    _instance: Optional["CameraManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "CameraManager":
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # Protect against multiple initialization
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self.usb_discovery = USBCameraDiscovery()
        self.onvif_discovery = ONVIFCameraDiscovery()

        # Cached camera lists
        self._usb_cameras: List[Camera] = []
        self._network_cameras: List[Camera] = []

        # Shared lock protecting camera cache updates
        self._lock = threading.Lock()
        self.logger = logging.getLogger("CameraManager")

    def _update_camera_cache(
        self, cached_cameras: List[Camera], discovered_cameras: List[Camera]
    ) -> List[Camera]:
        """Update cached camera list by adding new cameras and removing unavailable ones.

        Args:
            cached_cameras: Current cached camera list.
            discovered_cameras: Newly discovered camera list.

        Returns:
            Updated camera list with new cameras added and unavailable ones removed.
        """
        # Create a dictionary of discovered cameras by device_id for quick lookup
        discovered_dict = {cam.device_id: cam for cam in discovered_cameras}

        # Start with cameras that are still available (exist in discovered list)
        updated_cameras = []
        for cached_cam in cached_cameras:
            if cached_cam.device_id in discovered_dict:
                # Camera still exists - keep the cached version (preserves profiles and other important data)
                updated_cameras.append(cached_cam)
                # Remove from dict so we know we've processed it
                del discovered_dict[cached_cam.device_id]
            else:
                self.logger.debug(
                    f"Camera {cached_cam.device_id} is no longer available, removing from cache"
                )

        # Add any new cameras that weren't in the cache
        for new_cam in discovered_dict.values():
            self.logger.debug(f"New camera discovered: {new_cam.device_id}")
            updated_cameras.append(new_cam)

        return updated_cameras

    def discover_usb_cameras(self) -> List[Camera]:
        """Discover USB cameras and update the cache.

        Performs live discovery and intelligently updates the cached list by:
        - Adding newly discovered cameras
        - Removing cameras that are no longer available
        - Keeping existing cameras that are still present

        Returns:
            List[Camera]: Updated list of USB cameras.
        """
        try:
            self.logger.debug("Discovering USB cameras")
            discovered_cameras = self.usb_discovery.discover_cameras()
            with self._lock:
                self._usb_cameras = self._update_camera_cache(
                    self._usb_cameras, discovered_cameras
                )
            self.logger.debug(f"Discovered {len(self._usb_cameras)} USB camera(s)")
        except Exception as e:
            self.logger.error(f"Failed USB camera discovery: {e}", exc_info=True)
            # On error, keep existing cache

        with self._lock:
            return self._usb_cameras.copy()

    def discover_network_cameras(self) -> List[Camera]:
        """Discover network cameras and update the cache.

        Performs live discovery and intelligently updates the cached list by:
        - Adding newly discovered cameras
        - Removing cameras that are no longer available
        - Keeping existing cameras that are still present

        Returns:
            List[Camera]: Updated list of network cameras.
        """
        try:
            self.logger.debug("Discovering network cameras")
            discovered_cameras = self.onvif_discovery.discover_cameras()
            with self._lock:
                self._network_cameras = self._update_camera_cache(
                    self._network_cameras, discovered_cameras
                )
            self.logger.debug(
                f"Discovered {len(self._network_cameras)} network camera(s)"
            )
        except Exception as e:
            self.logger.error(f"Failed network camera discovery: {e}", exc_info=True)
            # On error, keep existing cache

        with self._lock:
            return self._network_cameras.copy()

    def discover_all_cameras(self) -> List[Camera]:
        """Discover all cameras (both USB and network) and update the cache.

        Performs live discovery for both USB and network cameras and updates their caches.

        Returns:
            List[Camera]: Combined list of all discovered cameras.
        """
        # Discover USB cameras (updates cache)
        usb_cameras = self.discover_usb_cameras()

        # Discover network cameras (updates cache)
        network_cameras = self.discover_network_cameras()

        all_cameras = usb_cameras + network_cameras
        self.logger.debug(
            f"Discovered {len(usb_cameras)} USB and {len(network_cameras)} "
            f"network camera(s), total: {len(all_cameras)}"
        )
        return all_cameras

    def get_camera_by_id(self, camera_id: str) -> Optional[Camera]:
        """
        Get a specific camera by its ID from the cache.

        This method searches for a camera in both USB and network camera caches.
        It does not trigger new discovery - use discover_* methods first if needed.

        Args:
            camera_id: Camera identifier (e.g., "usb-camera-0" or "network-camera-192.168.1.100-80").

        Returns:
            Camera object if found, None otherwise.
        """
        self.logger.debug(f"Looking for camera {camera_id}")

        # Search in USB cameras
        with self._lock:
            for camera in self._usb_cameras:
                if camera.device_id == camera_id:
                    self.logger.debug(f"Found USB camera {camera_id}")
                    return camera

        # Search in network cameras
        with self._lock:
            for camera in self._network_cameras:
                if camera.device_id == camera_id:
                    self.logger.debug(f"Found network camera {camera_id}")
                    return camera

        self.logger.debug(f"Camera {camera_id} not found in cache")
        return None

    def get_camera_by_device_path(self, device_path: str) -> Optional[Camera]:
        """Get a USB camera by its device path from the cache.

        Searches cached USB cameras for one matching the given device path.
        Does not trigger new discovery.

        Args:
            device_path: Device path (e.g., "/dev/video0").

        Returns:
            Camera object if found, None otherwise.
        """
        if not device_path:
            return None

        with self._lock:
            for camera in self._usb_cameras:
                if camera.details is None:
                    continue
                if not isinstance(camera.details, USBCameraDetails):
                    continue
                if camera.details.device_path == device_path:
                    self.logger.debug(f"Found USB camera for device path {device_path}")
                    return camera

        self.logger.debug(f"No USB camera found for device path {device_path}")
        return None

    def get_camera_by_rtsp_url(self, rtsp_url: str) -> Optional[Camera]:
        """Get a network camera that has a profile matching the given RTSP URL.

        Searches cached network cameras for one with a profile whose rtsp_url
        matches. Does not trigger new discovery or authentication.

        Args:
            rtsp_url: RTSP URL to search for (e.g., "rtsp://192.168.1.100:554/stream1").

        Returns:
            Camera object if found, None otherwise.
        """
        if not rtsp_url:
            return None

        normalized = rtsp_url.strip()
        with self._lock:
            for camera in self._network_cameras:
                if camera.details is None:
                    continue
                if not isinstance(camera.details, NetworkCameraDetails):
                    continue
                for profile in camera.details.profiles:
                    if profile.rtsp_url == normalized:
                        self.logger.debug(
                            f"Found network camera for RTSP URL {rtsp_url}"
                        )
                        return camera

        self.logger.debug(f"No network camera found for RTSP URL {rtsp_url}")
        return None

    def load_camera_profiles(
        self, camera_id: str, username: str, password: str
    ) -> Camera:
        """
        Load ONVIF profiles from a network camera and update the cached camera.

        This method authenticates with the camera, retrieves all available ONVIF profiles,
        and updates the cached camera object with the profile information.

        Args:
            camera_id: Camera identifier (e.g., "network-camera-192.168.1.100-80").
            username: ONVIF username for authentication.
            password: ONVIF password for authentication.

        Returns:
            Camera: Updated Camera object with populated profiles in details.profiles.

        Raises:
            ValueError: If camera_id is invalid or camera not found in cache.
            ConnectionError: If unable to connect to camera.
            Exception: For authentication or profile retrieval failures.
        """
        self.logger.debug(f"Loading profiles for camera {camera_id}")

        if not camera_id.startswith("network-camera-"):
            error_msg = "Invalid camera type - only network cameras supported"
            self.logger.error(error_msg)
            raise ValueError(error_msg)

        with self._lock:
            if camera_id not in [cam.device_id for cam in self._network_cameras]:
                error_msg = f"Camera with ID {camera_id} not found in cached cameras"
                self.logger.error(error_msg)
                raise ValueError(error_msg)

        # Load camera profiles from device
        authenticated_camera = self.onvif_discovery.load_camera_profiles(
            camera_id, username, password
        )

        # Update the cached network cameras list
        with self._lock:
            for i, camera in enumerate(self._network_cameras):
                if camera.device_id == camera_id:
                    self._network_cameras[i] = authenticated_camera
                    self.logger.debug(
                        f"Updated cached camera {camera_id} with profile information"
                    )
                    break

        return authenticated_camera

    def get_encoding_for_rtsp_url(self, rtsp_url: str) -> Optional[str]:
        """Get encoding for a given RTSP URL from cached ONVIF profiles.

        Network camera profiles (including `encoding` and `rtsp_url`) are only
        populated after successful authentication via `load_camera_profiles()`.
        This method does not trigger discovery/authentication; it only searches
        the in-memory cache.

        Args:
            rtsp_url: RTSP URL that appears in a profile (e.g. "rtsp://.../stream")

        Returns:
            Encoding string from the matching profile (e.g. "H264", "H265"),
            or None if not found.
        """
        if not rtsp_url:
            return None

        normalized = rtsp_url.strip()
        with self._lock:
            for camera in self._network_cameras:
                if camera.details is None:
                    continue
                if not isinstance(camera.details, NetworkCameraDetails):
                    continue
                for profile in camera.details.profiles:
                    if profile.rtsp_url == normalized:
                        return profile.encoding

        return None
