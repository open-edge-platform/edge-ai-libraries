import unittest
from unittest.mock import MagicMock, patch

from device import DeviceDiscovery, DeviceFamily, DeviceInfo, DeviceType


# Test DeviceInfo dataclass and its default values
class TestDeviceInfo(unittest.TestCase):
    def test_device_info_defaults(self):
        """Test DeviceInfo default values."""
        info = DeviceInfo(device_name="CPU")
        self.assertEqual(info.device_name, "CPU")
        self.assertEqual(info.full_device_name, "")
        self.assertEqual(info.device_type, DeviceType.INTEGRATED)
        self.assertEqual(info.device_family, DeviceFamily.CPU)
        self.assertIsNone(info.gpu_id)

    def test_device_info_gpu_id(self):
        """Test DeviceInfo with GPU id."""
        info = DeviceInfo(device_name="GPU", gpu_id=0)
        self.assertEqual(info.gpu_id, 0)
        info2 = DeviceInfo(device_name="CPU")
        self.assertIsNone(info2.gpu_id)


# Test DeviceDiscovery singleton, device listing, and parsing logic
class TestDeviceDiscovery(unittest.TestCase):
    def setUp(self):
        # Reset the singleton instance before each test
        DeviceDiscovery._instance = None

    def tearDown(self):
        # Reset the singleton instance after each test
        DeviceDiscovery._instance = None

    @patch("device.ov.Core")
    def test_singleton(self, mock_core):
        """Test that DeviceDiscovery is a singleton."""
        d1 = DeviceDiscovery()
        d2 = DeviceDiscovery()
        self.assertIs(d1, d2)

    @patch("device.ov.Core")
    def test_list_devices(self, mock_core):
        """Test listing devices returns correct DeviceInfo objects."""
        mock_core_instance = MagicMock()
        mock_core.return_value = mock_core_instance
        mock_core_instance.available_devices = ["CPU", "GPU"]
        mock_core_instance.get_property.side_effect = lambda device, prop: {
            ("CPU", "FULL_DEVICE_NAME"): "Intel CPU",
            ("CPU", "DEVICE_TYPE"): "Type.INTEGRATED",
            ("GPU", "FULL_DEVICE_NAME"): "Intel GPU",
            ("GPU", "DEVICE_TYPE"): "Type.INTEGRATED",
        }[(device, prop)]

        discovery = DeviceDiscovery()
        devices = discovery.list_devices()
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0].device_name, "CPU")
        self.assertEqual(devices[1].device_name, "GPU")
        self.assertEqual(devices[0].full_device_name, "Intel CPU")
        self.assertEqual(devices[1].gpu_id, 0)

    @patch("device.ov.Core")
    def test_multiple_gpus_full_device_name(self, mock_core):
        """Test that multiple GPUs get device name appended to full_device_name."""
        mock_core_instance = MagicMock()
        mock_core.return_value = mock_core_instance
        mock_core_instance.available_devices = ["GPU.0", "GPU.1"]
        mock_core_instance.get_property.side_effect = lambda device, prop: {
            ("GPU.0", "FULL_DEVICE_NAME"): "Intel GPU 0",
            ("GPU.0", "DEVICE_TYPE"): "Type.INTEGRATED",
            ("GPU.1", "FULL_DEVICE_NAME"): "Intel GPU 1",
            ("GPU.1", "DEVICE_TYPE"): "Type.INTEGRATED",
        }[(device, prop)]

        discovery = DeviceDiscovery()
        devices = discovery.list_devices()
        self.assertEqual(len(devices), 2)
        self.assertTrue(devices[0].full_device_name.endswith("(GPU.0)"))
        self.assertTrue(devices[1].full_device_name.endswith("(GPU.1)"))

    @patch("device.ov.Core")
    def test_parse_device_type_integrated(self, mock_core):
        """Test parse_device_type returns INTEGRATED."""
        mock_core_instance = MagicMock()
        mock_core.return_value = mock_core_instance
        mock_core_instance.available_devices = ["CPU"]
        mock_core_instance.get_property.side_effect = lambda device, prop: {
            ("CPU", "FULL_DEVICE_NAME"): "Intel CPU",
            ("CPU", "DEVICE_TYPE"): "Type.INTEGRATED",
        }[(device, prop)]
        discovery = DeviceDiscovery()
        self.assertEqual(discovery.parse_device_type("CPU"), DeviceType.INTEGRATED)

    @patch("device.ov.Core")
    def test_parse_device_type_discrete(self, mock_core):
        """Test parse_device_type returns DISCRETE."""
        mock_core_instance = MagicMock()
        mock_core.return_value = mock_core_instance
        mock_core_instance.available_devices = ["GPU"]
        mock_core_instance.get_property.side_effect = lambda device, prop: {
            ("GPU", "FULL_DEVICE_NAME"): "Intel GPU",
            ("GPU", "DEVICE_TYPE"): "Type.DISCRETE",
        }[(device, prop)]
        discovery = DeviceDiscovery()
        self.assertEqual(discovery.parse_device_type("GPU"), DeviceType.DISCRETE)

    @patch("device.ov.Core")
    def test_parse_device_type_unknown(self, mock_core):
        """Test parse_device_type logs error and falls back to INTEGRATED."""
        mock_core_instance = MagicMock()
        mock_core.return_value = mock_core_instance
        mock_core_instance.available_devices = ["NPU"]
        mock_core_instance.get_property.side_effect = lambda device, prop: {
            ("NPU", "FULL_DEVICE_NAME"): "Intel NPU",
            ("NPU", "DEVICE_TYPE"): "Type.UNKNOWN",
        }[(device, prop)]
        with patch("device.logger") as mock_logger:
            discovery = DeviceDiscovery()
            result = discovery.parse_device_type("NPU")
            self.assertEqual(result, DeviceType.INTEGRATED)
            mock_logger.error.assert_called()

    def test_parse_device_family_static(self):
        """Test parse_device_family static method for all families and fallback."""
        self.assertEqual(DeviceDiscovery.parse_device_family("CPU"), DeviceFamily.CPU)
        self.assertEqual(DeviceDiscovery.parse_device_family("GPU"), DeviceFamily.GPU)
        self.assertEqual(DeviceDiscovery.parse_device_family("NPU"), DeviceFamily.NPU)
        with patch("device.logger") as mock_logger:
            self.assertEqual(
                DeviceDiscovery.parse_device_family("OTHER"), DeviceFamily.CPU
            )
            mock_logger.error.assert_called()

    def test_parse_gpu_id_static(self):
        """Test parse_gpu_id static method for various device names."""
        self.assertEqual(DeviceDiscovery.parse_gpu_id("GPU"), 0)
        self.assertEqual(DeviceDiscovery.parse_gpu_id("GPU.1"), 1)
        self.assertIsNone(DeviceDiscovery.parse_gpu_id("CPU"))
        with patch("device.logger") as mock_logger:
            self.assertIsNone(DeviceDiscovery.parse_gpu_id("GPU.bad"))
            mock_logger.info.assert_called()

    @patch("device.ov.Core")
    def test_list_devices_empty(self, mock_core):
        """Test list_devices returns empty list if no devices."""
        mock_core_instance = MagicMock()
        mock_core.return_value = mock_core_instance
        mock_core_instance.available_devices = []
        discovery = DeviceDiscovery()
        self.assertEqual(discovery.list_devices(), [])

    @patch("device.ov.Core")
    def test_list_devices_called(self, mock_core):
        """Test list_devices returns a list of DeviceInfo."""
        mock_core_instance = MagicMock()
        mock_core.return_value = mock_core_instance
        mock_core_instance.available_devices = ["CPU"]
        mock_core_instance.get_property.side_effect = lambda device, prop: {
            ("CPU", "FULL_DEVICE_NAME"): "Intel CPU",
            ("CPU", "DEVICE_TYPE"): "Type.INTEGRATED",
        }[(device, prop)]
        discovery = DeviceDiscovery()
        self.assertIsInstance(discovery.list_devices(), list)
        self.assertEqual(len(discovery.list_devices()), 1)

    @patch("device.ov.Core")
    def test_init_only_once(self, mock_core):
        """Test that __init__ does not reinitialize if already initialized."""
        mock_core_instance = MagicMock()
        mock_core.return_value = mock_core_instance
        mock_core_instance.available_devices = ["CPU"]
        mock_core_instance.get_property.side_effect = lambda device, prop: {
            ("CPU", "FULL_DEVICE_NAME"): "Intel CPU",
            ("CPU", "DEVICE_TYPE"): "Type.INTEGRATED",
        }[(device, prop)]
        discovery = DeviceDiscovery()
        # Save the core object
        core_before = discovery.core
        # Call __init__ again, should not reinitialize
        discovery.__init__()
        self.assertIs(discovery.core, core_before)

    @patch("device.ov.Core")
    def test_multiple_gpu_id_parsing(self, mock_core):
        """Test parse_gpu_id with multiple GPU devices."""
        mock_core_instance = MagicMock()
        mock_core.return_value = mock_core_instance
        mock_core_instance.available_devices = ["GPU.0", "GPU.1", "GPU.bad"]
        mock_core_instance.get_property.side_effect = lambda device, prop: {
            ("GPU.0", "FULL_DEVICE_NAME"): "Intel GPU 0",
            ("GPU.0", "DEVICE_TYPE"): "Type.INTEGRATED",
            ("GPU.1", "FULL_DEVICE_NAME"): "Intel GPU 1",
            ("GPU.1", "DEVICE_TYPE"): "Type.INTEGRATED",
            ("GPU.bad", "FULL_DEVICE_NAME"): "Intel GPU bad",
            ("GPU.bad", "DEVICE_TYPE"): "Type.INTEGRATED",
        }[(device, prop)]
        with patch("device.logger") as mock_logger:
            discovery = DeviceDiscovery()
            # Should log info for GPU.bad
            mock_logger.info.assert_called()
            devices = discovery.list_devices()
            self.assertEqual(devices[0].gpu_id, 0)
            self.assertEqual(devices[1].gpu_id, 1)
            self.assertIsNone(devices[2].gpu_id)

    def test_parse_device_family_case_insensitive(self):
        """Test parse_device_family is case-sensitive (should fallback for lowercase)."""
        with patch("device.logger") as mock_logger:
            self.assertEqual(
                DeviceDiscovery.parse_device_family("cpu"), DeviceFamily.CPU
            )
            mock_logger.error.assert_called()

    def test_parse_gpu_id_non_numeric(self):
        """Test parse_gpu_id with non-numeric GPU id."""
        with patch("device.logger") as mock_logger:
            self.assertIsNone(DeviceDiscovery.parse_gpu_id("GPU.x"))
            mock_logger.info.assert_called()

    def test_parse_gpu_id_empty(self):
        """Test parse_gpu_id with empty string."""
        self.assertIsNone(DeviceDiscovery.parse_gpu_id(""))

    def test_parse_device_family_empty(self):
        """Test parse_device_family with empty string."""
        with patch("device.logger") as mock_logger:
            self.assertEqual(DeviceDiscovery.parse_device_family(""), DeviceFamily.CPU)
            mock_logger.error.assert_called()


if __name__ == "__main__":
    unittest.main()
