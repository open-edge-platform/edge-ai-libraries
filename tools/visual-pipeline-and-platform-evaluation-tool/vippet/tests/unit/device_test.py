import unittest
from unittest.mock import patch

import httpx

from device import (
    DEVICES_READ_ATTEMPTS,
    DeviceDiscovery,
    DeviceDiscoveryError,
    DeviceFamily,
    DeviceInfo,
    DeviceType,
)


def _device(name, full_name=None, device_type="INTEGRATED"):
    properties = {"DEVICE_TYPE": device_type}
    if full_name is not None:
        properties["FULL_DEVICE_NAME"] = full_name
    return {"name": name, "properties": properties}


def _response(status_code=200, payload=None):
    return httpx.Response(
        status_code,
        json=payload,
        request=httpx.Request("GET", "http://dlsps/devices"),
    )


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


# Test DeviceDiscovery singleton, device listing from DLSPS 2.0, and parsing logic
@patch("device.time.sleep")
@patch("device.httpx.get")
class TestDeviceDiscovery(unittest.TestCase):
    def setUp(self):
        # Reset the singleton instance before each test
        DeviceDiscovery._instance = None

    def tearDown(self):
        # Reset the singleton instance after each test
        DeviceDiscovery._instance = None

    def test_singleton(self, mock_get, mock_sleep):
        """Test that DeviceDiscovery is a singleton."""
        d1 = DeviceDiscovery()
        d2 = DeviceDiscovery()
        self.assertIs(d1, d2)

    def test_init_does_not_read_server(self, mock_get, mock_sleep):
        """Test that the device list is read on first use, not on construction."""
        DeviceDiscovery()
        mock_get.assert_not_called()

    def test_list_devices(self, mock_get, mock_sleep):
        """Test listing devices returns correct DeviceInfo objects."""
        mock_get.return_value = _response(
            payload=[_device("CPU", "Intel CPU"), _device("GPU", "Intel GPU")]
        )

        devices = DeviceDiscovery().list_devices()

        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0].device_name, "CPU")
        self.assertEqual(devices[1].device_name, "GPU")
        self.assertEqual(devices[0].full_device_name, "Intel CPU")
        self.assertEqual(devices[0].device_family, DeviceFamily.CPU)
        self.assertEqual(devices[1].device_family, DeviceFamily.GPU)
        self.assertIsNone(devices[0].gpu_id)
        self.assertEqual(devices[1].gpu_id, 0)

    def test_list_devices_reads_dlsps2_devices_endpoint(self, mock_get, mock_sleep):
        """Test that the device list is read from GET /devices of DLSPS 2.0."""
        mock_get.return_value = _response(payload=[])
        with patch("device.DLSPS2_BASE_URL", "http://dlsps:8080"):
            DeviceDiscovery().list_devices()
        self.assertEqual(mock_get.call_args.args[0], "http://dlsps:8080/devices")

    def test_list_devices_device_type(self, mock_get, mock_sleep):
        """Test DEVICE_TYPE names map to DeviceType."""
        mock_get.return_value = _response(
            payload=[
                _device("CPU", "Intel CPU", "INTEGRATED"),
                _device("GPU", "Intel GPU", "DISCRETE"),
            ]
        )
        devices = DeviceDiscovery().list_devices()
        self.assertEqual(devices[0].device_type, DeviceType.INTEGRATED)
        self.assertEqual(devices[1].device_type, DeviceType.DISCRETE)

    def test_list_devices_missing_full_device_name(self, mock_get, mock_sleep):
        """Test that a device without FULL_DEVICE_NAME is named by its device name."""
        mock_get.return_value = _response(payload=[_device("NPU")])
        devices = DeviceDiscovery().list_devices()
        self.assertEqual(devices[0].full_device_name, "NPU")

    def test_multiple_gpus_full_device_name(self, mock_get, mock_sleep):
        """Test that multiple GPUs get device name appended to full_device_name."""
        mock_get.return_value = _response(
            payload=[_device("GPU.0", "Intel GPU 0"), _device("GPU.1", "Intel GPU 1")]
        )
        devices = DeviceDiscovery().list_devices()
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0].full_device_name, "Intel GPU 0 (GPU.0)")
        self.assertEqual(devices[1].full_device_name, "Intel GPU 1 (GPU.1)")

    def test_multiple_gpu_id_parsing(self, mock_get, mock_sleep):
        """Test gpu_id parsing with multiple GPU devices."""
        mock_get.return_value = _response(
            payload=[
                _device("GPU.0", "Intel GPU 0"),
                _device("GPU.1", "Intel GPU 1"),
                _device("GPU.bad", "Intel GPU bad"),
            ]
        )
        with patch("device.logger") as mock_logger:
            devices = DeviceDiscovery().list_devices()
            # Should log info for GPU.bad
            mock_logger.info.assert_called()
        self.assertEqual(devices[0].gpu_id, 0)
        self.assertEqual(devices[1].gpu_id, 1)
        self.assertIsNone(devices[2].gpu_id)

    def test_list_devices_empty(self, mock_get, mock_sleep):
        """Test list_devices returns empty list if no devices."""
        mock_get.return_value = _response(payload=[])
        self.assertEqual(DeviceDiscovery().list_devices(), [])

    def test_list_devices_cached(self, mock_get, mock_sleep):
        """Test that the first list read is kept and the server is not asked again."""
        mock_get.return_value = _response(payload=[_device("CPU", "Intel CPU")])
        discovery = DeviceDiscovery()
        first = discovery.list_devices()
        DeviceDiscovery().__init__()
        self.assertIs(DeviceDiscovery().list_devices(), first)
        mock_get.assert_called_once()

    def test_first_read_retries(self, mock_get, mock_sleep):
        """Test that the first read retries until the server answers."""
        mock_get.side_effect = [
            httpx.ConnectError("refused"),
            _response(503, {"detail": "OpenVINO device discovery unavailable"}),
            _response(payload=[_device("CPU", "Intel CPU")]),
        ]
        devices = DeviceDiscovery().list_devices()
        self.assertEqual([d.device_name for d in devices], ["CPU"])
        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    def test_read_failure_raises_and_next_read_tries_once(self, mock_get, mock_sleep):
        """Test that a failed read raises, is not cached, and is retried once later."""
        mock_get.side_effect = httpx.ConnectError("refused")
        discovery = DeviceDiscovery()
        with self.assertRaises(DeviceDiscoveryError):
            discovery.list_devices()
        self.assertEqual(mock_get.call_count, DEVICES_READ_ATTEMPTS)

        mock_get.reset_mock()
        with self.assertRaises(DeviceDiscoveryError):
            discovery.list_devices()
        mock_get.assert_called_once()

        mock_get.reset_mock()
        mock_get.side_effect = None
        mock_get.return_value = _response(payload=[_device("CPU", "Intel CPU")])
        self.assertEqual(len(discovery.list_devices()), 1)
        mock_get.assert_called_once()

    def test_unexpected_payload_raises(self, mock_get, mock_sleep):
        """Test that a payload that is not a device list raises DeviceDiscoveryError."""
        for payload in ({"name": "CPU"}, [{"properties": {}}], ["CPU"]):
            with self.subTest(payload=payload):
                DeviceDiscovery._instance = None
                mock_get.return_value = _response(payload=payload)
                with self.assertRaises(DeviceDiscoveryError):
                    DeviceDiscovery().list_devices()

    def test_parse_device_type(self, mock_get, mock_sleep):
        """Test parse_device_type maps DEVICE_TYPE names."""
        self.assertEqual(
            DeviceDiscovery.parse_device_type("CPU", "INTEGRATED"),
            DeviceType.INTEGRATED,
        )
        self.assertEqual(
            DeviceDiscovery.parse_device_type("GPU", "DISCRETE"), DeviceType.DISCRETE
        )

    def test_parse_device_type_unknown(self, mock_get, mock_sleep):
        """Test parse_device_type logs error and falls back to INTEGRATED."""
        for device_type in ("UNKNOWN", None):
            with self.subTest(device_type=device_type):
                with patch("device.logger") as mock_logger:
                    result = DeviceDiscovery.parse_device_type("NPU", device_type)
                    self.assertEqual(result, DeviceType.INTEGRATED)
                    mock_logger.error.assert_called()


# Test static name parsing helpers
class TestDeviceNameParsing(unittest.TestCase):
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
