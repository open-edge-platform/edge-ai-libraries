import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api.routes.devices import router as devices_router
import api.api_schemas as schemas
from cpu_topology import CoreType, CpuTopology, LogicalCpu, TopologySource


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

    def _cpu_and_gpu(self):
        return [
            self._make_device(
                "CPU",
                "Intel(R) Core(TM) Ultra 9 285H",
                schemas.DeviceType.INTEGRATED,
                schemas.DeviceFamily.CPU,
            ),
            self._make_device(
                "GPU",
                "Intel(R) Arc(TM) 140T GPU (16GB)",
                schemas.DeviceType.INTEGRATED,
                schemas.DeviceFamily.GPU,
                gpu_id=0,
            ),
        ]

    def _get_with_topology(self, **topology_patch):
        with (
            patch("api.routes.devices.DeviceDiscovery") as MockDiscovery,
            patch("api.routes.devices.get_cpu_topology", **topology_patch),
        ):
            MockDiscovery.return_value.list_devices.return_value = self._cpu_and_gpu()
            return self.client.get("/devices")

    def test_get_devices_reports_cpu_topology_on_cpu_only(self):
        """CPU entry carries the core types; other devices get null."""
        topology = CpuTopology(
            cpus=(
                LogicalCpu(cpu=0, core_type=CoreType.P, core_id=0),
                LogicalCpu(cpu=1, core_type=CoreType.P, core_id=0),
                LogicalCpu(cpu=2, core_type=CoreType.E, core_id=2),
                LogicalCpu(cpu=3, core_type=CoreType.LPE, core_id=3),
            ),
            source=TopologySource.SYSFS_PMU,
        )
        response = self._get_with_topology(return_value=topology)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            data[0]["cpu_topology"],
            {
                "is_hybrid": True,
                "source": "sysfs_pmu",
                "cores": [
                    {"cpu": 0, "core_type": "P", "core_id": 0},
                    {"cpu": 1, "core_type": "P", "core_id": 0},
                    {"cpu": 2, "core_type": "E", "core_id": 2},
                    {"cpu": 3, "core_type": "LPE", "core_id": 3},
                ],
            },
        )
        self.assertIsNone(data[1]["cpu_topology"])

    def test_get_devices_reports_uniform_cpu(self):
        topology = CpuTopology(
            cpus=(LogicalCpu(cpu=0, core_type=CoreType.UNIFORM, core_id=0),),
            source=TopologySource.UNIFORM,
        )
        response = self._get_with_topology(return_value=topology)

        self.assertEqual(response.status_code, 200)
        cpu_topology = response.json()[0]["cpu_topology"]
        self.assertFalse(cpu_topology["is_hybrid"])
        self.assertEqual(cpu_topology["source"], "uniform")
        self.assertEqual(cpu_topology["cores"][0]["core_type"], "UNIFORM")

    def test_get_devices_unavailable_topology_is_null(self):
        topology = CpuTopology(cpus=(), source=TopologySource.UNAVAILABLE)
        response = self._get_with_topology(return_value=topology)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()[0]["cpu_topology"])

    def test_get_devices_topology_error_does_not_fail_request(self):
        """A topology failure is logged and reported as null, not as 500."""
        with self.assertLogs("api.routes.devices", level="ERROR"):
            response = self._get_with_topology(side_effect=RuntimeError("boom"))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        self.assertIsNone(data[0]["cpu_topology"])
        self.assertIsNone(data[1]["cpu_topology"])

    def test_get_devices_discovery_error_returns_500(self):
        with patch("api.routes.devices.DeviceDiscovery") as MockDiscovery:
            MockDiscovery.return_value.list_devices.side_effect = RuntimeError("x")
            with self.assertLogs("api.routes.devices", level="ERROR"):
                response = self.client.get("/devices")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(), {"message": "Unexpected error when discovering devices"}
        )


if __name__ == "__main__":
    unittest.main()
