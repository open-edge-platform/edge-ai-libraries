#!/usr/bin/env bash

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# intel-cdi-npu-generator.sh — Generate CDI specs for Intel NPU devices
#
# Scans sysfs for Intel NPU (VPU) accelerators and generates a CDI 0.5.0
# spec file compatible with Docker, Podman, and containerd.
#
# Usage:
#   sudo ./intel-cdi-npu-generator.sh                    # generate NPU spec
#   sudo ./intel-cdi-npu-generator.sh --cdi-dir /etc/cdi
#   ./intel-cdi-npu-generator.sh --dry-run               # preview without writing

set -euo pipefail

CDI_DIR="/etc/cdi"
DRY_RUN=false
SYSFS_DRIVER_PATH="/sys/bus/pci/drivers/intel_vpu"

declare -A MODEL_NAMES=(
  ["0xb03e"]="NPU 3000 (Panther Lake)"
  ["0x643e"]="NPU 4000 (Lunar Lake)"
  ["0x7d1d"]="NPU 2000 (Meteor Lake)"
)

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Generate CDI spec for Intel NPU (VPU) accelerator devices.

Options:
  --cdi-dir DIR    CDI spec output directory (default: /etc/cdi)
  --dry-run, -n    Preview generated spec without writing to disk
  -h, --help       Show this help message

Output:
  \${cdi-dir}/intel.com-npu.yaml (CDI 0.5.0 format)

Supported NPU Devices:
  0xb03e — NPU 3000 (Panther Lake)
  0x643e — NPU 4000 (Lunar Lake)
  0x7d1d — NPU 2000 (Meteor Lake)
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cdi-dir)  CDI_DIR="$2"; shift 2 ;;
    --dry-run|-n) DRY_RUN=true; shift ;;
    -h|--help)  usage ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

echo "Scanning for NPU accelerators"

if [[ ! -d "$SYSFS_DRIVER_PATH" ]]; then
  echo "No Intel NPU devices found (${SYSFS_DRIVER_PATH} does not exist)"
  exit 0
fi

declare -a DEVICES=()
npu_index=0

for pci_dir in "$SYSFS_DRIVER_PATH"/????:??:??.?; do
  [[ -d "$pci_dir" ]] || continue
  pci_addr=$(basename "$pci_dir")

  device_id_file="${pci_dir}/device"
  [[ -f "$device_id_file" ]] || continue
  device_id=$(tr -d '[:space:]' < "$device_id_file")

  model_name="${MODEL_NAMES[$device_id]:-Unknown NPU ($device_id)}"

  accel_dir="${pci_dir}/accel"
  if [[ ! -d "$accel_dir" ]]; then
    echo "  WARN: No accel device for NPU at ${pci_addr}" >&2
    continue
  fi

  accel_dev=""
  for accel in "$accel_dir"/accel*; do
    [[ -d "$accel" ]] || continue
    accel_dev=$(basename "$accel")
    break
  done

  if [[ -z "$accel_dev" ]]; then
    echo "  WARN: No accel device found under ${accel_dir}" >&2
    continue
  fi

  device_name="npu${npu_index}"

  echo "  NPU: intel.com/npu=${device_name} (${model_name}) -> /dev/accel/${accel_dev}"

  DEVICES+=("${device_name}:${accel_dev}")
  (( npu_index++ )) || true
done

if (( ${#DEVICES[@]} == 0 )); then
  echo "No supported NPU devices detected"
  if [[ -f "${CDI_DIR}/intel.com-npu.yaml" ]] && ! $DRY_RUN; then
    rm -f "${CDI_DIR}/intel.com-npu.yaml"
    echo "Removed stale ${CDI_DIR}/intel.com-npu.yaml"
  fi
  exit 0
fi

spec="---
cdiVersion: \"0.5.0\"
kind: intel.com/npu
devices:"

for entry in "${DEVICES[@]}"; do
  device_name="${entry%%:*}"
  accel_dev="${entry##*:}"
  spec+="
  - name: ${device_name}
    containerEdits:
      deviceNodes:
        - path: /dev/accel/${accel_dev}
          hostPath: /dev/accel/${accel_dev}
          type: c"
done

if $DRY_RUN; then
  echo ""
  echo "--- DRY RUN: would write to ${CDI_DIR}/intel.com-npu.yaml ---"
  echo "$spec"
  exit 0
fi

mkdir -p "$CDI_DIR"
echo "$spec" > "${CDI_DIR}/intel.com-npu.yaml"
chmod 644 "${CDI_DIR}/intel.com-npu.yaml"
echo ""
echo "Wrote ${CDI_DIR}/intel.com-npu.yaml (${#DEVICES[@]} device(s))"
