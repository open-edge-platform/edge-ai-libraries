import unittest
from unittest.mock import MagicMock, patch

from device import DeviceDiscovery, DeviceInfo


class TestDeviceInfo(unittest.TestCase):
    def test_device_info_defaults(self):
        info = DeviceInfo(device_name="CPU")
        self.assertEqual(info.device_name, "CPU")
        self.assertEqual(info.available_devices, [])
        self.assertEqual(info.full_device_name, "")
        self.assertEqual(info.device_type, "")

    def test_device_info_custom(self):
        info = DeviceInfo(
            device_name="GPU",
            available_devices=["0"],
            full_device_name="Intel(R) Arc(TM) Graphics (iGPU)",
            device_type="Type.INTEGRATED"
        )
        self.assertEqual(info.device_name, "GPU")
        self.assertEqual(info.available_devices, ["0"])
        self.assertEqual(info.full_device_name, "Intel(R) Arc(TM) Graphics (iGPU)")
        self.assertEqual(info.device_type, "Type.INTEGRATED")

class TestDeviceDiscovery(unittest.TestCase):
    def setUp(self):
        # Reset the singleton instance before each test
        DeviceDiscovery._instance = None

    def tearDown(self):
        # Reset the singleton instance after each test
        DeviceDiscovery._instance = None

    @patch("device.ov.Core")
    def test_singleton(self, mock_core):
        # Ensure singleton property
        d1 = DeviceDiscovery()
        d2 = DeviceDiscovery()
        self.assertIs(d1, d2)

    @patch("device.ov.Core")
    def test_list_devices(self, mock_core):
        # Setup mock for ov.Core
        mock_core_instance = MagicMock()
        mock_core.return_value = mock_core_instance
        mock_core_instance.available_devices = ["CPU", "GPU"]
        mock_core_instance.get_property.side_effect = lambda device, prop: {
            ("CPU", "AVAILABLE_DEVICES"): [""],
            ("CPU", "FULL_DEVICE_NAME"): "Intel CPU",
            ("CPU", "DEVICE_TYPE"): "Type.INTEGRATED",
            ("GPU", "AVAILABLE_DEVICES"): ["0"],
            ("GPU", "FULL_DEVICE_NAME"): "Intel GPU",
            ("GPU", "DEVICE_TYPE"): "Type.INTEGRATED",
        }[(device, prop)]

        discovery = DeviceDiscovery()
        devices = discovery.list_devices()
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0].device_name, "CPU")
        self.assertEqual(devices[1].device_name, "GPU")
        self.assertEqual(devices[0].full_device_name, "Intel CPU")
        self.assertEqual(devices[1].available_devices, ["0"])

if __name__ == "__main__":
    unittest.main()