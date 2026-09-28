# shellcheck shell=bash
# Intel GPU detection and compute-runtime readiness checks.
# Covers discrete Arc / Data Center GPU Max (Ponte Vecchio) cards, which
# expose themselves as PCI display/3D controllers under vendor 0x8086 and
# are accessed through the i915 or xe kernel driver + Level-Zero/OpenCL.

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
  command_exists lsmod || return 1
  lsmod | grep -qE '^(i915|xe)\b'
}

# Returns 0 if render nodes are present and accessible (needed for container
# passthrough via --device=/dev/dri, no CDI/plugin required for Docker).
intel_gpu_render_nodes_available() {
  compgen -G "/dev/dri/renderD*" >/dev/null 2>&1
}

# Returns 0 if the user-space compute runtime (Level Zero / OpenCL ICD) is installed.
intel_compute_runtime_installed() {
  local found=1
  if command_exists clinfo && clinfo 2>/dev/null | grep -qi intel; then
    found=0
  fi
  if [[ -e /usr/lib/x86_64-linux-gnu/libze_intel_gpu.so.1 ]] \
    || [[ -e /usr/lib/libze_intel_gpu.so.1 ]] \
    || ldconfig -p 2>/dev/null | grep -q libze_intel_gpu; then
    found=0
  fi
  return "$found"
}

# Installs the Intel Compute Runtime + Level-Zero packages on Debian/Ubuntu.
# See: https://github.com/intel/compute-runtime
install_intel_compute_runtime_apt() {
  command_exists apt-get || error "Automatic Intel compute-runtime install only
supports apt-get (Debian/Ubuntu). Install intel-opencl-icd and
libze-intel-gpu1 manually, then re-run."
  info "Installing Intel GPU compute runtime (Level Zero + OpenCL) via apt…"
  sudo apt-get update -qq
  sudo apt-get install -y -qq \
    intel-opencl-icd \
    libze-intel-gpu1 \
    libze1 \
    clinfo \
    intel-gsc || error "Failed to install Intel compute-runtime packages."
  ok "Intel compute runtime installed"
}

# Ensures the current user can access /dev/dri render nodes (the 'render'
# group on most distros, 'video' as a fallback on older ones).
ensure_intel_gpu_group_access() {
  local current_user render_node group_name
  current_user="$(id -un)"
  render_node="$(compgen -G "/dev/dri/renderD*" | head -1 || true)"
  [[ -n "$render_node" ]] || return 0
  group_name="$(stat -c '%G' "$render_node" 2>/dev/null || true)"
  [[ -n "$group_name" ]] || return 0
  if id -nG "$current_user" 2>/dev/null | tr ' ' '\n' | grep -qx "$group_name"; then
    return 0
  fi
  info "Adding '$current_user' to the '$group_name' group for GPU device access."
  info "You may be asked for your password."
  sudo usermod -aG "$group_name" "$current_user"
  warn "Group membership needs a new login/shell session ('newgrp $group_name'
or log out and back in) before containers can use the GPU."
  return 1
}
