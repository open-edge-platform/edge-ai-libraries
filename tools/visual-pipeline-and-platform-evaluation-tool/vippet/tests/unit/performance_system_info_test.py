# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the performance-test report system-info collection."""

import unittest

from tests.performance.perf_helpers import system_info

_DEVICES = [
    {"device_family": "CPU", "full_device_name": "Intel(R) Core(TM) Ultra 7 265U"},
    {"device_family": "GPU", "full_device_name": "Intel(R) Arc(TM) Graphics"},
]

_CAPABILITIES = {
    "platform": {
        "os": "Linux",
        "kernel": "6.6.87.2-microsoft-standard-WSL2",
        "system_memory": {"installed_gib": 31.07},
        "system_storage": {"available_gib": 846.34, "total_capacity_gib": 1032.56},
    }
}


class TestCollectSystemInfo(unittest.TestCase):
    def test_full_snapshot_reports_all_fields(self) -> None:
        system = system_info.collect_system_info(
            _DEVICES, _CAPABILITIES, "2026.2.0-rc2"
        )["system"]

        self.assertEqual(system["Processor"], "Intel(R) Core(TM) Ultra 7 265U")
        self.assertEqual(system["GPU"], "Intel(R) Arc(TM) Graphics")
        self.assertNotIn("NPU", system)
        self.assertEqual(system["Memory"], "31.1 GiB")
        self.assertEqual(system["OS"], "Linux")
        self.assertEqual(system["Kernel"], "6.6.87.2-microsoft-standard-WSL2")
        self.assertEqual(system["Storage"], "846.3 GiB free of 1032.6 GiB")
        self.assertEqual(system["ViPPET Version"], "2026.2.0-rc2")

    def test_missing_capabilities_falls_back_to_unknown(self) -> None:
        system = system_info.collect_system_info(_DEVICES, {}, "Unknown")["system"]

        self.assertEqual(system["Memory"], "Unknown")
        self.assertEqual(system["OS"], "Unknown")
        self.assertEqual(system["Kernel"], "Unknown")
        self.assertEqual(system["Storage"], "Unknown")
        self.assertEqual(system["ViPPET Version"], "Unknown")
        # Devices are independent of capabilities and still reported.
        self.assertEqual(system["Processor"], "Intel(R) Core(TM) Ultra 7 265U")

    def test_partial_capabilities_only_marks_missing_fields_unknown(self) -> None:
        capabilities = {
            "platform": {
                "os": "Linux",
                "system_memory": {"installed_gib": 31.07},
                # kernel and system_storage omitted entirely.
            }
        }

        system = system_info.collect_system_info([], capabilities, "Unknown")["system"]

        self.assertEqual(system["OS"], "Linux")
        self.assertEqual(system["Memory"], "31.1 GiB")
        self.assertEqual(system["Kernel"], "Unknown")
        self.assertEqual(system["Storage"], "Unknown")

    def test_no_devices_detected_omits_device_rows(self) -> None:
        system = system_info.collect_system_info([], _CAPABILITIES, "2026.2.0-rc2")[
            "system"
        ]

        self.assertNotIn("Processor", system)
        self.assertNotIn("GPU", system)
        self.assertNotIn("NPU", system)

    def test_non_numeric_memory_and_storage_fall_back_to_unknown(self) -> None:
        capabilities = {
            "platform": {
                "system_memory": {"installed_gib": "n/a"},
                "system_storage": {
                    "available_gib": None,
                    "total_capacity_gib": 1032.56,
                },
            }
        }

        system = system_info.collect_system_info([], capabilities, "Unknown")["system"]

        self.assertEqual(system["Memory"], "Unknown")
        self.assertEqual(system["Storage"], "Unknown")


if __name__ == "__main__":
    unittest.main()
