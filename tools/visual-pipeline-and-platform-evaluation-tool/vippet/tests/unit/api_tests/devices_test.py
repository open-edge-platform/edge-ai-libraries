import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api.routes.devices import router as devices_router
import api.api_schemas as schemas


class TestDevicesAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up test client once for all tests."""
        app = FastAPI()
        app.include_router(devices_router, prefix="/devices")
        cls.client = TestClient(app)

    def _make_device(
        self, device_name, full_device_name, device_type, device_family, gpu_id=None
    ):
        """Helper method to create a mock device."""
        m = MagicMock()
        m.device_name = device_name
        m.full_device_name = full_device_name
        m.device_type = device_type
        m.device_family = device_family
        m.gpu_id = gpu_id
        return m

    def test_get_devices_returns_multiple_devices(self):
        """Test GET /devices returns list of multiple devices with correct attributes."""
        mock_devices = [
            self._make_device(
                "CPU",
                "Intel(R) Core(TM) Ultra 9 185H",
                schemas.DeviceType.INTEGRATED,
                schemas.DeviceFamily.CPU,
            ),
            self._make_device(
                "GPU",
                "Intel(R) Graphics (iGPU)",
                schemas.DeviceType.DISCRETE,
                schemas.DeviceFamily.GPU,
                gpu_id=2,
            ),
            self._make_device(
                "NPU",
                "Intel(R) AI Boost",
                schemas.DeviceType.INTEGRATED,
                schemas.DeviceFamily.NPU,
            ),
        ]
        with patch("api.routes.devices.DeviceDiscovery") as MockDeviceDiscovery:
            MockDeviceDiscovery.return_value.list_devices.return_value = mock_devices
            response = self.client.get("/devices")

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIsInstance(data, list)
            self.assertEqual(len(data), 3)

            # Check first device (CPU without gpu_id)
            self.assertEqual(data[0]["device_name"], "CPU")
            self.assertEqual(
                data[0]["full_device_name"], "Intel(R) Core(TM) Ultra 9 185H"
            )
            self.assertEqual(
                data[0]["device_type"], schemas.DeviceType.INTEGRATED.value
            )
            self.assertEqual(data[0]["device_family"], schemas.DeviceFamily.CPU.value)
            self.assertIsNone(data[0]["gpu_id"])

            # Check second device (GPU with gpu_id)
            self.assertEqual(data[1]["device_name"], "GPU")
            self.assertEqual(data[1]["full_device_name"], "Intel(R) Graphics (iGPU)")
            self.assertEqual(data[1]["device_type"], schemas.DeviceType.DISCRETE.value)
            self.assertEqual(data[1]["device_family"], schemas.DeviceFamily.GPU.value)
            self.assertEqual(data[1]["gpu_id"], 2)

            # Check third device (NPU without gpu_id)
            self.assertEqual(data[2]["device_name"], "NPU")
            self.assertEqual(data[2]["full_device_name"], "Intel(R) AI Boost")
            self.assertEqual(
                data[2]["device_type"], schemas.DeviceType.INTEGRATED.value
            )
            self.assertEqual(data[2]["device_family"], schemas.DeviceFamily.NPU.value)
            self.assertIsNone(data[2]["gpu_id"])

    def test_get_devices_returns_empty_list(self):
        """Test GET /devices returns empty list when no devices available."""
        with patch("api.routes.devices.DeviceDiscovery") as MockDiscovery:
            MockDiscovery.return_value.list_devices.return_value = []
            response = self.client.get("/devices")

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data, [])

    def test_get_devices_handles_missing_gpu_id(self):
        """Test GET /devices correctly handles devices without gpu_id attribute."""
        mock_device = MagicMock()
        mock_device.device_name = "CPU"
        mock_device.full_device_name = "Intel CPU"
        mock_device.device_type = schemas.DeviceType.INTEGRATED
        mock_device.device_family = schemas.DeviceFamily.CPU
        # Explicitly remove gpu_id attribute to test getattr fallback
        delattr(mock_device, "gpu_id") if hasattr(mock_device, "gpu_id") else None

        with patch("api.routes.devices.DeviceDiscovery") as MockDiscovery:
            MockDiscovery.return_value.list_devices.return_value = [mock_device]
            response = self.client.get("/devices")

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(len(data), 1)
            self.assertIsNone(data[0]["gpu_id"])


if __name__ == "__main__":
    unittest.main()
