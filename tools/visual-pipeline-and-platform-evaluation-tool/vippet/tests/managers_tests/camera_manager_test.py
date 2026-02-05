import unittest
from typing import cast
from unittest.mock import patch, MagicMock

from api.api_schemas import (
    Camera,
    CameraType,
    USBCameraDetails,
    NetworkCameraDetails,
    CameraProfileInfo,
)
from managers.camera_manager import CameraManager


class TestCameraManager(unittest.TestCase):
    """
    Unit tests for CameraManager.

    The tests focus on:
      * singleton pattern implementation,
      * camera discovery (USB and network),
      * cache update logic,
      * profile loading for network cameras,
      * error handling.
    """

    def setUp(self):
        """Reset singleton state before each test."""
        CameraManager._instance = None

    def tearDown(self):
        """Reset singleton state after each test."""
        CameraManager._instance = None

    def _build_camera(
        self,
        device_id: str,
        camera_type: CameraType = CameraType.USB,
        name: str = "Test Camera",
        profiles: list | None = None,
    ) -> Camera:
        """Helper that constructs a Camera instance."""
        if camera_type == CameraType.USB:
            details = USBCameraDetails(
                device_path=f"/dev/video{device_id[-1]}", resolution="1920x1080"
            )
        else:
            # Convert string profile names to CameraProfileInfo objects
            profile_objects = []
            if profiles:
                for profile_name in profiles:
                    if isinstance(profile_name, str):
                        profile_objects.append(
                            CameraProfileInfo(
                                name=profile_name,
                                rtsp_url=f"rtsp://192.168.1.100:554/{profile_name.lower()}",
                                resolution="1920x1080",
                                encoding="H264",
                                framerate=30,
                                bitrate=4096,
                            )
                        )
                    else:
                        profile_objects.append(profile_name)

            details = NetworkCameraDetails(
                ip="192.168.1.100", port=80, profiles=profile_objects
            )
        return Camera(
            device_id=device_id,
            device_name=name,
            device_type=camera_type,
            details=details,
        )

    # ------------------------------------------------------------------
    # Singleton tests
    # ------------------------------------------------------------------

    def test_singleton_returns_same_instance(self):
        """CameraManager() should return the same instance on multiple calls."""
        instance1 = CameraManager()
        instance2 = CameraManager()
        self.assertIs(instance1, instance2)

    def test_singleton_only_initializes_once(self):
        """Multiple calls should not re-initialize the singleton."""
        manager1 = CameraManager()
        original_usb_discovery = manager1.usb_discovery
        original_onvif_discovery = manager1.onvif_discovery

        manager2 = CameraManager()
        self.assertIs(manager2.usb_discovery, original_usb_discovery)
        self.assertIs(manager2.onvif_discovery, original_onvif_discovery)

    # ------------------------------------------------------------------
    # Cache update logic tests
    # ------------------------------------------------------------------

    def test_update_camera_cache_keeps_existing_cameras(self):
        """
        _update_camera_cache should keep cameras that are still discovered.
        """
        manager = CameraManager()

        cached_cam1 = self._build_camera("usb_camera_1", CameraType.USB)
        cached_cam2 = self._build_camera("usb_camera_2", CameraType.USB)
        cached_cameras = [cached_cam1, cached_cam2]

        discovered_cam1 = self._build_camera("usb_camera_1", CameraType.USB)
        discovered_cam2 = self._build_camera("usb_camera_2", CameraType.USB)
        discovered_cameras = [discovered_cam1, discovered_cam2]

        updated = manager._update_camera_cache(cached_cameras, discovered_cameras)

        self.assertEqual(len(updated), 2)
        # Should keep cached versions (preserves profiles)
        self.assertIs(updated[0], cached_cam1)
        self.assertIs(updated[1], cached_cam2)

    def test_update_camera_cache_removes_unavailable_cameras(self):
        """
        _update_camera_cache should remove cameras that are no longer discovered.
        """
        manager = CameraManager()

        cached_cam1 = self._build_camera("usb_camera_1", CameraType.USB)
        cached_cam2 = self._build_camera("usb_camera_2", CameraType.USB)
        cached_cameras = [cached_cam1, cached_cam2]

        # Only camera 1 is discovered this time
        discovered_cam1 = self._build_camera("usb_camera_1", CameraType.USB)
        discovered_cameras = [discovered_cam1]

        updated = manager._update_camera_cache(cached_cameras, discovered_cameras)

        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0].device_id, "usb_camera_1")

    def test_update_camera_cache_adds_new_cameras(self):
        """
        _update_camera_cache should add newly discovered cameras.
        """
        manager = CameraManager()

        cached_cam1 = self._build_camera("usb_camera_1", CameraType.USB)
        cached_cameras = [cached_cam1]

        discovered_cam1 = self._build_camera("usb_camera_1", CameraType.USB)
        discovered_cam2 = self._build_camera("usb_camera_2", CameraType.USB)
        discovered_cameras = [discovered_cam1, discovered_cam2]

        updated = manager._update_camera_cache(cached_cameras, discovered_cameras)

        self.assertEqual(len(updated), 2)
        device_ids = {cam.device_id for cam in updated}
        self.assertIn("usb_camera_1", device_ids)
        self.assertIn("usb_camera_2", device_ids)

    def test_update_camera_cache_empty_discovered_clears_cache(self):
        """
        _update_camera_cache should clear cache when no cameras are discovered.
        """
        manager = CameraManager()

        cached_cam1 = self._build_camera("usb_camera_1", CameraType.USB)
        cached_cam2 = self._build_camera("usb_camera_2", CameraType.USB)
        cached_cameras = [cached_cam1, cached_cam2]

        discovered_cameras = []

        updated = manager._update_camera_cache(cached_cameras, discovered_cameras)

        self.assertEqual(len(updated), 0)

    def test_update_camera_cache_empty_cache_with_discoveries(self):
        """
        _update_camera_cache should add all discovered cameras when cache is empty.
        """
        manager = CameraManager()

        cached_cameras = []

        discovered_cam1 = self._build_camera("usb_camera_1", CameraType.USB)
        discovered_cam2 = self._build_camera("usb_camera_2", CameraType.USB)
        discovered_cameras = [discovered_cam1, discovered_cam2]

        updated = manager._update_camera_cache(cached_cameras, discovered_cameras)

        self.assertEqual(len(updated), 2)
        self.assertIn(discovered_cam1, updated)
        self.assertIn(discovered_cam2, updated)

    # ------------------------------------------------------------------
    # USB camera discovery tests
    # ------------------------------------------------------------------

    @patch("managers.camera_manager.USBCameraDiscovery")
    def test_discover_usb_cameras_returns_discovered_cameras(
        self, mock_usb_discovery_cls
    ):
        """
        discover_usb_cameras should discover USB cameras and update cache.
        """
        mock_discovery = MagicMock()
        cam1 = self._build_camera("usb_camera_1", CameraType.USB)
        cam2 = self._build_camera("usb_camera_2", CameraType.USB)
        mock_discovery.discover_cameras.return_value = [cam1, cam2]
        mock_usb_discovery_cls.return_value = mock_discovery

        manager = CameraManager()
        result = manager.discover_usb_cameras()

        self.assertEqual(len(result), 2)
        device_ids = {cam.device_id for cam in result}
        self.assertIn("usb_camera_1", device_ids)
        self.assertIn("usb_camera_2", device_ids)
        mock_discovery.discover_cameras.assert_called_once()

    @patch("managers.camera_manager.USBCameraDiscovery")
    def test_discover_usb_cameras_updates_cache_correctly(self, mock_usb_discovery_cls):
        """
        discover_usb_cameras should update internal cache.
        """
        mock_discovery = MagicMock()
        cam1 = self._build_camera("usb_camera_1", CameraType.USB)
        mock_discovery.discover_cameras.return_value = [cam1]
        mock_usb_discovery_cls.return_value = mock_discovery

        manager = CameraManager()

        # First discovery
        result1 = manager.discover_usb_cameras()
        self.assertEqual(len(result1), 1)

        # Second discovery with different camera
        cam2 = self._build_camera("usb_camera_2", CameraType.USB)
        mock_discovery.discover_cameras.return_value = [cam2]
        result2 = manager.discover_usb_cameras()

        self.assertEqual(len(result2), 1)
        self.assertEqual(result2[0].device_id, "usb_camera_2")

    @patch("managers.camera_manager.USBCameraDiscovery")
    def test_discover_usb_cameras_keeps_cache_on_exception(
        self, mock_usb_discovery_cls
    ):
        """
        discover_usb_cameras should keep existing cache on discovery exception.
        """
        mock_discovery = MagicMock()
        cam1 = self._build_camera("usb_camera_1", CameraType.USB)
        mock_discovery.discover_cameras.return_value = [cam1]
        mock_usb_discovery_cls.return_value = mock_discovery

        manager = CameraManager()

        # First successful discovery
        result1 = manager.discover_usb_cameras()
        self.assertEqual(len(result1), 1)

        # Second discovery fails
        mock_discovery.discover_cameras.side_effect = RuntimeError("Discovery failed")
        result2 = manager.discover_usb_cameras()

        # Should still return cached camera
        self.assertEqual(len(result2), 1)
        self.assertEqual(result2[0].device_id, "usb_camera_1")

    @patch("managers.camera_manager.USBCameraDiscovery")
    def test_discover_usb_cameras_returns_copy_of_cache(self, mock_usb_discovery_cls):
        """
        discover_usb_cameras should return a copy to prevent external modification.
        """
        mock_discovery = MagicMock()
        cam1 = self._build_camera("usb_camera_1", CameraType.USB)
        mock_discovery.discover_cameras.return_value = [cam1]
        mock_usb_discovery_cls.return_value = mock_discovery

        manager = CameraManager()
        result1 = manager.discover_usb_cameras()
        result2 = manager.discover_usb_cameras()

        self.assertIsNot(result1, result2)
        self.assertIsNot(result1, manager._usb_cameras)

    # ------------------------------------------------------------------
    # Network camera discovery tests
    # ------------------------------------------------------------------

    @patch("managers.camera_manager.ONVIFCameraDiscovery")
    def test_discover_network_cameras_returns_discovered_cameras(
        self, mock_onvif_discovery_cls
    ):
        """
        discover_network_cameras should discover network cameras and update cache.
        """
        mock_discovery = MagicMock()
        cam1 = self._build_camera("network_camera_192.168.1.100_80", CameraType.NETWORK)
        cam2 = self._build_camera("network_camera_192.168.1.101_80", CameraType.NETWORK)
        mock_discovery.discover_cameras.return_value = [cam1, cam2]
        mock_onvif_discovery_cls.return_value = mock_discovery

        manager = CameraManager()
        result = manager.discover_network_cameras()

        self.assertEqual(len(result), 2)
        device_ids = {cam.device_id for cam in result}
        self.assertIn("network_camera_192.168.1.100_80", device_ids)
        self.assertIn("network_camera_192.168.1.101_80", device_ids)
        mock_discovery.discover_cameras.assert_called_once()

    @patch("managers.camera_manager.ONVIFCameraDiscovery")
    def test_discover_network_cameras_updates_cache_correctly(
        self, mock_onvif_discovery_cls
    ):
        """
        discover_network_cameras should update internal cache.
        """
        mock_discovery = MagicMock()
        cam1 = self._build_camera("network_camera_192.168.1.100_80", CameraType.NETWORK)
        mock_discovery.discover_cameras.return_value = [cam1]
        mock_onvif_discovery_cls.return_value = mock_discovery

        manager = CameraManager()

        # First discovery
        result1 = manager.discover_network_cameras()
        self.assertEqual(len(result1), 1)

        # Second discovery with different camera
        cam2 = self._build_camera("network_camera_192.168.1.101_80", CameraType.NETWORK)
        mock_discovery.discover_cameras.return_value = [cam2]
        result2 = manager.discover_network_cameras()

        self.assertEqual(len(result2), 1)
        self.assertEqual(result2[0].device_id, "network_camera_192.168.1.101_80")

    @patch("managers.camera_manager.ONVIFCameraDiscovery")
    def test_discover_network_cameras_keeps_cache_on_exception(
        self, mock_onvif_discovery_cls
    ):
        """
        discover_network_cameras should keep existing cache on discovery exception.
        """
        mock_discovery = MagicMock()
        cam1 = self._build_camera("network_camera_192.168.1.100_80", CameraType.NETWORK)
        mock_discovery.discover_cameras.return_value = [cam1]
        mock_onvif_discovery_cls.return_value = mock_discovery

        manager = CameraManager()

        # First successful discovery
        result1 = manager.discover_network_cameras()
        self.assertEqual(len(result1), 1)

        # Second discovery fails
        mock_discovery.discover_cameras.side_effect = RuntimeError("Discovery failed")
        result2 = manager.discover_network_cameras()

        # Should still return cached camera
        self.assertEqual(len(result2), 1)
        self.assertEqual(result2[0].device_id, "network_camera_192.168.1.100_80")

    @patch("managers.camera_manager.ONVIFCameraDiscovery")
    def test_discover_network_cameras_returns_copy_of_cache(
        self, mock_onvif_discovery_cls
    ):
        """
        discover_network_cameras should return a copy to prevent external modification.
        """
        mock_discovery = MagicMock()
        cam1 = self._build_camera("network_camera_192.168.1.100_80", CameraType.NETWORK)
        mock_discovery.discover_cameras.return_value = [cam1]
        mock_onvif_discovery_cls.return_value = mock_discovery

        manager = CameraManager()
        result1 = manager.discover_network_cameras()
        result2 = manager.discover_network_cameras()

        self.assertIsNot(result1, result2)
        self.assertIsNot(result1, manager._network_cameras)

    # ------------------------------------------------------------------
    # Discover all cameras tests
    # ------------------------------------------------------------------

    @patch("managers.camera_manager.ONVIFCameraDiscovery")
    @patch("managers.camera_manager.USBCameraDiscovery")
    def test_discover_all_cameras_returns_combined_list(
        self, mock_usb_discovery_cls, mock_onvif_discovery_cls
    ):
        """
        discover_all_cameras should return combined list of USB and network cameras.
        """
        mock_usb_discovery = MagicMock()
        usb_cam1 = self._build_camera("usb_camera_1", CameraType.USB)
        usb_cam2 = self._build_camera("usb_camera_2", CameraType.USB)
        mock_usb_discovery.discover_cameras.return_value = [usb_cam1, usb_cam2]
        mock_usb_discovery_cls.return_value = mock_usb_discovery

        mock_onvif_discovery = MagicMock()
        net_cam1 = self._build_camera(
            "network_camera_192.168.1.100_80", CameraType.NETWORK
        )
        mock_onvif_discovery.discover_cameras.return_value = [net_cam1]
        mock_onvif_discovery_cls.return_value = mock_onvif_discovery

        manager = CameraManager()
        result = manager.discover_all_cameras()

        self.assertEqual(len(result), 3)
        device_ids = {cam.device_id for cam in result}
        self.assertIn("usb_camera_1", device_ids)
        self.assertIn("usb_camera_2", device_ids)
        self.assertIn("network_camera_192.168.1.100_80", device_ids)

    @patch("managers.camera_manager.ONVIFCameraDiscovery")
    @patch("managers.camera_manager.USBCameraDiscovery")
    def test_discover_all_cameras_empty_when_no_cameras(
        self, mock_usb_discovery_cls, mock_onvif_discovery_cls
    ):
        """
        discover_all_cameras should return empty list when no cameras found.
        """
        mock_usb_discovery = MagicMock()
        mock_usb_discovery.discover_cameras.return_value = []
        mock_usb_discovery_cls.return_value = mock_usb_discovery

        mock_onvif_discovery = MagicMock()
        mock_onvif_discovery.discover_cameras.return_value = []
        mock_onvif_discovery_cls.return_value = mock_onvif_discovery

        manager = CameraManager()
        result = manager.discover_all_cameras()

        self.assertEqual(len(result), 0)

    # ------------------------------------------------------------------
    # Get camera by ID tests
    # ------------------------------------------------------------------

    @patch("managers.camera_manager.USBCameraDiscovery")
    @patch("managers.camera_manager.ONVIFCameraDiscovery")
    def test_get_camera_by_id_returns_usb_camera(
        self, mock_onvif_discovery_cls, mock_usb_discovery_cls
    ):
        """
        get_camera_by_id should return a USB camera if found in cache.
        """
        mock_usb_discovery = MagicMock()
        mock_onvif_discovery = MagicMock()
        mock_usb_discovery_cls.return_value = mock_usb_discovery
        mock_onvif_discovery_cls.return_value = mock_onvif_discovery

        usb_camera = self._build_camera("usb_camera_0", CameraType.USB)
        mock_usb_discovery.discover_cameras.return_value = [usb_camera]
        mock_onvif_discovery.discover_cameras.return_value = []

        manager = CameraManager()
        manager.discover_all_cameras()  # Populate cache

        result = manager.get_camera_by_id("usb_camera_0")

        self.assertIsNotNone(result)
        assert result is not None  # for type checkers
        self.assertEqual(result.device_id, "usb_camera_0")
        self.assertEqual(result.device_type, CameraType.USB)

    @patch("managers.camera_manager.USBCameraDiscovery")
    @patch("managers.camera_manager.ONVIFCameraDiscovery")
    def test_get_camera_by_id_returns_network_camera(
        self, mock_onvif_discovery_cls, mock_usb_discovery_cls
    ):
        """
        get_camera_by_id should return a network camera if found in cache.
        """
        mock_usb_discovery = MagicMock()
        mock_onvif_discovery = MagicMock()
        mock_usb_discovery_cls.return_value = mock_usb_discovery
        mock_onvif_discovery_cls.return_value = mock_onvif_discovery

        network_camera = self._build_camera(
            "network_camera_192.168.1.100_80", CameraType.NETWORK
        )
        mock_usb_discovery.discover_cameras.return_value = []
        mock_onvif_discovery.discover_cameras.return_value = [network_camera]

        manager = CameraManager()
        manager.discover_all_cameras()  # Populate cache

        result = manager.get_camera_by_id("network_camera_192.168.1.100_80")

        self.assertIsNotNone(result)
        assert result is not None  # for type checkers
        self.assertEqual(result.device_id, "network_camera_192.168.1.100_80")
        self.assertEqual(result.device_type, CameraType.NETWORK)

    @patch("managers.camera_manager.USBCameraDiscovery")
    @patch("managers.camera_manager.ONVIFCameraDiscovery")
    def test_get_camera_by_id_returns_none_for_unknown_camera(
        self, mock_onvif_discovery_cls, mock_usb_discovery_cls
    ):
        """
        get_camera_by_id should return None if camera not found in cache.
        """
        mock_usb_discovery = MagicMock()
        mock_onvif_discovery = MagicMock()
        mock_usb_discovery_cls.return_value = mock_usb_discovery
        mock_onvif_discovery_cls.return_value = mock_onvif_discovery

        mock_usb_discovery.discover_cameras.return_value = []
        mock_onvif_discovery.discover_cameras.return_value = []

        manager = CameraManager()
        manager.discover_all_cameras()  # Populate (empty) cache

        result = manager.get_camera_by_id("nonexistent_camera")

        self.assertIsNone(result)

    @patch("managers.camera_manager.USBCameraDiscovery")
    @patch("managers.camera_manager.ONVIFCameraDiscovery")
    def test_get_camera_by_id_works_with_mixed_cameras(
        self, mock_onvif_discovery_cls, mock_usb_discovery_cls
    ):
        """
        get_camera_by_id should find cameras from both USB and network caches.
        """
        mock_usb_discovery = MagicMock()
        mock_onvif_discovery = MagicMock()
        mock_usb_discovery_cls.return_value = mock_usb_discovery
        mock_onvif_discovery_cls.return_value = mock_onvif_discovery

        usb_camera = self._build_camera("usb_camera_0", CameraType.USB)
        network_camera = self._build_camera(
            "network_camera_192.168.1.100_80", CameraType.NETWORK
        )
        mock_usb_discovery.discover_cameras.return_value = [usb_camera]
        mock_onvif_discovery.discover_cameras.return_value = [network_camera]

        manager = CameraManager()
        manager.discover_all_cameras()  # Populate cache

        # Should find USB camera
        result_usb = manager.get_camera_by_id("usb_camera_0")
        self.assertIsNotNone(result_usb)
        assert result_usb is not None  # for type checkers
        self.assertEqual(result_usb.device_type, CameraType.USB)

        # Should find network camera
        result_network = manager.get_camera_by_id("network_camera_192.168.1.100_80")
        self.assertIsNotNone(result_network)
        assert result_network is not None  # for type checkers
        self.assertEqual(result_network.device_type, CameraType.NETWORK)

        # Should not find nonexistent camera
        result_none = manager.get_camera_by_id("nonexistent")
        self.assertIsNone(result_none)

    # ------------------------------------------------------------------
    # Load camera profiles tests
    # ------------------------------------------------------------------

    @patch("managers.camera_manager.ONVIFCameraDiscovery")
    def test_load_camera_profiles_returns_updated_camera(
        self, mock_onvif_discovery_cls
    ):
        """
        load_camera_profiles should authenticate and return camera with profiles.
        """
        mock_discovery = MagicMock()

        # Initial camera without profiles
        cam = self._build_camera("network_camera_192.168.1.100_80", CameraType.NETWORK)
        mock_discovery.discover_cameras.return_value = [cam]

        # Camera with loaded profiles
        cam_with_profiles = self._build_camera(
            "network_camera_192.168.1.100_80",
            CameraType.NETWORK,
            profiles=["Profile1", "Profile2"],
        )
        mock_discovery.load_camera_profiles.return_value = cam_with_profiles

        mock_onvif_discovery_cls.return_value = mock_discovery

        manager = CameraManager()
        # Discover first to populate cache
        manager.discover_network_cameras()

        result = manager.load_camera_profiles(
            "network_camera_192.168.1.100_80", "admin", "password123"
        )

        self.assertEqual(result.device_id, "network_camera_192.168.1.100_80")
        self.assertIsInstance(result.details, NetworkCameraDetails)
        details = cast(NetworkCameraDetails, result.details)
        self.assertEqual(len(details.profiles), 2)
        mock_discovery.load_camera_profiles.assert_called_once_with(
            "network_camera_192.168.1.100_80", "admin", "password123"
        )

    @patch("managers.camera_manager.ONVIFCameraDiscovery")
    def test_load_camera_profiles_updates_cache(self, mock_onvif_discovery_cls):
        """
        load_camera_profiles should update the cached camera with profile info.
        """
        mock_discovery = MagicMock()

        # Initial camera without profiles
        cam = self._build_camera("network_camera_192.168.1.100_80", CameraType.NETWORK)
        mock_discovery.discover_cameras.return_value = [cam]

        # Camera with loaded profiles
        cam_with_profiles = self._build_camera(
            "network_camera_192.168.1.100_80",
            CameraType.NETWORK,
            profiles=["Profile1"],
        )
        mock_discovery.load_camera_profiles.return_value = cam_with_profiles

        mock_onvif_discovery_cls.return_value = mock_discovery

        manager = CameraManager()
        manager.discover_network_cameras()

        # Load profiles
        manager.load_camera_profiles(
            "network_camera_192.168.1.100_80", "admin", "password123"
        )

        # Verify cache is updated
        self.assertEqual(len(manager._network_cameras), 1)
        cached_cam = manager._network_cameras[0]
        self.assertIsInstance(cached_cam.details, NetworkCameraDetails)
        details = cast(NetworkCameraDetails, cached_cam.details)
        self.assertEqual(len(details.profiles), 1)

    @patch("managers.camera_manager.ONVIFCameraDiscovery")
    def test_load_camera_profiles_raises_error_for_usb_camera(
        self, mock_onvif_discovery_cls
    ):
        """
        load_camera_profiles should raise ValueError for USB cameras.
        """
        mock_discovery = MagicMock()
        mock_onvif_discovery_cls.return_value = mock_discovery

        manager = CameraManager()

        with self.assertRaises(ValueError) as ctx:
            manager.load_camera_profiles("usb_camera_1", "admin", "password")

        self.assertIn("only network cameras supported", str(ctx.exception))

    @patch("managers.camera_manager.ONVIFCameraDiscovery")
    def test_load_camera_profiles_raises_error_for_unknown_camera(
        self, mock_onvif_discovery_cls
    ):
        """
        load_camera_profiles should raise ValueError for camera not in cache.
        """
        mock_discovery = MagicMock()
        mock_discovery.discover_cameras.return_value = []
        mock_onvif_discovery_cls.return_value = mock_discovery

        manager = CameraManager()
        manager.discover_network_cameras()

        with self.assertRaises(ValueError) as ctx:
            manager.load_camera_profiles(
                "network_camera_192.168.1.100_80", "admin", "password"
            )

        self.assertIn("not found in cached cameras", str(ctx.exception))

    @patch("managers.camera_manager.ONVIFCameraDiscovery")
    def test_load_camera_profiles_propagates_connection_errors(
        self, mock_onvif_discovery_cls
    ):
        """
        load_camera_profiles should propagate exceptions from ONVIF discovery.
        """
        mock_discovery = MagicMock()

        # Camera in cache
        cam = self._build_camera("network_camera_192.168.1.100_80", CameraType.NETWORK)
        mock_discovery.discover_cameras.return_value = [cam]

        # Loading profiles fails
        mock_discovery.load_camera_profiles.side_effect = ConnectionError(
            "Unable to connect"
        )

        mock_onvif_discovery_cls.return_value = mock_discovery

        manager = CameraManager()
        manager.discover_network_cameras()

        with self.assertRaises(ConnectionError) as ctx:
            manager.load_camera_profiles(
                "network_camera_192.168.1.100_80", "admin", "password"
            )

        self.assertIn("Unable to connect", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
