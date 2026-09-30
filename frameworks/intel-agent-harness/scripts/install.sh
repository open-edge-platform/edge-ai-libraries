#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Intel-platform installer payload — the actual install flow, invoked by the
# thin bootstrap at the repo root (../install.sh). Staged install flow:
# third-party notice, express install, host prep (GPU + Docker), Node.js,
# CLI install, onboarding — with a Docker-based sandbox manager for running
# containerized workloads (no CDI needed; Intel render nodes pass through
# via --device).
set -euo pipefail

# Repo root is one level up from this payload script.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
for lib in colors verify state sudo shim gpu-intel docker-setup nodejs notice gateway sandbox express openvino agents harness-mcp; do
  # shellcheck disable=SC1090
  . "${SCRIPT_DIR}/scripts/lib/${lib}.sh"
done

TOTAL_STEPS=4
NON_INTERACTIVE="${NON_INTERACTIVE:-}"
ACCEPT_THIRD_PARTY_SOFTWARE="${ACCEPT_THIRD_PARTY_SOFTWARE:-}"
SKIP_GPU_CHECK="${SKIP_GPU_CHECK:-}"

usage() {
  cat <<EOF

  ${C_BOLD}Intel Agent Harness${C_RESET}

  Usage:
    ./install.sh [options]                      Run the full install + onboarding
    ./install.sh sandbox <verb> [name]           Manage sandboxes directly
    ./install.sh models <list|remove> [name]     List or delete exported OpenVINO models
    ./install.sh mcp register <name> <url> [agent]  Register an arbitrary MCP endpoint URL
    ./install.sh skill <install|list|remove> [path|name]  Manage Hermes skills
    ./install.sh connect <name>                  Open a shell inside a running sandbox
    ./install.sh status                          Show Harness/OVMS/sandbox health
    ./install.sh onboard                         Re-run onboarding only

  Sandbox verbs: list, create <name> <image> [env-pairs], start <name>, stop <name>,
                 destroy <name>, backup <name>, backup-all, recover <name>,
                 recover-all

  Options:
    --non-interactive                Skip prompts (uses env vars / defaults)
    --yes-i-accept-third-party-software  Accept the third-party notice without prompting
    --skip-gpu-check                  Skip Intel GPU detection/driver checks
    --agent <openclaw|deepagents-code|hermes>  Real agent to install (sets HARNESS_AGENT)
    --hf-model <hf-model-id>          Hugging Face model to export to OpenVINO IR
    --help, -h                        Show this help message and exit

  Environment:
    HARNESS_AGENT               openclaw | deepagents-code | hermes (default: openclaw)
    HERMES_INSTALL_URL            Hermes's official installer URL (default: hermes-agent.nousresearch.com)
    HERMES_INSTALL_SHA256         Pin the Hermes installer's expected SHA-256 (required unless HERMES_ALLOW_UNVERIFIED_INSTALL=1)
    HERMES_ALLOW_UNVERIFIED_INSTALL  Run the Hermes installer without a pinned checksum (not recommended)
    DOCKER_INSTALL_SHA256         Pin get.docker.com's expected SHA-256 (non-apt hosts only; required unless DOCKER_ALLOW_UNVERIFIED_INSTALL=1)
    DOCKER_ALLOW_UNVERIFIED_INSTALL  Run the Docker convenience script without a pinned checksum (not recommended)
    HARNESS_LLM_ENDPOINT         OpenAI-compatible endpoint (default: local OpenVINO Model Server)
    HARNESS_LLM_PROVIDER         ovms (default) — the only backend this installer manages itself
    HARNESS_LLM_ROUTER_ENDPOINT  Route to an existing external OpenAI-compatible router instead of OVMS
    HARNESS_HF_MODEL             Hugging Face model to export/serve via OpenVINO
    HARNESS_OVMS_REST_PORT, HARNESS_MODELS_DIR
    HARNESS_SANDBOX_NAME, HARNESS_SANDBOX_IMAGE, HARNESS_SANDBOX_PORT
    HARNESS_GPU_PROFILE, MIN_NODE_VERSION
    HARNESS_OVMS_EXTRA_ARGS       Extra OVMS server flags (e.g. --tool_parser hermes3)
    HARNESS_OVMS_EXPORT_MODEL_PY_SHA256, HARNESS_OVMS_EXPORT_MODEL_REQUIREMENTS_SHA256  Pin export_model.py/requirements.txt when overriding HARNESS_OVMS_EXPORT_MODEL_REF
    HARNESS_ALLOW_UNVERIFIED_OVMS_EXPORTER  Skip pinning for a custom HARNESS_OVMS_EXPORT_MODEL_REF (not recommended)
    HARNESS_GATEWAY_ENABLED       Route sandbox traffic through a shared gateway instead of publishing ports (default: off)
    HARNESS_GATEWAY_NETWORK, HARNESS_GATEWAY_CONTAINER, HARNESS_GATEWAY_PORT
    HERMES_CONFIG                  Path to Hermes's config.yaml (default: ~/.hermes/config.yaml)
    HARNESS_MCP_REGISTER_CMD       Script to register an MCP endpoint with a non-Hermes agent
    HARNESS_ADVERTISED_HOST       Host/IP printed in endpoint URLs (default: 127.0.0.1)
    HARNESS_BIND_HOST             Address Docker binds published ports to (default: same as HARNESS_ADVERTISED_HOST)
    HTTP_PROXY, HTTPS_PROXY, ALL_PROXY, NO_PROXY  Forwarded into OVMS/sandbox/gateway containers
    NON_INTERACTIVE=1, ACCEPT_THIRD_PARTY_SOFTWARE=1, SKIP_GPU_CHECK=1

EOF
}

# maybe_prompt_advertised_host — offers to advertise endpoint URLs under a
# non-loopback host/IP (e.g. this machine's LAN address) instead of the
# 127.0.0.1 default, for setups accessed from another machine. Skipped
# non-interactively or without a TTY; the chosen value is persisted so later
# invocations (sandbox list, status) keep showing it.
maybe_prompt_advertised_host() {
  [[ "${NON_INTERACTIVE:-}" != "1" ]] || return 0
  local reply=""
  if [[ -t 0 ]]; then
    printf "  Host/IP to advertise in printed endpoint URLs [%s]: " "$(resolve_advertised_host)"
    IFS= read -r reply || reply=""
  elif { exec 3</dev/tty; } 2>/dev/null; then
    printf "  Host/IP to advertise in printed endpoint URLs [%s]: " "$(resolve_advertised_host)"
    IFS= read -r reply <&3 || reply=""
    exec 3<&-
  else
    return 0
  fi
  [[ -n "$reply" ]] || return 0
  # This value now also doubles as the literal docker -p bind address (via
  # resolve_bind_host) unless HARNESS_BIND_HOST overrides it separately, so
  # reject anything that isn't a plausible IPv4/IPv6/hostname literal before
  # persisting it -- a typo here would otherwise surface later as a much
  # more confusing "docker run" failure instead of just wrong display text.
  if [[ ! "$reply" =~ ^[A-Za-z0-9.:-]+$ ]]; then
    warn "'${reply}' doesn't look like a valid host/IP; keeping the previous value."
    return 0
  fi
  HARNESS_ADVERTISED_HOST="$reply"
  HARNESS_ADVERTISED_HOST_WAS_SET=1
  persist_advertised_host "$reply"
}

prepare_installer_host() {
  maybe_offer_express_install
  maybe_prompt_advertised_host

  info "Checking Intel GPU…"
  if [[ -n "$SKIP_GPU_CHECK" ]]; then
    info "Skipping GPU check (--skip-gpu-check)."
  elif ! detect_intel_gpu; then
    warn "No Intel display/GPU PCI device detected. Continuing in CPU-only mode."
  else
    ok "Intel GPU detected"
    describe_intel_gpu | sed 's/^/    /'
    intel_gpu_kernel_driver_loaded || warn "Neither the i915 nor xe kernel driver appears
loaded. GPU acceleration may be unavailable."
    intel_gpu_render_nodes_available || warn "No /dev/dri render nodes found; containers
will not get GPU passthrough."
    if intel_compute_runtime_installed; then
      ok "Intel compute runtime already installed"
    elif [[ "$NON_INTERACTIVE" == "1" ]]; then
      install_intel_compute_runtime_apt
    else
      printf "  Install the Intel compute runtime (Level Zero + OpenCL) now? [Y/n]: "
      local reply=""
      IFS= read -r reply || true
      case "$(printf '%s' "$reply" | tr '[:upper:]' '[:lower:]')" in
        "" | y | yes) install_intel_compute_runtime_apt ;;
        *) warn "Skipping compute runtime install; GPU acceleration may not work." ;;
      esac
    fi
    ensure_intel_gpu_group_access || true
  fi

  ensure_docker
  ok "Docker is ready"
}

print_done() {
  printf "\n${C_GREEN}${C_BOLD}=== Installation complete ===${C_RESET}\n\n"
  local gpu_device_args
  gpu_device_args="$(intel_gpu_docker_device_args)"
  if [[ -n "$gpu_device_args" ]]; then
    printf "  ${C_DIM}Intel GPU render nodes are passed to sandboxes automatically.${C_RESET}\n"
  fi
  if sandbox_gateway_enabled; then
    printf "  ${C_DIM}Sandboxes are routed through the harness gateway on port $(resolve_gateway_port_for_display).${C_RESET}\n"
  fi
  printf "  ${C_BOLD}Sandboxes:${C_RESET}\n"
  list_sandboxes
  printf "\n"
}

# print_status — combined health view: host/GPU, OVMS, the installed Harness
# agent, and every registered sandbox. Read-only; touches nothing.
print_status() {
  local agent cli_bin

  printf "\n${C_BOLD}Host${C_RESET}\n"
  if command_exists docker && docker info >/dev/null 2>&1; then
    ok "Docker is running"
  else
    warn "Docker is not running or not installed"
  fi
  if detect_intel_gpu; then
    ok "Intel GPU detected"
  else
    info "No Intel GPU detected (CPU-only)"
  fi

  printf "\n${C_BOLD}Inference backend${C_RESET}\n"
  if [[ -n "${HARNESS_LLM_ROUTER_ENDPOINT:-}" ]]; then
    ok "Routed externally — ${HARNESS_LLM_ROUTER_ENDPOINT} (not managed by this installer)"
  elif ! command_exists docker; then
    info "Docker not installed"
  elif docker inspect "$HARNESS_OVMS_CONTAINER" >/dev/null 2>&1; then
    if [[ "$(docker inspect -f '{{.State.Running}}' "$HARNESS_OVMS_CONTAINER" 2>/dev/null)" == "true" ]]; then
      ok "Running — $(harness_llm_endpoint)"
    else
      warn "Container exists but is not running (${HARNESS_OVMS_CONTAINER})"
    fi
  else
    info "Not installed"
  fi

  printf "\n${C_BOLD}Harness agent${C_RESET}\n"
  local display
  agent="$(canonical_agent_name "${HARNESS_AGENT:-openclaw}")"
  cli_bin="$(agent_cli_bin "$agent")"
  display="$(agent_display_name "$agent")"
  if [[ -n "$cli_bin" ]] && command_exists "$cli_bin"; then
    ok "${display} installed ($(command -v "$cli_bin"))"
  elif [[ -n "$cli_bin" && -x "${HARNESS_SHIM_DIR}/${cli_bin}" ]]; then
    # Shim exists but isn't resolvable via this shell's current PATH yet
    # (e.g. .bashrc was updated after this terminal started) — command -v
    # alone would wrongly report it as not installed.
    warn "${display} installed (${HARNESS_SHIM_DIR}/${cli_bin}) but not on this
shell's PATH yet — open a new terminal, or re-source your shell profile."
  else
    info "${display} not installed"
  fi

  printf "\n${C_BOLD}Sandboxes${C_RESET}\n"
  list_sandboxes
  printf "\n"
}

run_sandbox_command() {
  local verb="${1:-}" name="${2:-}"
  shift || true
  [[ -n "$verb" ]] || { usage; error "sandbox requires a verb (list/create/start/stop/destroy/backup/backup-all/recover/recover-all)."; }
  case "$verb" in
    list) list_sandboxes ;;
    create) create_sandbox "$name" "${2:-${HARNESS_SANDBOX_IMAGE:-}}" "" "${3:-}" ;;
    start) start_sandbox "$name" ;;
    stop) stop_sandbox "$name" ;;
    destroy) destroy_sandbox "$name" "${2:-}" ;;
    backup) backup_sandbox "$name" ;;
    backup-all) backup_all_sandboxes ;;
    recover) recover_sandbox "$name" ;;
    recover-all) recover_all_sandboxes ;;
    *) usage; error "Unknown sandbox verb: $verb" ;;
  esac
}

run_models_command() {
  local verb="${1:-}" name="${2:-}"
  [[ -n "$verb" ]] || { usage; error "models requires a verb (list/remove)."; }
  case "$verb" in
    list) list_exported_models ;;
    remove) remove_exported_model "$name" ;;
    *) usage; error "Unknown models verb: $verb" ;;
  esac
}

# run_mcp_command — registers an arbitrary MCP endpoint URL with an agent.
# Reuses harness_register_mcp_endpoint (Hermes built in;
# HARNESS_MCP_REGISTER_CMD for anything else) — see harness-mcp.sh.
run_mcp_command() {
  local verb="${1:-}" name="${2:-}" url="${3:-}" agent="${4:-${HARNESS_AGENT:-hermes}}"
  [[ -n "$verb" ]] || { usage; error "mcp requires a verb (register)."; }
  case "$verb" in
    register)
      [[ -n "$name" && -n "$url" ]] || error "Usage: ./install.sh mcp register <name> <url> [agent]"
      harness_register_mcp_endpoint "$agent" "$name" "$url"
      ;;
    *) usage; error "Unknown mcp verb: $verb" ;;
  esac
}

# run_skill_command — Hermes-only (see agents.sh hermes_skill_install); the
# other catalog agents own their own plugin/skill mechanisms.
run_skill_command() {
  local verb="${1:-}" arg="${2:-}"
  [[ -n "$verb" ]] || { usage; error "skill requires a verb (install/list/remove)."; }
  case "$verb" in
    install) hermes_skill_install "$arg" ;;
    list) hermes_skill_list ;;
    remove) hermes_skill_remove "$arg" ;;
    *) usage; error "Unknown skill verb: $verb" ;;
  esac
}

main() {
  local -a positional=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --non-interactive) NON_INTERACTIVE=1 ;;
      --yes-i-accept-third-party-software) ACCEPT_THIRD_PARTY_SOFTWARE=1 ;;
      --skip-gpu-check) SKIP_GPU_CHECK=1 ;;
      --agent) HARNESS_AGENT="$2"; shift ;;
      --hf-model) HARNESS_HF_MODEL="$2"; shift ;;
      --help | -h) usage; exit 0 ;;
      --) ;;
      *) positional+=("$1") ;;
    esac
    shift
  done
  export NON_INTERACTIVE ACCEPT_THIRD_PARTY_SOFTWARE
  export HARNESS_AGENT HARNESS_HF_MODEL

  if [[ "${positional[0]:-}" == "sandbox" ]]; then
    require_third_party_notice_acceptance
    run_sandbox_command "${positional[@]:1}"
    exit 0
  fi
  if [[ "${positional[0]:-}" == "models" ]]; then
    require_third_party_notice_acceptance
    run_models_command "${positional[@]:1}"
    exit 0
  fi
  if [[ "${positional[0]:-}" == "mcp" ]]; then
    require_third_party_notice_acceptance
    run_mcp_command "${positional[@]:1}"
    exit 0
  fi
  if [[ "${positional[0]:-}" == "skill" ]]; then
    require_third_party_notice_acceptance
    run_skill_command "${positional[@]:1}"
    exit 0
  fi
  if [[ "${positional[0]:-}" == "connect" ]]; then
    require_third_party_notice_acceptance
    connect_sandbox "${positional[1]:-}"
    exit 0
  fi
  if [[ "${positional[0]:-}" == "status" ]]; then
    require_third_party_notice_acceptance
    print_status
    exit 0
  fi
  if [[ "${positional[0]:-}" == "onboard" ]]; then
    run_agent_onboard
    exit 0
  fi
  if [[ -n "${positional[0]:-}" ]]; then
    usage
    error "Unknown command: ${positional[0]}"
  fi

  printf "\n${C_GREEN}${C_BOLD}Intel Agent Harness${C_RESET}\n\n"

  require_third_party_notice_acceptance
  prepare_installer_host

  step 1 "$TOTAL_STEPS" "Node.js"
  install_nodejs

  step 2 "$TOTAL_STEPS" "Inference routing"
  ensure_inference_backend
  export HARNESS_LLM_ENDPOINT="${HARNESS_LLM_ENDPOINT:-$(harness_llm_endpoint)}"
  ok "LLM endpoint: ${HARNESS_LLM_ENDPOINT}"

  step 3 "$TOTAL_STEPS" "Agent install"
  install_selected_agent

  step 4 "$TOTAL_STEPS" "Onboarding"
  run_agent_onboard

  print_done
}

main "$@"
