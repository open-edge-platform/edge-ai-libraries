# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Platform and device capability discovery helpers.

This module inspects local host/container-visible interfaces (/proc, /sys) and
returns a JSON-serializable snapshot suitable for REST responses.

Unified Intel GPU Device Registry (source-of-truth for all Intel GPUs):
This registry covers Intel discrete/integrated GPU generations and is used for
PCI ID classification and software capability inference (OpenVINO support,
media/rendering capability).
"""

from __future__ import annotations

import importlib
import importlib.util as importlib_util
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from time import time
from typing import Any, Literal

# ============================================================================
# Unified Intel GPU Device Registry (Single Source of Truth)
# ============================================================================
# Map: pci_id (lowercase "vendor:device" hex) -> device_info dict
# device_info includes: name, architecture, pci_id, sw_capabilities_template
# sw_capabilities_template guides OpenVINO/inference support classification
_INTEL_GPU_DEVICE_REGISTRY: dict[str, dict[str, Any]] = {
    # ========== Xe2 Architecture (Latest, Full OpenVINO GPU Support) ==========
    "8086:e212": {"name": "Intel Arc B50", "arch": "Xe2", "category": "dgpu", "min_kernel": "6.14"},
    "8086:e211": {"name": "Intel Arc B60", "arch": "Xe2", "category": "dgpu", "min_kernel": "6.14"},
    "8086:e20b": {"name": "Intel Arc B580", "arch": "Xe2", "category": "dgpu", "min_kernel": "6.11"},
    "8086:e20c": {"name": "Intel Arc B570", "arch": "Xe2", "category": "dgpu", "min_kernel": "6.11"},
    "8086:6420": {"name": "Intel Graphics (Lunar Lake)", "arch": "Xe2", "category": "igpu", "min_kernel": "6.10"},
    "8086:6422": {"name": "Intel Graphics (Lunar Lake)", "arch": "Xe2", "category": "igpu", "min_kernel": "6.10"},
    # ========== Xe-LPG Architecture (Arrow Lake, Meteor Lake, Full OV GPU) ==========
    "8086:7d51": {"name": "Intel Graphics (Arrow Lake-H)", "arch": "Xe-LPG", "category": "igpu", "min_kernel": "6.9"},
    "8086:7d67": {"name": "Intel Graphics (Arrow Lake-S)", "arch": "Xe-LPG", "category": "igpu", "min_kernel": "6.7"},
    "8086:7d41": {"name": "Intel Graphics (Arrow Lake-U)", "arch": "Xe-LPG", "category": "igpu", "min_kernel": "6.9"},
    "8086:7dd5": {"name": "Intel Graphics (Meteor Lake-G)", "arch": "Xe-LPG", "category": "igpu", "min_kernel": "6.6"},
    "8086:7d55": {"name": "Intel Graphics (Meteor Lake-H)", "arch": "Xe-LPG", "category": "igpu", "min_kernel": "6.6"},
    "8086:7d60": {"name": "Intel Graphics (Meteor Lake-S)", "arch": "Xe-LPG", "category": "igpu", "min_kernel": "6.6"},
    "8086:7d45": {"name": "Intel Graphics (Meteor Lake-U)", "arch": "Xe-LPG", "category": "igpu", "min_kernel": "6.6"},
    "8086:7d40": {"name": "Intel Graphics (Meteor Lake-P)", "arch": "Xe-LPG", "category": "igpu", "min_kernel": "6.6"},
    # ========== Xe-HPG Architecture (Arc A/Pro Series, Full OpenVINO GPU) ==========
    "8086:56a0": {"name": "Intel Arc A770", "arch": "Xe-HPG", "category": "dgpu", "min_kernel": "6.2"},
    "8086:56a1": {"name": "Intel Arc A750", "arch": "Xe-HPG", "category": "dgpu", "min_kernel": "6.2"},
    "8086:56a2": {"name": "Intel Arc A580", "arch": "Xe-HPG", "category": "dgpu", "min_kernel": "6.2"},
    "8086:56a3": {"name": "Intel Arc A380", "arch": "Xe-HPG", "category": "dgpu", "min_kernel": "6.2"},
    "8086:56a4": {"name": "Intel Arc A310", "arch": "Xe-HPG", "category": "dgpu", "min_kernel": "6.2"},
    "8086:56a5": {"name": "Intel Arc Pro A60", "arch": "Xe-HPG", "category": "dgpu", "min_kernel": "6.2"},
    "8086:56a6": {"name": "Intel Arc Pro A60M", "arch": "Xe-HPG", "category": "dgpu", "min_kernel": "6.2"},
    "8086:5690": {"name": "Intel Arc A370M", "arch": "Xe-HPG", "category": "dgpu", "min_kernel": "6.2"},
    "8086:5691": {"name": "Intel Arc A350M", "arch": "Xe-HPG", "category": "dgpu", "min_kernel": "6.2"},
    "8086:5692": {"name": "Intel Arc A550M", "arch": "Xe-HPG", "category": "dgpu", "min_kernel": "6.2"},
    "8086:5693": {"name": "Intel Arc A370M", "arch": "Xe-HPG", "category": "dgpu", "min_kernel": "6.2"},
    "8086:5694": {"name": "Intel Arc A350M", "arch": "Xe-HPG", "category": "dgpu", "min_kernel": "6.2"},
    "8086:5695": {"name": "Intel Arc A730M", "arch": "Xe-HPG", "category": "dgpu", "min_kernel": "6.2"},
    "8086:5696": {"name": "Intel Arc A550M", "arch": "Xe-HPG", "category": "dgpu", "min_kernel": "6.2"},
    "8086:5697": {"name": "Intel Arc A770M", "arch": "Xe-HPG", "category": "dgpu", "min_kernel": "6.2"},
    "8086:56b0": {"name": "Intel Arc Pro A40", "arch": "Xe-HPG", "category": "dgpu", "min_kernel": "6.2"},
    "8086:56b1": {"name": "Intel Arc Pro A50", "arch": "Xe-HPG", "category": "dgpu", "min_kernel": "6.2"},
    "8086:56b2": {"name": "Intel Arc Pro A30M", "arch": "Xe-HPG", "category": "dgpu", "min_kernel": "6.2"},
    "8086:56b3": {"name": "Intel Arc Pro A40", "arch": "Xe-HPG", "category": "dgpu", "min_kernel": "6.2"},
    # ========== Xe Architecture (Raptor Lake, Alder Lake, Tiger Lake) ==========
    "8086:a788": {"name": "Intel UHD Graphics 770", "arch": "Xe", "category": "igpu", "min_kernel": "6.7"},
    "8086:a789": {"name": "Intel UHD Graphics 750", "arch": "Xe", "category": "igpu", "min_kernel": "6.7"},
    "8086:a78a": {"name": "Intel UHD Graphics 730", "arch": "Xe", "category": "igpu", "min_kernel": "6.7"},
    "8086:a78b": {"name": "Intel UHD Graphics 710", "arch": "Xe", "category": "igpu", "min_kernel": "6.7"},
    "8086:a780": {"name": "Intel UHD Graphics 770", "arch": "Xe", "category": "igpu", "min_kernel": "6.7"},
    "8086:a720": {"name": "Intel Iris Xe Graphics", "arch": "Xe", "category": "igpu", "min_kernel": "6.7"},
    "8086:a721": {"name": "Intel Iris Xe Graphics", "arch": "Xe", "category": "igpu", "min_kernel": "6.7"},
    "8086:a7a0": {"name": "Intel Iris Xe Graphics", "arch": "Xe", "category": "igpu", "min_kernel": "6.7"},
    "8086:a7a1": {"name": "Intel Iris Xe Graphics", "arch": "Xe", "category": "igpu", "min_kernel": "6.7"},
    "8086:a7ac": {"name": "Intel Graphics", "arch": "Xe", "category": "igpu", "min_kernel": "6.7"},
    "8086:a7ad": {"name": "Intel Graphics", "arch": "Xe", "category": "igpu", "min_kernel": "6.7"},
    # DG1 discrete
    "8086:4905": {"name": "Intel Iris Xe MAX Graphics", "arch": "Xe", "category": "dgpu", "min_kernel": "5.16"},
    "8086:4907": {"name": "Intel Server GPU", "arch": "Xe", "category": "dgpu", "min_kernel": "5.16"},
    "8086:4908": {"name": "Intel Iris Xe MAX Graphics", "arch": "Xe", "category": "dgpu", "min_kernel": "5.16"},
    "8086:4909": {"name": "Intel Iris Xe MAX Graphics", "arch": "Xe", "category": "dgpu", "min_kernel": "5.16"},
    # Alder Lake
    "8086:4680": {"name": "Intel UHD Graphics 770", "arch": "Xe", "category": "igpu", "min_kernel": "5.17"},
    "8086:4682": {"name": "Intel UHD Graphics 730", "arch": "Xe", "category": "igpu", "min_kernel": "5.17"},
    "8086:4690": {"name": "Intel UHD Graphics 770", "arch": "Xe", "category": "igpu", "min_kernel": "5.17"},
    "8086:4692": {"name": "Intel UHD Graphics 730", "arch": "Xe", "category": "igpu", "min_kernel": "5.17"},
    "8086:4693": {"name": "Intel UHD Graphics 710", "arch": "Xe", "category": "igpu", "min_kernel": "5.17"},
    # Tiger Lake
    "8086:9a49": {"name": "Intel Iris Xe Graphics", "arch": "Xe", "category": "igpu", "min_kernel": "5.9"},
    "8086:9a40": {"name": "Intel Iris Xe Graphics", "arch": "Xe", "category": "igpu", "min_kernel": "5.9"},
    "8086:9a60": {"name": "Intel UHD Graphics", "arch": "Xe", "category": "igpu", "min_kernel": "5.9"},
    "8086:9a68": {"name": "Intel UHD Graphics", "arch": "Xe", "category": "igpu", "min_kernel": "5.9"},
    # Gen12 (Rocket Lake)
    "8086:4c80": {"name": "Intel UHD Graphics 750", "arch": "Gen12", "category": "igpu", "min_kernel": "5.11"},
    "8086:4c8a": {"name": "Intel UHD Graphics 730", "arch": "Gen12", "category": "igpu", "min_kernel": "5.11"},
    # Gen11 (Ice Lake, Elkhart Lake)
    "8086:8a50": {"name": "Intel Iris Plus Graphics", "arch": "Gen11", "category": "igpu", "min_kernel": "5.2"},
    "8086:8a56": {"name": "Intel UHD Graphics", "arch": "Gen11", "category": "igpu", "min_kernel": "5.2"},
    "8086:4551": {"name": "Intel UHD Graphics (Elkhart Lake)", "arch": "Gen11", "category": "igpu", "min_kernel": "5.8"},
    # Gen9.5 (Coffee Lake)
    "8086:3e90": {"name": "Intel UHD Graphics 610", "arch": "Gen9.5", "category": "igpu", "min_kernel": "4.20"},
    "8086:3e91": {"name": "Intel UHD Graphics 630", "arch": "Gen9.5", "category": "igpu", "min_kernel": "4.20"},
}

# Best-effort PCI ID branding fallback used when lspci/pci.ids is unavailable.
_GPU_MODEL_FALLBACK_BY_PCI_ID: dict[str, str] = {
    pci_id: info["name"] for pci_id, info in _INTEL_GPU_DEVICE_REGISTRY.items()
}


def _detect_inference_runtimes() -> dict[str, bool]:
    """Detect available inference runtimes on the system.

    Returns a dict mapping runtime names to availability (bool).
    Checks for Python packages and binary tools.
    """

    # Capability reporting prioritizes lightweight functional probes grouped by
    # runtime API family over static lookup-table assumptions.

    def _module_or_none(module_name: str) -> Any | None:
        try:
            if importlib_util.find_spec(module_name) is None:
                return None
            return importlib.import_module(module_name)
        except (ImportError, ModuleNotFoundError, ValueError):
            return None

    def _probe_openvino() -> bool:
        ov_mod = _module_or_none("openvino")
        if ov_mod is None:
            return False

        core_cls = getattr(ov_mod, "Core", None)
        if core_cls is None:
            runtime_mod = _module_or_none("openvino.runtime")
            core_cls = getattr(runtime_mod, "Core", None) if runtime_mod else None
        if core_cls is None:
            return False

        try:
            core = core_cls()
            _ = list(getattr(core, "available_devices", []) or [])
            return True
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False

    def _probe_tensorflow() -> bool:
        tf_mod = _module_or_none("tensorflow")
        if tf_mod is None:
            return False
        try:
            _ = tf_mod.config.list_physical_devices()
            return True
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False

    def _probe_pytorch() -> bool:
        torch_mod = _module_or_none("torch")
        if torch_mod is None:
            return False
        try:
            _ = getattr(torch_mod, "__version__", None)
            cuda_ns = getattr(torch_mod, "cuda", None)
            if cuda_ns is not None and hasattr(cuda_ns, "is_available"):
                _ = cuda_ns.is_available()
            return True
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False

    def _probe_onnxruntime() -> bool:
        ort_mod = _module_or_none("onnxruntime")
        if ort_mod is None:
            return False
        try:
            providers = ort_mod.get_available_providers()
            return len(providers) > 0
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False

    def _probe_tflite() -> bool:
        tflite_mod = _module_or_none("tensorflow.lite")
        if tflite_mod is None:
            return False
        try:
            _ = tflite_mod.Interpreter
            return True
        except AttributeError:
            return False

    def _probe_llama_cpp() -> bool:
        if shutil.which("llama-cli") is not None or shutil.which("llama-server") is not None:
            return True
        llama_mod = _module_or_none("llama_cpp")
        if llama_mod is None:
            return False
        return hasattr(llama_mod, "Llama")

    runtimes = {
        "openvino": _probe_openvino(),
        "tensorflow": _probe_tensorflow(),
        "pytorch": _probe_pytorch(),
        "onnx_runtime": _probe_onnxruntime(),
        "tflite": _probe_tflite(),
        "llama_cpp": _probe_llama_cpp(),
    }

    return runtimes


def _detect_openvino_available_devices() -> set[str]:
    """Detect OpenVINO-exposed logical device classes.

    Returns a normalized set like {"CPU", "GPU", "NPU"} when available.
    """
    ov_mod: Any | None = None
    try:
        if importlib_util.find_spec("openvino") is None:
            return set()
        ov_mod = importlib.import_module("openvino")
    except (ImportError, ModuleNotFoundError, ValueError):
        return set()

    core_cls = getattr(ov_mod, "Core", None)
    if core_cls is None:
        try:
            runtime_mod = importlib.import_module("openvino.runtime")
            core_cls = getattr(runtime_mod, "Core", None)
        except (ImportError, ModuleNotFoundError, ValueError):
            return set()
    if core_cls is None:
        return set()

    try:
        core = core_cls()
        devices = list(getattr(core, "available_devices", []) or [])
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return set()

    normalized: set[str] = set()
    for device in devices:
        value = str(device).upper()
        if value.startswith("CPU"):
            normalized.add("CPU")
        elif value.startswith("GPU"):
            normalized.add("GPU")
        elif value.startswith(("NPU", "VPU")):
            normalized.add("NPU")
    return normalized


def _detect_runtime_media_codecs() -> dict[str, list[str]]:
    """Best-effort media codec capability probe from runtime tooling.

    Uses `vainfo` when available and maps supported profiles/entry points
    to normalized capability strings used by this service.
    """
    by_category: dict[str, list[str]] = {
        "cpu": [],
        "igpu": [],
        "dgpu": [],
        "npu": [],
    }

    if shutil.which("vainfo") is None:
        return by_category

    # In a container/headless environment there is no X/Wayland display.
    # vainfo falls through to DRM mode automatically, but the iHD driver
    # needs a concrete render node.  Prefer LIBVA_DRM_DEVICE already set
    # in the environment; otherwise probe renderD128 then renderD129.
    env = dict(os.environ)
    if not env.get("LIBVA_DRM_DEVICE") and not env.get("DISPLAY") and not env.get("WAYLAND_DISPLAY"):
        for node in ("/dev/dri/renderD128", "/dev/dri/renderD129"):
            if Path(node).exists():
                env["LIBVA_DRM_DEVICE"] = node
                break

    try:
        result = subprocess.run(
            ["vainfo"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return by_category

    text = f"{result.stdout}\n{result.stderr}".upper()
    if "VA_PROFILE" not in text:
        return by_category

    caps: set[str] = set()
    if "H264" in text or "AVC" in text:
        caps.add("h264_decode")
        if "ENC" in text:
            caps.add("h264_encode")
    if "HEVC" in text or "H265" in text:
        caps.add("h265_decode")
        if "ENC" in text:
            caps.add("h265_encode")
    if "VP9" in text:
        caps.add("vp9_support")
    if "AV1" in text:
        caps.add("av1_support")
    if "JPEG" in text:
        caps.add("jpeg_accelerated")

    # VAAPI data represents accelerator/video blocks and is GPU-facing.
    resolved = sorted(caps)
    by_category["igpu"] = resolved
    by_category["dgpu"] = resolved
    return by_category


def _detect_runtime_precision_support(
    openvino_devices: set[str],
    available_runtimes: dict[str, bool] | None = None,
) -> dict[str, list[str]]:
    """Best-effort precision capability probe per device category.

    Priority:
    1) OpenVINO optimization capabilities per logical device class
    2) CPU ISA flags from /proc/cpuinfo for CPU-only fallback
    """
    by_category: dict[str, set[str]] = {
        "cpu": set(),
        "igpu": set(),
        "dgpu": set(),
        "npu": set(),
    }

    cpuinfo_text = (_read_text("/proc/cpuinfo") or "").lower()
    cpu_caps = by_category["cpu"]
    cpu_caps.add("fp32_compute")
    if any(flag in cpuinfo_text for flag in (" f16c", " avx512_fp16", " avx512fp16")):
        cpu_caps.add("fp16_compute")
    if any(flag in cpuinfo_text for flag in (" avx2", " avx512_vnni", " amx_int8")):
        cpu_caps.add("int8_compute")
    if any(flag in cpuinfo_text for flag in (" avx512_bf16", " amx_bf16", " bf16")):
        cpu_caps.add("bfloat16_compute")

    if "CPU" not in openvino_devices and cpu_caps == {"fp32_compute"}:
        # Keep pragmatic baseline when ISA flag extraction is inconclusive.
        cpu_caps.update({"fp16_compute", "int8_compute", "bfloat16_compute"})

    if not (available_runtimes or {}).get("openvino") or not openvino_devices:
        return {k: sorted(v) for k, v in by_category.items()}

    try:
        ov_mod = importlib.import_module("openvino")
        core_cls = getattr(ov_mod, "Core", None)
        if core_cls is None:
            runtime_mod = importlib.import_module("openvino.runtime")
            core_cls = getattr(runtime_mod, "Core", None)
        if core_cls is None:
            return {k: sorted(v) for k, v in by_category.items()}
        core = core_cls()
    except (ImportError, ModuleNotFoundError, ValueError, AttributeError):
        return {k: sorted(v) for k, v in by_category.items()}

    def _map_ov_caps(tokens: list[str]) -> set[str]:
        mapped: set[str] = set()
        upper_tokens = {str(token).upper() for token in tokens}
        if "FP32" in upper_tokens:
            mapped.add("fp32_compute")
        if "FP16" in upper_tokens:
            mapped.add("fp16_compute")
        if "INT8" in upper_tokens:
            mapped.add("int8_compute")
        if "BF16" in upper_tokens:
            mapped.add("bfloat16_compute")
        if "INT4" in upper_tokens:
            mapped.add("int4_compute")
        return mapped

    for logical in ("CPU", "GPU", "NPU"):
        if logical not in openvino_devices:
            continue
        try:
            raw = core.get_property(logical, "OPTIMIZATION_CAPABILITIES")
            caps = _map_ov_caps(list(raw) if isinstance(raw, (list, tuple, set)) else [])
        except (AttributeError, RuntimeError, TypeError, ValueError):
            caps = set()

        if logical == "CPU":
            by_category["cpu"].update(caps)
        elif logical == "GPU":
            by_category["igpu"].update(caps)
            by_category["dgpu"].update(caps)
        elif logical == "NPU":
            by_category["npu"].update(caps)

    return {k: sorted(v) for k, v in by_category.items()}


def _get_media_codecs(
    category: str,
    pci_id: str | None,
    runtime_media_codecs: dict[str, list[str]] | None = None,
) -> list[str]:
    """Detect supported media codecs for a device.

    Args:
        category: Device category ("cpu", "igpu", "dgpu", "npu")
        pci_id: PCI ID like "8086:a780" or None
    Returns:
        List of supported media codec strings
    """
    if runtime_media_codecs:
        runtime_caps = runtime_media_codecs.get(category, [])
        if runtime_caps:
            return list(runtime_caps)
    codecs: list[str] = []

    # CPU rarely has hardware codecs unless it's a special SKU
    if category == "cpu":
        return codecs

    # GPU codec support based on architecture
    if category in ("igpu", "dgpu"):
        if pci_id and pci_id in _INTEL_GPU_DEVICE_REGISTRY:
            arch = _INTEL_GPU_DEVICE_REGISTRY[pci_id].get("arch")

            # Xe2 (Battlemage, Lunar Lake): Full modern codec support
            if arch == "Xe2":
                codecs.extend([
                    "h264_encode", "h264_decode",
                    "h265_encode", "h265_decode",
                    "vp9_support", "av1_support",
                    "jpeg_accelerated"
                ])

            # Xe-LPG (Arrow Lake, Meteor Lake): Modern codec support
            elif arch == "Xe-LPG":
                codecs.extend([
                    "h264_encode", "h264_decode",
                    "h265_encode", "h265_decode",
                    "vp9_support", "av1_support",
                    "jpeg_accelerated"
                ])

            # Xe-HPG (Arc A/B, Alchemist): Modern codec support
            elif arch == "Xe-HPG":
                codecs.extend([
                    "h264_encode", "h264_decode",
                    "h265_encode", "h265_decode",
                    "vp9_support",
                    "jpeg_accelerated"
                ])

            # Older Xe (Raptor Lake, Alder Lake, Tiger Lake): Limited codec support
            elif arch == "Xe":
                codecs.extend([
                    "h264_encode", "h264_decode",
                    "h265_decode",  # Decode only
                    "jpeg_accelerated"
                ])

            # Gen12, Gen11, Gen9.5: Very limited legacy support
            elif arch in ("Gen12", "Gen11", "Gen9.5"):
                codecs.extend([
                    "h264_encode", "h264_decode",
                    "jpeg_accelerated"
                ])

    # NPU typically doesn't handle media codecs (inference-focused)
    # but may have some decode assist in integrated platforms
    elif category == "npu":
        pass

    return codecs

def _get_precision_support(
    category: str,
    pci_id: str | None,
    runtime_precisions: dict[str, list[str]] | None = None,
) -> list[str]:
    """Detect supported compute precisions for a device.

    Args:
        category: Device category ("cpu", "igpu", "dgpu", "npu")
        pci_id: PCI ID like "8086:a780" or None

    Returns:
        List of supported precision strings
    """
    if runtime_precisions:
        runtime_caps = runtime_precisions.get(category, [])
        if runtime_caps:
            return list(runtime_caps)

    precisions: list[str] = []

    if category == "cpu":
        # All CPUs support fp32
        precisions.append("fp32_compute")
        # Modern x86-64 CPUs support fp16 and int8 (via AVX-512 or other SIMD)
        # For simplicity, always report these as available on modern systems
        precisions.extend(["fp16_compute", "int8_compute"])
        # bfloat16 support is CPU-model dependent but increasingly common
        precisions.append("bfloat16_compute")

    elif category == "igpu":
        # Integrated GPU precision support
        if pci_id and pci_id in _INTEL_GPU_DEVICE_REGISTRY:
            arch = _INTEL_GPU_DEVICE_REGISTRY[pci_id].get("arch")

            # All modern Xe architectures support fp32, fp16, int8
            if arch in ("Xe2", "Xe-LPG", "Xe-HPG"):
                precisions.extend([
                    "fp32_compute", "fp16_compute", "int8_compute"
                ])

            # Older Xe: fp32 and fp16 support, limited int8
            elif arch == "Xe":
                precisions.extend(["fp32_compute", "fp16_compute"])

            # Gen12 and older: fp32 only
            elif arch in ("Gen12", "Gen11", "Gen9.5"):
                precisions.append("fp32_compute")

    elif category == "dgpu":
        # Discrete Arc GPUs support full modern precision
        precisions.extend([
            "fp32_compute", "fp16_compute", "int8_compute", "bfloat16_compute"
        ])

        # Xe2/Xe-LPG also support int4 for extreme quantization
        if pci_id and pci_id in _INTEL_GPU_DEVICE_REGISTRY:
            arch = _INTEL_GPU_DEVICE_REGISTRY[pci_id].get("arch")
            if arch in ("Xe2", "Xe-LPG"):
                precisions.append("int4_compute")

    elif category == "npu":
        # NPU typically supports fp32 and int8 at minimum
        precisions.extend(["fp32_compute", "int8_compute"])

    return precisions

def _get_realtime_capabilities(category: str) -> list[str]:
    """Detect real-time inference capabilities for a device.
    Args:
        category: Device category ("cpu", "igpu", "dgpu", "npu")

    Returns:
        List of real-time capability strings
    """
    capabilities: list[str] = []

    # All devices support batch inference (throughput-oriented)
    capabilities.append("batch_inference_capable")
    # All devices can support streaming (frame-by-frame)
    capabilities.append("streaming_inference_capable")

    # Only GPU/NPU can provide real-time inference guarantees
    # (CPU-only systems are constrained by sequential processing)
    if category in ("igpu", "dgpu", "npu"):
        capabilities.append("real_time_inference")

    return capabilities

def _get_device_sw_capabilities(
    category: str,
    pci_id: str | None,
    available_runtimes: dict[str, bool],
    openvino_devices: set[str] | None = None,
    runtime_media_codecs: dict[str, list[str]] | None = None,
    runtime_precisions: dict[str, list[str]] | None = None,
) -> list[str]:
    """Classify software functional capabilities for a device.

    Args:
        category: Device category ("cpu", "igpu", "dgpu", "npu")
        pci_id: PCI ID like "8086:a780" or None
        available_runtimes: Dict from _detect_inference_runtimes()
        openvino_devices: Set from _detect_openvino_available_devices()
    Returns:
        List of capability strings (e.g., ["openvino_gpu_inference", "media"])
    """
    capabilities: list[str] = []
    ov_devices = openvino_devices or set()
    has_openvino_cpu = "CPU" in ov_devices
    has_openvino_gpu = "GPU" in ov_devices
    has_openvino_npu = "NPU" in ov_devices

    if category == "cpu":
        # CPU inference support
        # Always expose baseline CPU inference capability so schedulers have a
        # deterministic fallback even when framework-specific checks are false.
        capabilities.append("cpu_inference")
        if has_openvino_cpu or (available_runtimes.get("openvino") and not ov_devices):
            capabilities.append("openvino_cpu_inference")
        if available_runtimes.get("tensorflow"):
            capabilities.append("tensorflow_cpu_inference")
        if available_runtimes.get("pytorch"):
            capabilities.append("pytorch_cpu_inference")
        if available_runtimes.get("onnx_runtime"):
            capabilities.append("onnx_cpu_inference")
        if available_runtimes.get("llama_cpp"):
            capabilities.append("llama_cpp_inference")
        capabilities.append("general_compute")
        # Add precision and real-time capabilities
        capabilities.extend(_get_precision_support(category, pci_id, runtime_precisions))
        capabilities.extend(_get_realtime_capabilities(category))

    elif category == "igpu":
        # Integrated GPU: media/rendering always, inference depends on architecture
        capabilities.append("media")
        capabilities.append("rendering")

        # openvino_gpu_inference reflects hardware capability (arch support), not
        # whether OpenVINO is installed.  OpenVINO Core.available_devices is used
        # as the primary confirmation when available; otherwise architecture from
        # the device registry is the fallback signal for schedulers.
        if has_openvino_gpu:
            capabilities.append("openvino_gpu_inference")
        elif pci_id and pci_id in _INTEL_GPU_DEVICE_REGISTRY:
            arch = _INTEL_GPU_DEVICE_REGISTRY[pci_id].get("arch")
            if arch in ("Xe2", "Xe-LPG", "Xe-HPG", "Xe"):
                capabilities.append("openvino_gpu_inference")

        # Other inference runtimes (CPU fallback on integrated GPU)
        if available_runtimes.get("tensorflow"):
            capabilities.append("tensorflow_gpu_compute")  # May use GPU or fallback to CPU
        if available_runtimes.get("pytorch"):
            capabilities.append("pytorch_gpu_compute")

        # Add media codecs, precision support, and real-time capabilities
        capabilities.extend(_get_media_codecs(category, pci_id, runtime_media_codecs))
        capabilities.extend(_get_precision_support(category, pci_id, runtime_precisions))
        capabilities.extend(_get_realtime_capabilities(category))

    elif category == "dgpu":
        # Discrete GPU: full capabilities (media, rendering, inference)
        capabilities.append("media")
        capabilities.append("rendering")
        capabilities.append("gpu_compute")

        # dGPU Arc/Battlemage support full OpenVINO GPU inference
        # All Arc/Battlemage dGPUs support OpenVINO GPU inference by architecture.
        if has_openvino_gpu:
            capabilities.append("openvino_gpu_inference")
        elif pci_id and pci_id in _INTEL_GPU_DEVICE_REGISTRY:
            arch = _INTEL_GPU_DEVICE_REGISTRY[pci_id].get("arch")
            if arch in ("Xe2", "Xe-LPG", "Xe-HPG", "Xe"):
                capabilities.append("openvino_gpu_inference")
        elif not pci_id:
            capabilities.append("openvino_gpu_inference")
        if available_runtimes.get("tensorflow"):
            capabilities.append("tensorflow_gpu_inference")
        if available_runtimes.get("pytorch"):
            capabilities.append("pytorch_gpu_inference")
        if available_runtimes.get("onnx_runtime"):
            capabilities.append("onnx_gpu_inference")

        # Add media codecs, precision support, and real-time capabilities
        capabilities.extend(_get_media_codecs(category, pci_id, runtime_media_codecs))
        capabilities.extend(_get_precision_support(category, pci_id, runtime_precisions))
        capabilities.extend(_get_realtime_capabilities(category))

    elif category == "npu":
        # Intel NPU: inference acceleration primarily
        capabilities.append("inference_acceleration")
        capabilities.append("telemetry_sysfs")

        # NPU vendor-specific inference (Intel VPU driver)
        if has_openvino_npu or (available_runtimes.get("openvino") and not ov_devices):
            capabilities.append("openvino_npu_inference")

        # Add precision support and real-time capabilities
        capabilities.extend(_get_precision_support(category, pci_id, runtime_precisions))
        capabilities.extend(_get_realtime_capabilities(category))

    return capabilities

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


def _gpu_devices(
    available_runtimes: dict[str, bool] | None = None,
    openvino_devices: set[str] | None = None,
    runtime_media_codecs: dict[str, list[str]] | None = None,
    runtime_precisions: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """Discover GPUs via /sys/class/drm/card*.

    Classification heuristic:
    - boot_vga=1 is treated as iGPU (primary display adapter)
    - other cards are treated as dGPU

    Note: Only enumerates actual GPU devices (card0, card1, etc.),
    not display connectors (card0-DP-1, card0-HDMI-A-1, etc.).

    Args:
        available_runtimes: Dict from _detect_inference_runtimes(), or None to detect on-demand
        openvino_devices: Set from _detect_openvino_available_devices(), or None to detect on-demand
    """
    if available_runtimes is None:
        available_runtimes = _detect_inference_runtimes()
    if openvino_devices is None:
        openvino_devices = _detect_openvino_available_devices()

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
        pci_id: str | None = None
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

        # Classify software capabilities based on device category and available runtimes
        sw_capabilities = _get_device_sw_capabilities(
            category,
            pci_id,
            available_runtimes,
            openvino_devices,
            runtime_media_codecs,
            runtime_precisions,
        )

        devices.append(
            {
                "id": card.name,
                "category": category,
                "present": True,
                "model": model,
                "commercial_reference": _device_commercial_reference({"category": category, "model": model}),
                "vendor": vendor,
                "vendor_name": _vendor_name(vendor),
                "pci_device": pci_device,
                "driver": driver,
                "capabilities": [
                    "render",
                    "compute",
                    "media",
                ],
                "sw_functional_capabilities": sw_capabilities,
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


def _npu_device(
    available_runtimes: dict[str, bool] | None = None,
    openvino_devices: set[str] | None = None,
    runtime_media_codecs: dict[str, list[str]] | None = None,
    runtime_precisions: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Discover Intel NPU capabilities via intel_vpu sysfs driver path.

    Args:
        available_runtimes: Dict from _detect_inference_runtimes(), or None to detect on-demand
        openvino_devices: Set from _detect_openvino_available_devices(), or None to detect on-demand
    """
    if available_runtimes is None:
        available_runtimes = _detect_inference_runtimes()
    if openvino_devices is None:
        openvino_devices = _detect_openvino_available_devices()

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
            "sw_functional_capabilities": [],
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
            "sw_functional_capabilities": [],
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

    # Classify software capabilities for NPU
    sw_capabilities = _get_device_sw_capabilities(
        "npu",
        None,
        available_runtimes,
        openvino_devices,
        runtime_media_codecs,
        runtime_precisions,
    )

    return {
        "id": bdf_path.name,
        "category": "npu",
        "present": True,
        "model": None,
        "commercial_reference": _device_commercial_reference({"category": "npu", "model": None}),
        "vendor": vendor,
        "vendor_name": _vendor_name(vendor),
        "pci_device": _read_text(str(bdf_path / "device")),
        "driver": "intel_vpu",
        "capabilities": [
            "inference_acceleration",
            "telemetry_sysfs",
        ],
        "sw_functional_capabilities": sw_capabilities,
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

    # Detect inference runtimes once and pass to all device discovery functions
    available_runtimes = _detect_inference_runtimes()
    openvino_devices = _detect_openvino_available_devices()
    runtime_media_codecs = _detect_runtime_media_codecs()
    runtime_precisions = _detect_runtime_precision_support(openvino_devices, available_runtimes)

    # Classify CPU software capabilities
    cpu_sw_capabilities = _get_device_sw_capabilities(
        "cpu",
        None,
        available_runtimes,
        openvino_devices,
        runtime_media_codecs,
        runtime_precisions,
    )

    devices: list[dict[str, Any]] = [
        {
            "id": "cpu",
            "category": "cpu",
            "present": True,
            "model": cpu_specs.get("model"),
            "commercial_reference": _device_commercial_reference({"category": "cpu", "model": cpu_specs.get("model")}),
            "vendor": cpu_specs.get("vendor"),
            "vendor_name": _vendor_name(cpu_specs.get("vendor")),
            "pci_device": None,
            "driver": None,
            "capabilities": [
                "general_purpose_compute",
                "simd_extensions_unknown",
            ],
            "sw_functional_capabilities": cpu_sw_capabilities,
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

    devices.extend(_gpu_devices(available_runtimes, openvino_devices, runtime_media_codecs, runtime_precisions))
    devices.append(_npu_device(available_runtimes, openvino_devices, runtime_media_codecs, runtime_precisions))

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
        "inference_runtimes": available_runtimes,
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


def _device_name_pair(device: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return normalized model and commercial reference values for output."""
    model = device.get("model")
    commercial_reference = device.get("commercial_reference")

    if model and commercial_reference:
        return str(model), str(commercial_reference)

    resolved = commercial_reference or model or _device_commercial_reference(device)
    if resolved is None:
        return None, None

    resolved_text = str(resolved)
    return resolved_text, resolved_text


def _minimal_from_expanded(expanded: dict[str, Any]) -> dict[str, Any]:
    """Create a categorized high-level minimal capability response."""
    minimal_devices: list[dict[str, Any]] = []
    for device in expanded.get("devices", []):
        model, commercial_reference = _device_name_pair(device)
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
                "model": model,
                "commercial_reference": commercial_reference,
                "vendor": device.get("vendor"),
                "vendor_name": device.get("vendor_name"),
                "sw_functional_capabilities": device.get("sw_functional_capabilities", []),
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
        "inference_runtimes": expanded.get("inference_runtimes", {}),
    }


def get_capabilities_snapshot(profile: Literal["minimal", "expanded"] = "minimal") -> dict[str, Any]:
    """Build a platform/device capability snapshot in requested profile format."""
    expanded = _expanded_capabilities_snapshot()
    if profile == "expanded":
        return expanded
    return _minimal_from_expanded(expanded)
