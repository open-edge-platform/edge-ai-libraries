# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from utils.device_validation import resolve_tts_device


class DeviceValidationTests(unittest.TestCase):
    def setUp(self):
        resolve_tts_device.cache_clear()

    def tearDown(self):
        resolve_tts_device.cache_clear()

    @staticmethod
    def _openvino_with(*devices: str) -> ModuleType:
        module = ModuleType("openvino")
        module.Core = lambda: SimpleNamespace(available_devices=list(devices))
        return module

    def test_openvino_cpu_is_available(self):
        with patch.dict(sys.modules, {"openvino": self._openvino_with("CPU")}):
            self.assertEqual(
                resolve_tts_device("openvino", "microsoft/speecht5_tts", "CPU"),
                "CPU",
            )

    def test_openvino_gpu_family_matches_indexed_device(self):
        with patch.dict(sys.modules, {"openvino": self._openvino_with("CPU", "GPU.0")}):
            self.assertEqual(
                resolve_tts_device("openvino", "microsoft/speecht5_tts", "GPU"),
                "GPU",
            )

    def test_kokoro_rejects_accelerator(self):
        with self.assertRaisesRegex(ValueError, "supports only CPU"):
            resolve_tts_device("openvino", "kokoro", "NPU")

    def test_unknown_device_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported TTS device"):
            resolve_tts_device("openvino", "microsoft/speecht5_tts", "AUTO")


if __name__ == "__main__":
    unittest.main()
