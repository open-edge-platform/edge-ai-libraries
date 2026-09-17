# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Structural invariants for the Intel GPU device registry.

The registry is hand-maintained from upstream tables, so these tests guard the
shape and the arch vocabulary rather than individual device IDs.
"""

import re

import pytest

from app.capabilities import (
    _GPU_MODEL_FALLBACK_BY_PCI_ID,
    _INTEL_GPU_DEVICE_REGISTRY,
    _get_device_sw_capabilities,
    _get_media_codecs,
    _get_precision_support,
)

_PCI_ID_RE = re.compile(r"^8086:[0-9a-f]{4}$")

# Every arch string the capability-inference branches know how to classify.
_KNOWN_ARCHES = {
    "Xe3p",
    "Xe3",
    "Xe2",
    "Xe-LPG",
    "Xe-HPG",
    "Xe",
    "Gen12",
    "Gen11",
    "Gen9.5",
}


@pytest.mark.parametrize("pci_id", sorted(_INTEL_GPU_DEVICE_REGISTRY))
def test_registry_entry_is_well_formed(pci_id: str) -> None:
    entry = _INTEL_GPU_DEVICE_REGISTRY[pci_id]
    assert _PCI_ID_RE.match(pci_id), "keys must be lowercase 8086:xxxx"
    assert set(entry) == {"name", "arch", "category", "min_kernel"}
    assert entry["name"]
    assert entry["arch"] in _KNOWN_ARCHES
    assert entry["category"] in ("igpu", "dgpu")
    assert re.match(r"^\d+\.\d+$", entry["min_kernel"])


def test_model_fallback_covers_whole_registry() -> None:
    assert _GPU_MODEL_FALLBACK_BY_PCI_ID.keys() == _INTEL_GPU_DEVICE_REGISTRY.keys()


@pytest.mark.parametrize("arch", sorted(_KNOWN_ARCHES))
def test_every_arch_yields_capabilities(arch: str) -> None:
    """No arch may fall through the inference branches and report nothing."""
    pci_id = next(
        pid for pid, e in _INTEL_GPU_DEVICE_REGISTRY.items() if e["arch"] == arch
    )
    category = _INTEL_GPU_DEVICE_REGISTRY[pci_id]["category"]

    assert _get_media_codecs(category, pci_id, None)
    assert _get_precision_support(category, pci_id, None)


@pytest.mark.parametrize("arch", sorted(_KNOWN_ARCHES - {"Gen12", "Gen11", "Gen9.5"}))
def test_every_xe_arch_reports_openvino_gpu_inference(arch: str) -> None:
    pci_id = next(
        pid for pid, e in _INTEL_GPU_DEVICE_REGISTRY.items() if e["arch"] == arch
    )
    category = _INTEL_GPU_DEVICE_REGISTRY[pci_id]["category"]

    assert "openvino_gpu_inference" in _get_device_sw_capabilities(
        category, pci_id, available_runtimes={}, openvino_devices=set()
    )


@pytest.mark.parametrize(
    "pci_id,arch",
    [
        ("8086:b080", "Xe3"),  # Panther Lake -- xe_pci.c IP 3000, "Xe3_LPG"
        ("8086:fd80", "Xe3"),  # Wildcat Lake -- PtlHwConfig, SUPPORT_XE3_CORE
        ("8086:d740", "Xe3"),  # Nova Lake-S -- NvlsHwConfig, SUPPORT_XE3_CORE
        ("8086:d750", "Xe3p"),  # Nova Lake-P -- NvlHwConfig, SUPPORT_XE3P_CORE
        ("8086:674c", "Xe3p"),  # Crescent Island -- CriHwConfig, SUPPORT_XE3P_CORE
        ("8086:e20b", "Xe2"),  # Battlemage -- SUPPORT_XE2_HPG_CORE
    ],
)
def test_arch_matches_compute_runtime_grouping(pci_id: str, arch: str) -> None:
    assert _INTEL_GPU_DEVICE_REGISTRY[pci_id]["arch"] == arch


@pytest.mark.parametrize("pci_id", ["8086:6422", "8086:b0ff", "8086:d744"])
def test_ids_absent_from_kernel_tables_are_not_registered(pci_id: str) -> None:
    """These exist in pci.ids and/or compute-runtime but bind to no in-tree driver."""
    assert pci_id not in _INTEL_GPU_DEVICE_REGISTRY
