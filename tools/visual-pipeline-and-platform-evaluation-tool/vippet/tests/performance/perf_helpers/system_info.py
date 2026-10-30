# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Build the benchmark report's "System" info block.

Combines the ViPPET /devices snapshot (CPU/GPU/NPU names) with the
metrics-manager /api/v1/capabilities snapshot (memory/OS/kernel/storage)
and the ViPPET /status version, all captured once at pre-flight time.
"""

from typing import Any

UNKNOWN = "Unknown"


def _format_gib(value: Any) -> str | None:
    """Render a GiB value with 1 decimal, or None if not a usable number."""
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return None


def collect_system_info(
    devices: list[dict[str, Any]],
    capabilities: dict[str, Any],
    vippet_version: str,
) -> dict[str, Any]:
    """Build system details for the benchmark report.

    CPU/GPU/NPU come from the /devices snapshot and are only added when
    detected. Memory/OS/Kernel/Storage/ViPPET Version come from the
    capabilities snapshot and /status, and are always present, with
    "Unknown" standing in for anything unavailable so a missing field stays
    visible in the artefact rather than disappearing.
    """
    devices_info: dict[str, str] = {}
    for device in devices:
        family = str(device.get("device_family", "")).upper()
        full_name = device.get("full_device_name", "")
        if family and full_name:
            devices_info[family] = full_name

    system: dict[str, str] = {}
    if devices_info.get("CPU"):
        system["Processor"] = devices_info["CPU"]
    if devices_info.get("GPU"):
        system["GPU"] = devices_info["GPU"]
    if devices_info.get("NPU"):
        system["NPU"] = devices_info["NPU"]

    platform_info = capabilities.get("platform") or {}
    memory = platform_info.get("system_memory") or {}
    memory_gib = _format_gib(memory.get("installed_gib"))
    system["Memory"] = f"{memory_gib} GiB" if memory_gib else UNKNOWN
    system["OS"] = platform_info.get("os") or UNKNOWN
    system["Kernel"] = platform_info.get("kernel") or UNKNOWN

    storage = platform_info.get("system_storage") or {}
    available_gib = _format_gib(storage.get("available_gib"))
    total_gib = _format_gib(storage.get("total_capacity_gib"))
    system["Storage"] = (
        f"{available_gib} GiB free of {total_gib} GiB"
        if available_gib and total_gib
        else UNKNOWN
    )

    system["ViPPET Version"] = vippet_version or UNKNOWN

    return {"system": system}
