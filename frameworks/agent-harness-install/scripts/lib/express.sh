# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# Intel hardware "express install" profiles — classifies the host by PCI
# device family, since there is no fixed appliance SKU to detect against
# in the Intel discrete-accelerator lineup. Scoped to a single Core Ultra
# node with an optional discrete GPU per the OEP Agentic Blueprint (data
# center-class accelerators like Xeon/Gaudi/Data Center GPU Max are out of
# scope — those target the separate, Xeon-only Enterprise Agent Toolkit).
#
# Known Intel discrete GPU PCI device-ID prefixes (subset; extend as needed):
#   0x56xx = Arc (Alchemist/Battlemage, consumer & workstation)
#   0xb0xx = Arc (Panther Lake integrated, e.g. Arc B390 -- confirmed 0xb080)
detect_intel_harness_profile() {
  local dev vendor device root="/sys/bus/pci/devices"

  if [[ -d "$root" ]]; then
    for dev in "$root"/*; do
      [[ -d "$dev" ]] || continue
      vendor="$(cat "$dev/vendor" 2>/dev/null || true)"
      device="$(cat "$dev/device" 2>/dev/null || true)"
      vendor="${vendor#0x}"
      device="${device#0x}"
      [[ "$vendor" == "8086" ]] || continue
      case "$device" in
        56* | b0*) printf 'arc'; return ;;
      esac
    done
  fi

  if detect_intel_gpu; then
    printf 'intel-gpu-other'
  else
    printf 'cpu-only'
  fi
}

describe_harness_profile() {
  case "$1" in
    arc) printf 'Intel Arc GPU' ;;
    intel-gpu-other) printf 'Other Intel GPU' ;;
    cpu-only) printf 'CPU-only (no Intel GPU detected)' ;;
    *) printf 'Unknown' ;;
  esac
}

# apply_gpu_profile_defaults — the actual effect of HARNESS_GPU_PROFILE
# (set either by maybe_offer_express_install's prompt, or directly by the
# operator, per its documented env var). Without this, accepting the express
# prompt changed no install behavior at all. "Express install with profile
# defaults" means: don't prompt again, and skip re-running GPU diagnostics
# that profile detection already just performed for an already-confirmed
# Intel GPU profile (arc/intel-gpu-other) -- cpu-only still runs them, since
# nothing was confirmed in that case.
apply_gpu_profile_defaults() {
  [[ -n "${HARNESS_GPU_PROFILE:-}" ]] || return 0
  NON_INTERACTIVE=1
  export NON_INTERACTIVE
  case "$HARNESS_GPU_PROFILE" in
    arc | intel-gpu-other) SKIP_GPU_CHECK=1 ;;
  esac
  info "Using '${HARNESS_GPU_PROFILE}' profile defaults: non-interactive$([[ -n "${SKIP_GPU_CHECK:-}" ]] && printf ', GPU check skipped')."
}

# Offers a one-shot non-interactive express install using profile defaults,
# mirroring maybe_offer_express_install's Y/n prompt + env-var activation.
maybe_offer_express_install() {
  [[ "${NON_INTERACTIVE:-}" != "1" ]] || return 0
  [[ -z "${HARNESS_GPU_PROFILE:-}" ]] || return 0

  local profile
  profile="$(detect_intel_harness_profile)"
  [[ "$profile" != "cpu-only" ]] || return 0

  info "Detected: $(describe_harness_profile "$profile")"
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
      export HARNESS_GPU_PROFILE="$profile"
      info "Using express install for ${profile}."
      ;;
    *) info "Skipping express install. Continuing with the interactive flow." ;;
  esac
}
