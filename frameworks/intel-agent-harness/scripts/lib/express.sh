# shellcheck shell=bash
# Intel hardware "express install" profiles — classifies the host by PCI
# device family, since there is no fixed appliance SKU to detect against
# in the Intel discrete-accelerator lineup.
#
# Known Intel discrete GPU PCI device-ID prefixes (subset; extend as needed):
#   0x56xx = Arc (Alchemist/Battlemage, consumer & workstation)
#   0x0Bxx = Data Center GPU Max (Ponte Vecchio)
# Habana Gaudi accelerators are a different PCI vendor (0x1da3, Habana Labs,
# an Intel subsidiary) and are detected separately via /dev/accel + hl-smi.
detect_intel_platform_profile() {
  local dev vendor device root="/sys/bus/pci/devices"

  if command_exists hl-smi || { [[ -d /dev/accel ]] && compgen -G "/dev/accel/*" >/dev/null 2>&1; }; then
    printf 'gaudi'
    return
  fi

  if [[ -d "$root" ]]; then
    for dev in "$root"/*; do
      [[ -d "$dev" ]] || continue
      vendor="$(cat "$dev/vendor" 2>/dev/null || true)"
      device="$(cat "$dev/device" 2>/dev/null || true)"
      vendor="${vendor#0x}"
      device="${device#0x}"
      [[ "$vendor" == "8086" ]] || continue
      case "$device" in
        0b* | 0B*) printf 'datacenter-gpu-max'; return ;;
        56*) printf 'arc'; return ;;
      esac
    done
  fi

  if detect_intel_gpu; then
    printf 'intel-gpu-other'
  else
    printf 'cpu-only'
  fi
}

describe_platform_profile() {
  case "$1" in
    gaudi) printf 'Intel Gaudi accelerator (Habana SynapseAI)' ;;
    datacenter-gpu-max) printf 'Intel Data Center GPU Max (Ponte Vecchio)' ;;
    arc) printf 'Intel Arc GPU' ;;
    intel-gpu-other) printf 'Other Intel GPU' ;;
    cpu-only) printf 'CPU-only (no Intel GPU detected)' ;;
    *) printf 'Unknown' ;;
  esac
}

# Offers a one-shot non-interactive express install using profile defaults,
# mirroring maybe_offer_express_install's Y/n prompt + env-var activation.
maybe_offer_express_install() {
  [[ "${NON_INTERACTIVE:-}" != "1" ]] || return 0
  [[ -z "${PLATFORM_GPU_PROFILE:-}" ]] || return 0

  local profile
  profile="$(detect_intel_platform_profile)"
  [[ "$profile" != "cpu-only" ]] || return 0

  info "Detected: $(describe_platform_profile "$profile")"
  if [[ ! -t 0 ]] && ! { exec 3</dev/tty; } 2>/dev/null; then
    info "Skipping express prompt (no TTY)."
    return 0
  fi

  local reply
  printf "  Run express install with the '%s' profile defaults? [Y/n]: " "$profile"
  if [[ -t 0 ]]; then
    IFS= read -r reply || reply=""
  else
    IFS= read -r reply <&3 || reply=""
    exec 3<&-
  fi
  case "$(printf '%s' "$reply" | tr '[:upper:]' '[:lower:]')" in
    "" | y | yes)
      export PLATFORM_GPU_PROFILE="$profile"
      info "Using express install for ${profile}."
      ;;
    *) info "Skipping express install. Continuing with the interactive flow." ;;
  esac
}
