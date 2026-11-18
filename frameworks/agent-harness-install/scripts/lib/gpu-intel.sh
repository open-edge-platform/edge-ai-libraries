# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# Intel GPU detection and compute-runtime readiness checks.
# Covers Core Ultra iGPU and Arc (CRI) cards, which expose themselves as PCI
# display/3D controllers under vendor 0x8086 and are accessed through the
# i915 or xe kernel driver + Level-Zero/OpenCL.

INTEL_PCI_VENDOR_ID="8086"

# Returns 0 if at least one Intel discrete/display GPU PCI device is present.
detect_intel_gpu() {
  local dev vendor pci_class
  local root="/sys/bus/pci/devices"
  [[ -d "$root" ]] || return 1
  for dev in "$root"/*; do
    [[ -d "$dev" ]] || continue
    vendor="$(cat "$dev/vendor" 2>/dev/null || true)"
    pci_class="$(cat "$dev/class" 2>/dev/null || true)"
    vendor="${vendor#0x}"
    # Class 0x03xxxx = display controller (VGA/3D/other).
    if [[ "$vendor" == "$INTEL_PCI_VENDOR_ID" && "$pci_class" == 0x03* ]]; then
      return 0
    fi
  done
  return 1
}

# Prints a short description of detected Intel GPU(s), or nothing if none.
describe_intel_gpu() {
  if command_exists xpu-smi; then
    xpu-smi discovery 2>/dev/null | grep -E 'Device Name|Device ID' || true
    return
  fi
  if command_exists lspci; then
    lspci -d "${INTEL_PCI_VENDOR_ID}:" 2>/dev/null | grep -Ei 'vga|3d|display' || true
  fi
}

# Returns 0 if the kernel-mode driver (i915 legacy or xe, for Battlemage+) is loaded.
intel_gpu_kernel_driver_loaded() {
  [[ -d /sys/module/xe || -d /sys/module/i915 ]] && return 0
  command_exists lsmod || return 1
  # No -q: an early grep exit would SIGPIPE lsmod and fail the pipeline under pipefail.
  lsmod | grep -E '^(i915|xe)\b' >/dev/null
}

# Returns 0 if render nodes are present and accessible (needed for container
# passthrough via --device=/dev/dri, no CDI/plugin required for Docker).
intel_gpu_render_nodes_available() {
  compgen -G "/dev/dri/renderD*" >/dev/null 2>&1
}

# Returns 0 if the user-space compute runtime (Level Zero / OpenCL ICD) is installed.
intel_compute_runtime_installed() {
  local found=1
  if command_exists clinfo && clinfo 2>/dev/null | grep -i intel >/dev/null; then
    found=0
  fi
  if [[ -e /usr/lib/x86_64-linux-gnu/libze_intel_gpu.so.1 ]] \
    || [[ -e /usr/lib/libze_intel_gpu.so.1 ]] \
    || ldconfig -p 2>/dev/null | grep libze_intel_gpu >/dev/null; then
    found=0
  fi
  return "$found"
}
