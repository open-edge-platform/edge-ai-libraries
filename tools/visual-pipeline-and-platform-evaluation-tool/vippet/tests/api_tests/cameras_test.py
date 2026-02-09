import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api.routes.cameras import router as cameras_router


class TestCamerasAPI(unittest.TestCase):
    """
    Integration-style unit tests for the cameras HTTP API.

    The tests use FastAPI's TestClient and patch the CameraManager singleton
    so we can precisely control the behavior of the underlying manager without
    touching its real implementation.
    """

    @classmethod
    def setUpClass(cls):
        """
        Build a minimal FastAPI app and mount the cameras router once for all tests.

        This mirrors the approach used in other test files to:
        * exercise the actual path/operation configuration of the router,
        * verify serialization / response models and HTTP codes,
        * keep the tests fast and side-effect free by patching dependencies.
        """
        app = FastAPI()
        app.include_router(cameras_router, prefix="/cameras")
        cls.client = TestClient(app)

    @staticmethod
    def _make_usb_camera(device_id, device_name, device_path="/dev/video0"):
        """Helper method to create a mock USB camera."""
        return {
            "device_id": device_id,
            "device_name": device_name,
            "device_type": "USB",
            "details": {"device_path": device_path, "resolution": "1920x1080"},
        }

    @staticmethod
    def _make_network_camera(device_id, device_name, ip, port=80, profiles=None):
        """Helper method to create a mock network camera."""
        return {
            "device_id": device_id,
            "device_name": device_name,
            "device_type": "NETWORK",
            "details": {
                "ip": ip,
                "port": port,
                "profiles": profiles if profiles is not None else [],
            },
        }

    # ------------------------------------------------------------------
    # GET /cameras
    # ------------------------------------------------------------------

    @patch("api.routes.cameras.CameraManager")
    def test_get_cameras_returns_empty_list(self, mock_camera_manager_cls):
        """
        Test GET /cameras returns empty list when no cameras are discovered.
        """
        # Arrange
        mock_manager = MagicMock()
        mock_manager.discover_all_cameras.return_value = []
        mock_camera_manager_cls.return_value = mock_manager

        # Act
        response = self.client.get("/cameras")

        # Assert
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 0)
        mock_manager.discover_all_cameras.assert_called_once()

    @patch("api.routes.cameras.CameraManager")
    def test_get_cameras_returns_usb_cameras(self, mock_camera_manager_cls):
        """
        Test GET /cameras returns list of USB cameras.
        """
        # Arrange
        mock_cameras = [
            self._make_usb_camera("usb_camera_0", "Integrated Camera", "/dev/video0"),
            self._make_usb_camera("usb_camera_1", "External Webcam", "/dev/video1"),
        ]
        mock_manager = MagicMock()
        mock_manager.discover_all_cameras.return_value = mock_cameras
        mock_camera_manager_cls.return_value = mock_manager

        # Act
        response = self.client.get("/cameras")

        # Assert
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["device_id"], "usb_camera_0")
        self.assertEqual(data[0]["device_type"], "USB")
        self.assertEqual(data[1]["device_id"], "usb_camera_1")
        mock_manager.discover_all_cameras.assert_called_once()

    @patch("api.routes.cameras.CameraManager")
    def test_get_cameras_returns_network_cameras(self, mock_camera_manager_cls):
        """
        Test GET /cameras returns list of network cameras.
        """
        # Arrange
        mock_cameras = [
            self._make_network_camera(
                "network_camera_192.168.1.100_80",
                "ONVIF Camera 192.168.1.100",
                "192.168.1.100",
                80,
            ),
        ]
        mock_manager = MagicMock()
        mock_manager.discover_all_cameras.return_value = mock_cameras
        mock_camera_manager_cls.return_value = mock_manager

        # Act
        response = self.client.get("/cameras")

        # Assert
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["device_id"], "network_camera_192.168.1.100_80")
        self.assertEqual(data[0]["device_type"], "NETWORK")
        self.assertEqual(data[0]["details"]["ip"], "192.168.1.100")
        self.assertEqual(data[0]["details"]["port"], 80)

    @patch("api.routes.cameras.CameraManager")
    def test_get_cameras_returns_mixed_cameras(self, mock_camera_manager_cls):
        """
        Test GET /cameras returns list of both USB and network cameras.
        """
        # Arrange
        mock_cameras = [
            self._make_usb_camera("usb_camera_0", "Integrated Camera", "/dev/video0"),
            self._make_network_camera(
                "network_camera_192.168.1.100_80",
                "ONVIF Camera 192.168.1.100",
                "192.168.1.100",
                80,
            ),
        ]
        mock_manager = MagicMock()
        mock_manager.discover_all_cameras.return_value = mock_cameras
        mock_camera_manager_cls.return_value = mock_manager

        # Act
        response = self.client.get("/cameras")

        # Assert
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["device_type"], "USB")
        self.assertEqual(data[1]["device_type"], "NETWORK")

    @patch("api.routes.cameras.CameraManager")
    def test_get_cameras_handles_exception(self, mock_camera_manager_cls):
        """
        Test GET /cameras returns 500 when discovery fails unexpectedly.
        """
        # Arrange
        mock_manager = MagicMock()
        mock_manager.discover_all_cameras.side_effect = Exception("Unexpected error")
        mock_camera_manager_cls.return_value = mock_manager

        # Act
        response = self.client.get("/cameras")

        # Assert
        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertIn("message", data)
        self.assertEqual(data["message"], "Unexpected error when discovering cameras")

    # ------------------------------------------------------------------
    # GET /cameras/{camera_id}
    # ------------------------------------------------------------------

    @patch("api.routes.cameras.CameraManager")
    def test_get_camera_returns_usb_camera(self, mock_camera_manager_cls):
        """
        Test GET /cameras/{camera_id} returns USB camera when found.
        """
        # Arrange
        mock_camera = self._make_usb_camera(
            "usb_camera_0", "Integrated Camera", "/dev/video0"
        )
        mock_manager = MagicMock()
        mock_manager.get_camera_by_id.return_value = mock_camera
        mock_camera_manager_cls.return_value = mock_manager

        # Act
        response = self.client.get("/cameras/usb_camera_0")

        # Assert
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["device_id"], "usb_camera_0")
        self.assertEqual(data["device_name"], "Integrated Camera")
        self.assertEqual(data["device_type"], "USB")
        self.assertEqual(data["details"]["device_path"], "/dev/video0")
        mock_manager.get_camera_by_id.assert_called_once_with("usb_camera_0")

    @patch("api.routes.cameras.CameraManager")
    def test_get_camera_returns_network_camera(self, mock_camera_manager_cls):
        """
        Test GET /cameras/{camera_id} returns network camera when found.
        """
        # Arrange
        mock_camera = self._make_network_camera(
            "network_camera_192.168.1.100_80",
            "ONVIF Camera 192.168.1.100",
            "192.168.1.100",
            80,
            profiles=[
                {
                    "name": "Profile_1",
                    "rtsp_url": "rtsp://192.168.1.100:554/stream1",
                    "resolution": "1920x1080",
                    "encoding": "H264",
                    "framerate": 30,
                    "bitrate": 4096,
                }
            ],
        )
        mock_manager = MagicMock()
        mock_manager.get_camera_by_id.return_value = mock_camera
        mock_camera_manager_cls.return_value = mock_manager

        # Act
        response = self.client.get("/cameras/network_camera_192.168.1.100_80")

        # Assert
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["device_id"], "network_camera_192.168.1.100_80")
        self.assertEqual(data["device_type"], "NETWORK")
        self.assertEqual(data["details"]["ip"], "192.168.1.100")
        self.assertEqual(data["details"]["port"], 80)
        self.assertEqual(len(data["details"]["profiles"]), 1)
        mock_manager.get_camera_by_id.assert_called_once_with(
            "network_camera_192.168.1.100_80"
        )

    @patch("api.routes.cameras.CameraManager")
    def test_get_camera_returns_404_when_not_found(self, mock_camera_manager_cls):
        """
        Test GET /cameras/{camera_id} returns 404 when camera not found.
        """
        # Arrange
        mock_manager = MagicMock()
        mock_manager.get_camera_by_id.return_value = None
        mock_camera_manager_cls.return_value = mock_manager

        # Act
        response = self.client.get("/cameras/nonexistent_camera")

        # Assert
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn("detail", data)
        self.assertIn("nonexistent_camera", data["detail"])
        mock_manager.get_camera_by_id.assert_called_once_with("nonexistent_camera")

    @patch("api.routes.cameras.CameraManager")
    def test_get_camera_handles_exception(self, mock_camera_manager_cls):
        """
        Test GET /cameras/{camera_id} returns 500 when unexpected error occurs.
        """
        # Arrange
        mock_manager = MagicMock()
        mock_manager.get_camera_by_id.side_effect = Exception("Unexpected error")
        mock_camera_manager_cls.return_value = mock_manager

        # Act
        response = self.client.get("/cameras/usb_camera_0")

        # Assert
        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertIn("message", data)
        self.assertEqual(data["message"], "Unexpected error when retrieving camera")

    # ------------------------------------------------------------------
    # POST /cameras/{camera_id}/profiles
    # ------------------------------------------------------------------

    @patch("api.routes.cameras.CameraManager")
    def test_load_camera_profiles_success(self, mock_camera_manager_cls):
        """
        Test POST /cameras/{camera_id}/profiles successfully loads profiles from a network camera.
        """
        # Arrange
        camera_with_profiles = self._make_network_camera(
            "network_camera_192.168.1.100_80",
            "ONVIF Camera 192.168.1.100",
            "192.168.1.100",
            80,
            profiles=[
                {
                    "name": "Profile_1",
                    "rtsp_url": "rtsp://192.168.1.100:554/stream1",
                    "resolution": "1920x1080",
                    "encoding": "H264",
                    "framerate": 30,
                    "bitrate": 4096,
                }
            ],
        )
        mock_manager = MagicMock()
        mock_manager.load_camera_profiles.return_value = camera_with_profiles
        mock_camera_manager_cls.return_value = mock_manager

        # Act
        request_body = {
            "username": "admin",
            "password": "admin123",
        }
        response = self.client.post(
            "/cameras/network_camera_192.168.1.100_80/profiles", json=request_body
        )

        # Assert
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("camera", data)
        camera = data["camera"]
        self.assertEqual(camera["device_id"], "network_camera_192.168.1.100_80")
        self.assertIn("profiles", camera["details"])
        self.assertEqual(len(camera["details"]["profiles"]), 1)
        self.assertEqual(camera["details"]["profiles"][0]["name"], "Profile_1")

        # Verify manager was called with correct parameters
        mock_manager.load_camera_profiles.assert_called_once_with(
            "network_camera_192.168.1.100_80", "admin", "admin123"
        )

    @patch("api.routes.cameras.CameraManager")
    def test_load_camera_profiles_with_multiple_profiles(self, mock_camera_manager_cls):
        """
        Test POST /cameras/{camera_id}/profiles successfully loads multiple profiles.
        """
        # Arrange
        camera_with_profiles = self._make_network_camera(
            "network_camera_192.168.1.100_80",
            "ONVIF Camera 192.168.1.100",
            "192.168.1.100",
            80,
            profiles=[
                {
                    "name": "Profile_1",
                    "rtsp_url": "rtsp://192.168.1.100:554/stream1",
                    "resolution": "1920x1080",
                    "encoding": "H264",
                    "framerate": 30,
                    "bitrate": 4096,
                },
                {
                    "name": "Profile_2",
                    "rtsp_url": "rtsp://192.168.1.100:554/stream2",
                    "resolution": "1280x720",
                    "encoding": "H264",
                    "framerate": 15,
                    "bitrate": 2048,
                },
            ],
        )
        mock_manager = MagicMock()
        mock_manager.load_camera_profiles.return_value = camera_with_profiles
        mock_camera_manager_cls.return_value = mock_manager

        # Act
        request_body = {
            "username": "admin",
            "password": "admin123",
        }
        response = self.client.post(
            "/cameras/network_camera_192.168.1.100_80/profiles", json=request_body
        )

        # Assert
        self.assertEqual(response.status_code, 200)
        data = response.json()
        camera = data["camera"]
        self.assertEqual(len(camera["details"]["profiles"]), 2)
        self.assertEqual(camera["details"]["profiles"][0]["name"], "Profile_1")
        self.assertEqual(camera["details"]["profiles"][1]["name"], "Profile_2")

    @patch("api.routes.cameras.CameraManager")
    def test_load_camera_profiles_invalid_camera_id(self, mock_camera_manager_cls):
        """
        Test POST /cameras/{camera_id}/profiles returns 400 for invalid camera_id format.
        """
        # Arrange
        mock_manager = MagicMock()
        mock_manager.load_camera_profiles.side_effect = ValueError(
            "Invalid camera_id format"
        )
        mock_camera_manager_cls.return_value = mock_manager

        # Act
        request_body = {
            "username": "admin",
            "password": "admin123",
        }
        response = self.client.post(
            "/cameras/invalid_camera_id/profiles", json=request_body
        )

        # Assert
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("detail", data)

    @patch("api.routes.cameras.CameraManager")
    def test_load_camera_profiles_camera_not_found(self, mock_camera_manager_cls):
        """
        Test POST /cameras/{camera_id}/profiles returns 404 when camera is not reachable.
        """
        # Arrange
        mock_manager = MagicMock()
        mock_manager.load_camera_profiles.side_effect = ConnectionError(
            "Camera not reachable"
        )
        mock_camera_manager_cls.return_value = mock_manager

        # Act
        request_body = {
            "username": "admin",
            "password": "admin123",
        }
        response = self.client.post(
            "/cameras/network_camera_192.168.1.200_80/profiles", json=request_body
        )

        # Assert
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn("detail", data)
        self.assertIn("Camera not reachable", data["detail"])

    @patch("api.routes.cameras.CameraManager")
    def test_load_camera_profiles_invalid_credentials(self, mock_camera_manager_cls):
        """
        Test POST /cameras/{camera_id}/profiles returns 401 for invalid credentials.
        """
        # Arrange
        mock_manager = MagicMock()
        mock_manager.load_camera_profiles.side_effect = Exception("unauthorized access")
        mock_camera_manager_cls.return_value = mock_manager

        # Act
        request_body = {
            "username": "admin",
            "password": "wrongpassword",
        }
        response = self.client.post(
            "/cameras/network_camera_192.168.1.100_80/profiles", json=request_body
        )

        # Assert
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertIn("detail", data)
        self.assertIn("invalid credentials", data["detail"])

    @patch("api.routes.cameras.CameraManager")
    def test_load_camera_profiles_authentication_error(self, mock_camera_manager_cls):
        """
        Test POST /cameras/{camera_id}/profiles returns 401 for authentication error.
        """
        # Arrange
        mock_manager = MagicMock()
        mock_manager.load_camera_profiles.side_effect = Exception(
            "authentication failed"
        )
        mock_camera_manager_cls.return_value = mock_manager

        # Act
        request_body = {
            "username": "admin",
            "password": "wrongpassword",
        }
        response = self.client.post(
            "/cameras/network_camera_192.168.1.100_80/profiles", json=request_body
        )

        # Assert
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertIn("detail", data)

    @patch("api.routes.cameras.CameraManager")
    def test_load_camera_profiles_credentials_error(self, mock_camera_manager_cls):
        """
        Test POST /cameras/{camera_id}/profiles returns 401 for credentials error.
        """
        # Arrange
        mock_manager = MagicMock()
        mock_manager.load_camera_profiles.side_effect = Exception(
            "invalid credentials provided"
        )
        mock_camera_manager_cls.return_value = mock_manager

        # Act
        request_body = {
            "username": "admin",
            "password": "wrongpassword",
        }
        response = self.client.post(
            "/cameras/network_camera_192.168.1.100_80/profiles", json=request_body
        )

        # Assert
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertIn("detail", data)

    @patch("api.routes.cameras.CameraManager")
    def test_load_camera_profiles_unexpected_error(self, mock_camera_manager_cls):
        """
        Test POST /cameras/{camera_id}/profiles returns 500 for unexpected errors.
        """
        # Arrange
        mock_manager = MagicMock()
        mock_manager.load_camera_profiles.side_effect = Exception(
            "Unexpected internal error"
        )
        mock_camera_manager_cls.return_value = mock_manager

        # Act
        request_body = {
            "username": "admin",
            "password": "admin123",
        }
        response = self.client.post(
            "/cameras/network_camera_192.168.1.100_80/profiles", json=request_body
        )

        # Assert
        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertIn("detail", data)
        self.assertIn("Unexpected error", data["detail"])

    @patch("api.routes.cameras.CameraManager")
    def test_load_camera_profiles_missing_username(self, mock_camera_manager_cls):
        """
        Test POST /cameras/{camera_id}/profiles returns 422 for missing username.
        """
        # Arrange
        mock_manager = MagicMock()
        mock_camera_manager_cls.return_value = mock_manager

        # Act: send request without username
        request_body = {
            "password": "admin123",
        }
        response = self.client.post(
            "/cameras/network_camera_192.168.1.100_80/profiles", json=request_body
        )

        # Assert: FastAPI validation should reject the request
        self.assertEqual(response.status_code, 422)
        mock_manager.load_camera_profiles.assert_not_called()

    @patch("api.routes.cameras.CameraManager")
    def test_load_camera_profiles_missing_password(self, mock_camera_manager_cls):
        """
        Test POST /cameras/{camera_id}/profiles returns 422 for missing password.
        """
        # Arrange
        mock_manager = MagicMock()
        mock_camera_manager_cls.return_value = mock_manager

        # Act: send request without password
        request_body = {
            "username": "admin",
        }
        response = self.client.post(
            "/cameras/network_camera_192.168.1.100_80/profiles", json=request_body
        )

        # Assert: FastAPI validation should reject the request
        self.assertEqual(response.status_code, 422)
        mock_manager.load_camera_profiles.assert_not_called()


if __name__ == "__main__":
    unittest.main()
