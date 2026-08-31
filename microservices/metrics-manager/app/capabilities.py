# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Platform and device capability discovery helpers.

This module inspects local host/container-visible interfaces (/proc, /sys) and
returns a JSON-serializable snapshot suitable for REST responses.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from time import time
from typing import Any, Literal

# Best-effort PCI ID branding fallback used when lspci/pci.ids is unavailable.
_GPU_MODEL_FALLBACK_BY_PCI_ID: dict[str, str] = {
    "8086:a780": "Intel UHD Graphics 770",
    # DG2 desktop Arc (Alchemist)
    "8086:56a0": "Intel Arc A770",
    "8086:56a1": "Intel Arc A750",
    "8086:56a2": "Intel Arc A580",
    # Battlemage G21 desktop/workstation Arc
    "8086:e20b": "Intel Arc B580",
    "8086:e20c": "Intel Arc B570",
    "8086:e211": "Intel Arc Pro B60",
    "8086:e212": "Intel Arc Pro B50",
}


def _read_text(path: str) -> str | None:
    """Read a text file and return stripped contents, or None if unavailable."""
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None


def _parse_size_to_bytes(size_text: str | None) -> int | None:
    """Parse strings like 32K/2M/1G into bytes.

    Returns None when the format is unknown.
    """
    if not size_text:
        return None
    text = size_text.strip().upper()
    match = re.fullmatch(r"(\d+)([KMG])?", text)
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2)
    if unit == "K":
        return value * 1024
    if unit == "M":
        return value * 1024 * 1024
    if unit == "G":
        return value * 1024 * 1024 * 1024
    return value


def _get_mem_total_bytes() -> int | None:
    """Read installed system memory from /proc/meminfo (MemTotal)."""
    meminfo = _read_text("/proc/meminfo") or ""
    for line in meminfo.splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1]) * 1024
    return None


def _system_memory_type() -> dict[str, str | None]:
    """Best-effort memory technology discovery (e.g. DDR4/DDR5/LPDDR5).

    Prefers dmidecode output when available; otherwise returns unknown.
    """

    if shutil.which("dmidecode") is None:
        return {"type": "unknown", "source": "dmidecode_unavailable"}

    try:
        result = subprocess.run(
            ["dmidecode", "-t", "memory"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"type": "unknown", "source": "dmidecode_failed"}

    if result.returncode != 0:
        return {"type": "unknown", "source": "dmidecode_permission_or_error"}

    mem_types: set[str] = set()
    for line in result.stdout.splitlines():
        text = line.strip()
        if not text.startswith("Type:"):
            continue
        # Example values: DDR4, DDR5, LPDDR5, Unknown, RAM
        value = text.split(":", 1)[1].strip().upper()
        if value in {"UNKNOWN", "RAM", "OTHER", ""}:
            continue
        if "DDR" in value:
            mem_types.add(value)

    if not mem_types:
        return {"type": "unknown", "source": "dmidecode_no_ddr_type"}

    # If multiple types are detected across DIMMs, expose a compact combined value.
    combined = "/".join(sorted(mem_types))
    return {"type": combined, "source": "dmidecode"}


def _to_int(value: Any) -> int | None:
    """Best-effort integer parsing for string/int fields."""
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _flatten_lsblk_tree(node: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a flat list of one lsblk node and all descendants."""
    nodes = [node]
    for child in node.get("children", []) or []:
        nodes.extend(_flatten_lsblk_tree(child))
    return nodes


def _mount_available_bytes(mountpoint: str) -> int:
    """Return available bytes for a mounted path, or 0 on error."""
    try:
        return shutil.disk_usage(mountpoint).free
    except OSError:
        return 0


def _storage_display_name(vendor: str | None, manufacturer: str | None, model: str | None, serial: str | None) -> str | None:
    """Pick the best available human-readable storage identity."""
    for value in (vendor, manufacturer, model, serial):
        if value:
            return value.strip() or None
    return None


def _system_storage() -> dict[str, Any]:
    """Collect storage capacity/availability and vendor details."""
    storage_devices: list[dict[str, Any]] = []
    vendor_counts: dict[str, int] = {}
    mountpoints: set[str] = set()

    if shutil.which("lsblk") is not None:
        try:
            result = subprocess.run(
                [
                    "lsblk",
                    "-J",
                    "-b",
                    "-o",
                    "NAME,KNAME,TYPE,SIZE,VENDOR,MODEL,SERIAL,MOUNTPOINT",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                payload = json.loads(result.stdout)
                for disk in payload.get("blockdevices", []):
                    if disk.get("type") != "disk":
                        continue

                    vendor = (disk.get("vendor") or "").strip() or None
                    model = (disk.get("model") or "").strip() or None
                    serial = (disk.get("serial") or "").strip() or None
                    manufacturer = None
                    capacity_bytes = _to_int(disk.get("size"))
                    resolved_name = _storage_display_name(vendor, manufacturer, model, serial)

                    disk_mounts: set[str] = set()
                    for node in _flatten_lsblk_tree(disk):
                        mountpoint = node.get("mountpoint")
                        if mountpoint and isinstance(mountpoint, str):
                            disk_mounts.add(mountpoint)

                    available_bytes = sum(_mount_available_bytes(mp) for mp in sorted(disk_mounts))
                    mountpoints.update(disk_mounts)

                    storage_devices.append(
                        {
                            "id": disk.get("name") or disk.get("kname"),
                            "vendor": vendor,
                            "manufacturer": manufacturer,
                            "model": model,
                            "serial": serial,
                            "resolved_vendor": resolved_name,
                            "capacity_bytes": capacity_bytes,
                            "available_bytes": available_bytes if available_bytes > 0 else None,
                        }
                    )
                    if resolved_name:
                        vendor_counts[resolved_name] = vendor_counts.get(resolved_name, 0) + 1
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            storage_devices = []

    if not storage_devices:
        for block in sorted(Path("/sys/block").glob("*")):
            name = block.name
            if name.startswith(("loop", "ram", "zram", "fd", "sr", "dm-")):
                continue

            sectors = _read_text(str(block / "size"))
            capacity_bytes = int(sectors) * 512 if sectors and sectors.isdigit() else None
            vendor = _read_text(str(block / "device/vendor"))
            manufacturer = _read_text(str(block / "device/manufacturer"))
            model = _read_text(str(block / "device/model"))
            serial = _read_text(str(block / "device/serial"))
            resolved_name = _storage_display_name(vendor, manufacturer, model, serial)

            storage_devices.append(
                {
                    "id": name,
                    "vendor": vendor,
                    "manufacturer": manufacturer,
                    "model": model,
                    "serial": serial,
                    "resolved_vendor": resolved_name,
                    "capacity_bytes": capacity_bytes,
                    "available_bytes": None,
                }
            )
            if resolved_name:
                vendor_counts[resolved_name] = vendor_counts.get(resolved_name, 0) + 1

    total_capacity_bytes = sum(
        int(device["capacity_bytes"])
        for device in storage_devices
        if isinstance(device.get("capacity_bytes"), int)
    )

    if mountpoints:
        available_bytes = sum(_mount_available_bytes(mp) for mp in sorted(mountpoints))
    else:
        available_bytes = _mount_available_bytes("/")

    return {
        "total_capacity_bytes": total_capacity_bytes if total_capacity_bytes > 0 else None,
        "total_capacity_gib": (
            round(total_capacity_bytes / (1024**3), 2) if total_capacity_bytes > 0 else None
        ),
        "available_bytes": available_bytes if available_bytes > 0 else None,
        "available_gib": round(available_bytes / (1024**3), 2) if available_bytes > 0 else None,
        "vendor_details": [
            {"vendor": vendor, "device_count": count}
            for vendor, count in sorted(vendor_counts.items())
        ],
        "devices": storage_devices,
    }


def _vendor_name(vendor: str | None) -> str | None:
    """Convert vendor identifiers to readable vendor names when possible."""
    if not vendor:
        return None

    normalized = vendor.strip().lower()
    pci_vendor_map = {
        "0x8086": "Intel",
        "0x10de": "NVIDIA",
        "0x1002": "AMD",
        "0x1022": "AMD",
    }
    if normalized in pci_vendor_map:
        return pci_vendor_map[normalized]

    text_vendor_map = {
        "genuineintel": "Intel",
        "authenticamd": "AMD",
    }
    if normalized in text_vendor_map:
        return text_vendor_map[normalized]

    return vendor


def _hostname() -> str:
    """Resolve the most useful hostname for telemetry and capability reports."""
    env_hostname = os.environ.get("METRICS_MANAGER_HOSTNAME")
    if env_hostname:
        return env_hostname

    host_root_hostname = _read_text("/proc/1/root/etc/hostname")
    if host_root_hostname:
        return host_root_hostname

    return os.uname().nodename


def _system_identity() -> dict[str, Any]:
    """Collect best-effort system identity information from DMI/sysfs."""
    return {
        "hostname": _hostname(),
        "vendor": _read_text("/sys/class/dmi/id/sys_vendor"),
        "product": _read_text("/sys/class/dmi/id/product_name"),
        "product_version": _read_text("/sys/class/dmi/id/product_version"),
    }


def _cpu_frequency_specs() -> dict[str, Any]:
    """Collect CPU frequency specification (not runtime frequency)."""
    cpufreq_root = Path("/sys/devices/system/cpu/cpu0/cpufreq")
    if not cpufreq_root.exists():
        return {
            "supported": False,
            "min_hz": None,
            "base_hz": None,
            "max_hz": None,
            "scaling_driver": None,
        }

    def _khz_to_hz(path: Path) -> int | None:
        raw = _read_text(str(path))
        return int(raw) * 1000 if raw and raw.isdigit() else None

    return {
        "supported": True,
        "min_hz": _khz_to_hz(cpufreq_root / "cpuinfo_min_freq"),
        "base_hz": _khz_to_hz(cpufreq_root / "base_frequency"),
        "max_hz": _khz_to_hz(cpufreq_root / "cpuinfo_max_freq"),
        "scaling_driver": _read_text(str(cpufreq_root / "scaling_driver")),
    }


def _cpu_cache_specs() -> list[dict[str, Any]]:
    """Collect CPU cache hierarchy from sysfs."""
    cache_root = Path("/sys/devices/system/cpu/cpu0/cache")
    if not cache_root.exists():
        return []

    entries: list[dict[str, Any]] = []
    for index_dir in sorted(cache_root.glob("index*")):
        entries.append(
            {
                "level": int(_read_text(str(index_dir / "level")) or "0") or None,
                "type": _read_text(str(index_dir / "type")),
                "size_bytes": _parse_size_to_bytes(_read_text(str(index_dir / "size"))),
                "line_size_bytes": (
                    int(_read_text(str(index_dir / "coherency_line_size")) or "0") or None
                ),
                "ways_of_associativity": (
                    int(_read_text(str(index_dir / "ways_of_associativity")) or "0") or None
                ),
            }
        )

    return entries


def _cpu_core_type_counts(logical_cores: int) -> dict[str, Any]:
    """Infer E-core/P-core counts when kernel core_type is available.

    Linux commonly reports core_type values as:
    - 1: efficiency/atom
    - 2: performance/core
    These mappings are not guaranteed on every platform, so raw values are
    also returned for transparency.
    """
    core_type_files = sorted(Path("/sys/devices/system/cpu").glob("cpu[0-9]*/topology/core_type"))
    if not core_type_files:
        return {
            "p_cores": None,
            "e_cores": None,
            "raw_core_type_counts": {},
            "source": "unavailable",
        }

    type_counts: dict[str, int] = {}
    for file_path in core_type_files:
        raw = _read_text(str(file_path))
        if raw is None:
            continue
        type_counts[raw] = type_counts.get(raw, 0) + 1

    return {
        "p_cores": type_counts.get("2"),
        "e_cores": type_counts.get("1"),
        "raw_core_type_counts": type_counts,
        "source": "sysfs_core_type",
        "logical_cores_seen": logical_cores,
    }


def _cpu_specs() -> dict[str, Any]:
    """Extract CPU model and core metadata from /proc/cpuinfo when available."""
    cpuinfo = _read_text("/proc/cpuinfo") or ""
    model_name: str | None = None
    vendor_id: str | None = None
    logical_cores = 0
    physical_ids: set[str] = set()
    core_ids_by_package: set[tuple[str, str]] = set()

    for raw_line in cpuinfo.splitlines():
        if not raw_line.strip():
            continue
        if raw_line.startswith("model name") and model_name is None:
            parts = raw_line.split(":", 1)
            if len(parts) == 2:
                model_name = parts[1].strip()
        if raw_line.startswith("vendor_id") and vendor_id is None:
            parts = raw_line.split(":", 1)
            if len(parts) == 2:
                vendor_id = parts[1].strip()
        if raw_line.startswith("processor"):
            logical_cores += 1

    # Second pass to extract physical/core ids by block.
    for block in cpuinfo.split("\n\n"):
        package_id: str | None = None
        core_id: str | None = None
        for line in block.splitlines():
            if line.startswith("physical id"):
                package_id = line.split(":", 1)[1].strip()
            if line.startswith("core id"):
                core_id = line.split(":", 1)[1].strip()
        if package_id is not None:
            physical_ids.add(package_id)
        if package_id is not None and core_id is not None:
            core_ids_by_package.add((package_id, core_id))

    physical_cores = len(core_ids_by_package) if core_ids_by_package else None
    socket_count = len(physical_ids) if physical_ids else None

    core_type = _cpu_core_type_counts(logical_cores)

    return {
        "model": model_name,
        "vendor": vendor_id,
        "logical_cores": logical_cores or None,
        "physical_cores": physical_cores,
        "sockets": socket_count,
        "e_cores": core_type.get("e_cores"),
        "p_cores": core_type.get("p_cores"),
        "core_type_metadata": {
            "raw_core_type_counts": core_type.get("raw_core_type_counts"),
            "source": core_type.get("source"),
        },
        "frequency": _cpu_frequency_specs(),
        "cache": _cpu_cache_specs(),
    }


def _gpu_model_by_pci_id() -> dict[str, str]:
    """Build a map of PCI vendor:device IDs to GPU model names via lspci.

    Returns a dict like {"8086:a780": "Intel UHD Graphics 770", ...}
    Returns empty dict if lspci is unavailable.
    """
    models: dict[str, str] = dict(_GPU_MODEL_FALLBACK_BY_PCI_ID)
    try:
        result = subprocess.run(
            ["lspci", "-nn"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            return models

        for line in result.stdout.splitlines():
            # Parse the final vendor:device token from lines like:
            # "00:02.0 Display controller [0380]: ... [UHD Graphics 770] [8086:a780] (rev 04)"
            pci_ids = re.findall(r"\[([0-9a-fA-F]{4}:[0-9a-fA-F]{4})\]", line)
            if not pci_ids:
                continue

            pci_id = pci_ids[-1].lower()

            # Prefer a bracketed marketing/model segment before the PCI ID.
            before_pci = line.split(f"[{pci_ids[-1]}]", 1)[0]
            model_matches = re.findall(r"\[([^\[\]]+)\]", before_pci)
            if model_matches:
                candidate = model_matches[-1].strip()
                if candidate and ":" not in candidate:
                    models[pci_id] = candidate
                    continue

            # Fallback: infer a readable tail from text after the final colon.
            tail = before_pci.rsplit(":", 1)[-1].strip()
            if tail:
                models[pci_id] = tail
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return models


def _gpu_devices() -> list[dict[str, Any]]:
    """Discover GPUs via /sys/class/drm/card*.

    Classification heuristic:
    - boot_vga=1 is treated as iGPU (primary display adapter)
    - other cards are treated as dGPU

    Note: Only enumerates actual GPU devices (card0, card1, etc.),
    not display connectors (card0-DP-1, card0-HDMI-A-1, etc.).
    """
    devices: list[dict[str, Any]] = []
    gpu_models = _gpu_model_by_pci_id()

    for card in sorted(Path("/sys/class/drm").glob("card[0-9]*")):
        # Skip display connectors like card0-DP-1, card1-HDMI-A-2
        if "-" in card.name:
            continue

        device_dir = card / "device"
        if not device_dir.exists():
            continue

        vendor = _read_text(str(device_dir / "vendor"))
        pci_device = _read_text(str(device_dir / "device"))
        boot_vga = _read_text(str(device_dir / "boot_vga"))
        uevent = _read_text(str(device_dir / "uevent")) or ""

        driver: str | None = None
        for line in uevent.splitlines():
            if line.startswith("DRIVER="):
                driver = line.split("=", 1)[1]
                break

        # Lookup GPU model by vendor:device PCI ID
        model: str | None = None
        if vendor and pci_device:
            pci_id = f"{vendor[2:].lower()}:{pci_device[2:].lower()}"
            model = gpu_models.get(pci_id)

        # Best-effort memory capacity paths across DRM drivers.
        vram_total_bytes = None
        for mem_path in (
            device_dir / "mem_info_vram_total",
            device_dir / "lmem_total_bytes",
            device_dir / "vram_total",
        ):
            raw = _read_text(str(mem_path))
            if raw and raw.isdigit():
                vram_total_bytes = int(raw)
                break

        bdf = device_dir.resolve().name.lower()
        model_lower = (model or "").lower()

        # boot_vga can point to the active display adapter and is not always a
        # reliable iGPU/dGPU discriminator. Prefer PCI topology/model hints.
        if bdf.startswith("0000:00:02."):
            category = "igpu"
        elif "arc" in model_lower:
            category = "dgpu"
        elif any(token in model_lower for token in ("uhd", "iris", "xe")):
            category = "igpu"
        else:
            category = "igpu" if boot_vga == "1" else "dgpu"

        devices.append(
            {
                "id": card.name,
                "category": category,
                "present": True,
                "model": model,
                "vendor": vendor,
                "vendor_name": _vendor_name(vendor),
                "pci_device": pci_device,
                "driver": driver,
                "capabilities": [
                    "render",
                    "compute",
                    "media",
                ],
                "specs": {
                    "memory": {
                        "type": "vram" if vram_total_bytes is not None else "shared_or_unknown",
                        "total_bytes": vram_total_bytes,
                    }
                },
                "details": {
                    "sysfs_path": str(device_dir),
                    "pci_bdf": bdf,
                    "boot_vga": boot_vga,
                },
            }
        )

    return devices


def _npu_device() -> dict[str, Any]:
    """Discover Intel NPU capabilities via intel_vpu sysfs driver path."""
    driver_root = Path("/sys/bus/pci/drivers/intel_vpu")
    if not driver_root.exists():
        return {
            "id": "intel_vpu",
            "category": "npu",
            "present": False,
            "model": None,
            "vendor": None,
            "pci_device": None,
            "driver": "intel_vpu",
            "capabilities": [],
            "specs": {
                "memory": {
                    "type": "unknown",
                    "total_bytes": None,
                }
            },
            "details": {
                "reason": "intel_vpu driver path not found",
            },
        }

    bdf_path = next((entry for entry in driver_root.iterdir() if entry.name.startswith("0000:")), None)
    if bdf_path is None:
        return {
            "id": "intel_vpu",
            "category": "npu",
            "present": False,
            "model": None,
            "vendor": None,
            "pci_device": None,
            "driver": "intel_vpu",
            "capabilities": [],
            "specs": {
                "memory": {
                    "type": "unknown",
                    "total_bytes": None,
                }
            },
            "details": {
                "reason": "intel_vpu driver present but no bound PCI device",
            },
        }

    memory_util_path = bdf_path / "npu_memory_utilization"

    vendor = _read_text(str(bdf_path / "vendor"))

    return {
        "id": bdf_path.name,
        "category": "npu",
        "present": True,
        "model": None,
        "vendor": vendor,
        "vendor_name": _vendor_name(vendor),
        "pci_device": _read_text(str(bdf_path / "device")),
        "driver": "intel_vpu",
        "capabilities": [
            "inference_acceleration",
            "telemetry_sysfs",
        ],
        "specs": {
            "memory": {
                "type": "on_device_or_shared_unknown",
                "total_bytes": None,
            },
            "memory_utilization_supported": memory_util_path.exists(),
        },
        "details": {
            "sysfs_path": str(bdf_path),
        },
    }


def _expanded_capabilities_snapshot() -> dict[str, Any]:
    """Build an expanded platform/device capabilities snapshot."""
    cpu_specs = _cpu_specs()
    system_identity = _system_identity()
    devices: list[dict[str, Any]] = [
        {
            "id": "cpu",
            "category": "cpu",
            "present": True,
            "model": cpu_specs.get("model"),
            "vendor": cpu_specs.get("vendor"),
            "vendor_name": _vendor_name(cpu_specs.get("vendor")),
            "pci_device": None,
            "driver": None,
            "capabilities": [
                "general_purpose_compute",
                "simd_extensions_unknown",
            ],
            "specs": {
                "topology": {
                    "logical_cores": cpu_specs.get("logical_cores"),
                    "physical_cores": cpu_specs.get("physical_cores"),
                    "sockets": cpu_specs.get("sockets"),
                    "p_cores": cpu_specs.get("p_cores"),
                    "e_cores": cpu_specs.get("e_cores"),
                    "core_type_metadata": cpu_specs.get("core_type_metadata"),
                },
                "frequency": cpu_specs.get("frequency"),
                "cache": cpu_specs.get("cache"),
            },
            "details": {
                "source": "/proc/cpuinfo,/sys/devices/system/cpu",
            },
        }
    ]

    devices.extend(_gpu_devices())
    devices.append(_npu_device())

    igpu_count = sum(1 for d in devices if d.get("category") == "igpu" and d.get("present"))
    dgpu_count = sum(1 for d in devices if d.get("category") == "dgpu" and d.get("present"))
    npu_count = sum(1 for d in devices if d.get("category") == "npu" and d.get("present"))
    cpu_count = sum(1 for d in devices if d.get("category") == "cpu" and d.get("present"))
    system_memory_bytes = _get_mem_total_bytes()
    memory_type_info = _system_memory_type()
    storage_info = _system_storage()

    return {
        "generated_at": int(time()),
        "profile": "expanded",
        "categories": {
            "platform_profile": "Technical platform inventory",
            "device_inventory": "Per-device technical specifications",
        },
        "platform": {
            "hostname": system_identity.get("hostname"),
            "vendor": system_identity.get("vendor"),
            "vendor_name": _vendor_name(system_identity.get("vendor")),
            "os": platform.system(),
            "kernel": platform.release(),
            "architecture": platform.machine(),
            "system": system_identity,
            "system_memory": {
                "installed_bytes": system_memory_bytes,
                "installed_gib": (
                    round(system_memory_bytes / (1024**3), 2)
                    if system_memory_bytes is not None
                    else None
                ),
                "type": memory_type_info.get("type"),
            },
            "system_storage": {
                k: v for k, v in storage_info.items() if k != "source"
            },
            "device_summary": {
                "cpu": cpu_count,
                "igpu": igpu_count,
                "dgpu": dgpu_count,
                "npu": npu_count,
            },
        },
        "devices": devices,
    }


def _device_commercial_reference(device: dict[str, Any]) -> str:
    """Return a user-friendly commercial reference string for minimal profile."""
    category = device.get("category")
    model = device.get("model")
    if model:
        return str(model)
    if category == "cpu":
        return "CPU"
    if category == "igpu":
        return "Integrated GPU"
    if category == "dgpu":
        return "Discrete GPU"
    if category == "npu":
        return "Intel NPU"
    return "Unknown device"


def _minimal_from_expanded(expanded: dict[str, Any]) -> dict[str, Any]:
    """Create a categorized high-level minimal capability response."""
    minimal_devices: list[dict[str, Any]] = []
    for device in expanded.get("devices", []):
        category = device.get("category")
        specs = device.get("specs", {})
        details = {}

        if category == "cpu":
            topology = specs.get("topology", {}) if isinstance(specs, dict) else {}
            details = {
                "cores": {
                    "logical": topology.get("logical_cores"),
                    "physical": topology.get("physical_cores"),
                    "p_cores": topology.get("p_cores"),
                    "e_cores": topology.get("e_cores"),
                },
                "sockets": topology.get("sockets"),
            }
        else:
            memory = specs.get("memory", {}) if isinstance(specs, dict) else {}
            details = {
                "memory": {
                    "type": memory.get("type"),
                    "total_bytes": memory.get("total_bytes"),
                }
            }

        minimal_devices.append(
            {
                "id": device.get("id"),
                "category": category,
                "present": device.get("present"),
                "commercial_reference": _device_commercial_reference(device),
                "vendor": device.get("vendor"),
                "vendor_name": device.get("vendor_name"),
                "details": details,
            }
        )

    platform = expanded.get("platform", {})
    return {
        "generated_at": expanded.get("generated_at"),
        "profile": "minimal",
        "categories": {
            "platform_overview": "High-level host and memory summary",
            "compute_device_overview": "Commercial-style list of available compute devices",
        },
        "platform": {
            "hostname": platform.get("hostname"),
            "vendor": platform.get("vendor"),
            "vendor_name": platform.get("vendor_name"),
            "os": platform.get("os"),
            "kernel": platform.get("kernel"),
            "architecture": platform.get("architecture"),
            "system": platform.get("system"),
            "system_memory": platform.get("system_memory"),
            "system_storage": platform.get("system_storage"),
            "device_summary": platform.get("device_summary"),
        },
        "devices": minimal_devices,
    }


def get_capabilities_snapshot(profile: Literal["minimal", "expanded"] = "minimal") -> dict[str, Any]:
    """Build a platform/device capability snapshot in requested profile format."""
    expanded = _expanded_capabilities_snapshot()
    if profile == "expanded":
        return expanded
    return _minimal_from_expanded(expanded)
