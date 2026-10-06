#!/usr/bin/env bash

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# install-systemd.sh — Install Intel CDI systemd service, timer, and udev rules
#
# This installs:
#   1. Udev rules    → triggers CDI regeneration on device hot-plug
#   2. Systemd service → runs the CDI spec generators
#   3. Systemd timer  → periodic fallback (every 5 min) for missed events
#
# Usage:
#   sudo ./install-systemd.sh           # install and enable everything
#   sudo ./install-systemd.sh --no-timer  # skip the periodic timer
#   sudo ./install-systemd.sh --uninstall # remove everything

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

SCRIPTS_DIR="/opt/edge/scripts/cdi"
SYSTEMD_DIR="/etc/systemd/system"
UDEV_DIR="/etc/udev/rules.d"
CDI_DIR="/etc/cdi"

NO_TIMER=false
UNINSTALL=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-timer)  NO_TIMER=true; shift ;;
    --uninstall) UNINSTALL=true; shift ;;
    -h|--help)
      echo "Usage: $(basename "$0") [--no-timer] [--uninstall]"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: Must be run as root (sudo)." >&2
  exit 1
fi

# --- Uninstall --------------------------------------------------------------

if $UNINSTALL; then
  echo "Uninstalling Intel CDI systemd components..."

  systemctl stop intel-cdi-regenerate.timer 2>/dev/null || true
  systemctl stop intel-cdi-regenerate.service 2>/dev/null || true
  systemctl disable intel-cdi-regenerate.timer 2>/dev/null || true
  systemctl disable intel-cdi-regenerate.service 2>/dev/null || true

  rm -f "${SYSTEMD_DIR}/intel-cdi-regenerate.service"
  rm -f "${SYSTEMD_DIR}/intel-cdi-regenerate.timer"
  rm -f "${UDEV_DIR}/99-intel-cdi.rules"

  systemctl daemon-reload
  udevadm control --reload-rules 2>/dev/null || true

  echo "Uninstalled. CDI spec files in $CDI_DIR are preserved."
  echo "To remove specs: rm -f ${CDI_DIR}/intel.com-*.yaml"
  exit 0
fi

# --- Install ----------------------------------------------------------------

echo "============================================"
echo " Installing Intel CDI Systemd Service"
echo "============================================"
echo ""

if [[ ! -x "$SCRIPTS_DIR/intel-cdi-specs-generator-gpu" ]]; then
  echo "ERROR: GPU generator binary not found at: $SCRIPTS_DIR/intel-cdi-specs-generator-gpu" >&2
  echo "  Build it first: ${SCRIPTS_DIR}/build-gpu-generator.sh" >&2
  exit 1
fi

if [[ ! -x "$SCRIPTS_DIR/intel-cdi-npu-generator.sh" ]]; then
  echo "ERROR: intel-cdi-npu-generator.sh not found at: $SCRIPTS_DIR/intel-cdi-npu-generator.sh" >&2
  exit 1
fi

# Create CDI output directory
mkdir -p "$CDI_DIR"

# Install systemd service
echo "--- Installing systemd service ---"
cp -v "$SCRIPT_DIR/intel-cdi-regenerate.service" "$SYSTEMD_DIR/"
chmod 644 "$SYSTEMD_DIR/intel-cdi-regenerate.service"

# Install systemd timer
if ! $NO_TIMER; then
  echo "--- Installing systemd timer ---"
  cp -v "$SCRIPT_DIR/intel-cdi-regenerate.timer" "$SYSTEMD_DIR/"
  chmod 644 "$SYSTEMD_DIR/intel-cdi-regenerate.timer"
fi

# Install udev rules
echo "--- Installing udev rules ---"
cp -v "$SCRIPT_DIR/99-intel-cdi.rules" "$UDEV_DIR/"
chmod 644 "$UDEV_DIR/99-intel-cdi.rules"
echo ""

# Reload daemons
echo "--- Reloading systemd and udev ---"
systemctl daemon-reload
udevadm control --reload-rules
udevadm trigger --subsystem-match=drm --action=change 2>/dev/null || true
udevadm trigger --subsystem-match=accel --action=change 2>/dev/null || true

# Enable and start
echo "--- Enabling services ---"
systemctl enable intel-cdi-regenerate.service
if ! $NO_TIMER; then
  systemctl enable --now intel-cdi-regenerate.timer
  echo "  Timer enabled (runs every 5 min + on boot)"
fi

# Run once now to generate initial specs
echo ""
echo "--- Generating initial CDI specs ---"
systemctl start intel-cdi-regenerate.service || true
echo ""

# --- Summary ----------------------------------------------------------------

echo "============================================"
echo " Installation Complete"
echo "============================================"
echo ""
echo "Generators at: $SCRIPTS_DIR/"
echo "  $SYSTEMD_DIR/intel-cdi-regenerate.service"
if ! $NO_TIMER; then
  echo "  $SYSTEMD_DIR/intel-cdi-regenerate.timer"
fi
echo "  $UDEV_DIR/99-intel-cdi.rules"
echo ""
echo "CDI specs output to: $CDI_DIR/"
echo ""
echo "Triggers:"
echo "  - Udev: auto-regenerates when Intel DRM/accel devices appear or disappear"
if ! $NO_TIMER; then
  echo "  - Timer: periodic check every 5 minutes (catches missed events)"
fi
echo "  - Manual: systemctl start intel-cdi-regenerate.service"
echo ""
echo "Uninstall:"
echo "  sudo $(readlink -f "$0") --uninstall"
