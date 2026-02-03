import logging
import sys
from typing import List, Optional

from api.api_schemas import Camera
from camera import USBCameraDiscovery, ONVIFCameraDiscovery

logger = logging.getLogger("camera_manager")

# Singleton instance for CameraManager
_camera_manager_instance: Optional["CameraManager"] = None


def get_camera_manager() -> "CameraManager":
    """
    Returns the singleton instance of CameraManager.
    If it cannot be created, logs an error and exits the application.
    """
    global _camera_manager_instance
    if _camera_manager_instance is None:
        try:
            _camera_manager_instance = CameraManager()
        except Exception as e:
            logger.error(f"Failed to initialize CameraManager: {e}")
            sys.exit(1)
    return _camera_manager_instance


class CameraManager:
    """
    Manager for camera device discovery and information retrieval.

    Responsibilities:
    * Discover USB cameras connected to the system
    * Discover network cameras on the local network
    * Provide unified access to all camera devices
    """

    def __init__(self) -> None:
        """Initialize the CameraManager."""
        self.logger = logging.getLogger("CameraManager")
        self.usb_discovery = USBCameraDiscovery()
        self.onvif_discovery = ONVIFCameraDiscovery()
        
        # Store discovered cameras
        self._usb_cameras: List[Camera] = []
        self._network_cameras: List[Camera] = []
        
        self.logger.info("CameraManager initialized")
    
    def _update_camera_cache(self, cached_cameras: List[Camera], discovered_cameras: List[Camera]) -> List[Camera]:
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
                self.logger.info(f"Camera {cached_cam.device_id} is no longer available, removing from cache")
        
        # Add any new cameras that weren't in the cache
        for new_cam in discovered_dict.values():
            self.logger.info(f"New camera discovered: {new_cam.device_id}")
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
            self._usb_cameras = self._update_camera_cache(self._usb_cameras, discovered_cameras)
            self.logger.info(f"Discovered {len(self._usb_cameras)} USB camera(s)")
        except Exception as e:
            self.logger.error(f"Failed USB camera discovery: {e}", exc_info=True)
            # On error, keep existing cache
        
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
            discovered_cameras = self.onvif_discovery.discover_cameras(verbose=False)
            self._network_cameras = self._update_camera_cache(self._network_cameras, discovered_cameras)
            self.logger.info(f"Discovered {len(self._network_cameras)} network camera(s)")
        except Exception as e:
            self.logger.error(f"Failed network camera discovery: {e}", exc_info=True)
            # On error, keep existing cache
        
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

    def get_camera_profiles(self, camera_id: str, username: str, password: str):
        """
        Retrieve ONVIF profiles from a specific camera and update the cached camera list.
        
        Args:
            camera_id: Camera identifier (e.g., "network_camera_192.168.1.100_80").
            username: ONVIF username for authentication.
            password: ONVIF password for authentication.
            
        Returns:
            Tuple of (Updated Camera object with profiles, List of ONVIFProfile objects).
            
        Raises:
            ValueError: If camera_id is invalid or camera not found.
            ConnectionError: If unable to connect to camera.
            Exception: For authentication or profile retrieval failures.
        """
        self.logger.debug(f"Retrieving profiles for camera {camera_id}")

        if camera_id not in [cam.device_id for cam in self._network_cameras]:
            error_msg = f"Camera with ID {camera_id} not found in cached cameras"
            self.logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Get camera profiles
        authenticated_camera, profiles = self.onvif_discovery.get_camera_profiles(
            camera_id, username, password
        )
        
        # Update the cached network cameras list
        for i, camera in enumerate(self._network_cameras):
            if camera.device_id == camera_id:
                self._network_cameras[i] = authenticated_camera
                self.logger.info(f"Updated cached camera {camera_id} with profile information")
                break
        
        return authenticated_camera, profiles
