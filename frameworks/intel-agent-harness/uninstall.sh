#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Uninstaller — removes sandboxes, the OpenVINO Model Server, the installed
# agent (package + CLI shim), and this installer's state directory. Leaves
# Docker, Node.js/nvm, and the Intel compute runtime installed, since those
# are system tools this installer doesn't own.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
for lib in colors state sudo shim gpu-intel docker-setup nodejs install-cli notice gateway sandbox onboard express openvino agents; do
  # shellcheck disable=SC1090
  . "${SCRIPT_DIR}/scripts/lib/${lib}.sh"
done

ASSUME_YES=""
DELETE_MODELS=""
KEEP_AGENT_DATA="${KEEP_AGENT_DATA:-}"

usage() {
  cat <<EOF

  ${C_BOLD}Intel Agent Harness — Uninstall${C_RESET}

  Usage:
    ./uninstall.sh [--yes] [--delete-models] [--keep-agent-data] [--agent <name>]

  Removes all registered sandboxes, the OpenVINO Model Server container, the
  installed agent (its package, e.g. "npm uninstall -g", and its CLI shim),
  and this installer's state directory (~/.intel-agent). For Hermes, this
  also deletes its data directory (~/.hermes — config, sessions, memories,
  skills) unless --keep-agent-data is passed. Docker, Node.js/nvm, and the
  Intel compute runtime are left installed — remove those yourself if you no
  longer need them.

  Options:
    --yes               Skip the confirmation prompt
    --delete-models     Also delete exported OpenVINO models (PLATFORM_MODELS_DIR)
    --keep-agent-data   Keep Hermes's ~/.hermes data directory (sets KEEP_AGENT_DATA=1)
    --agent <name>       Agent to remove (default: PLATFORM_AGENT or openclaw)
    --help, -h           Show this help message and exit

EOF
}

confirm_uninstall() {
  local target="$1"
  [[ -n "$ASSUME_YES" ]] && return 0
  local prompt answer=""
  prompt="  This removes sandboxes, the inference server, ${target}, and $(platform_state_root). Continue? [y/N]: "
  if [[ -t 0 ]]; then
    printf '%s' "$prompt"
    IFS= read -r answer || answer=""
  elif { exec 3</dev/tty; } 2>/dev/null; then
    printf '%s' "$prompt"
    IFS= read -r answer <&3 || answer=""
    exec 3<&-
  else
    error "Uninstall confirmation requires a TTY. Re-run in a terminal, or pass --yes."
  fi
  case "$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')" in
    y | yes) return 0 ;;
    *) error "Uninstall cancelled." ;;
  esac
}

# Clears the state directory's own files/locks, but leaves the models dir
# alone unless --delete-models already removed it above.
remove_state_dir() {
  local state_root models_dir entry
  state_root="$(platform_state_root)"
  [[ -d "$state_root" ]] || return 0
  assert_state_path_safe "$state_root"
  models_dir="$PLATFORM_MODELS_DIR"
  for entry in "$state_root"/* "$state_root"/.[!.]*; do
    [[ -e "$entry" ]] || continue
    [[ "$entry" == "$models_dir" ]] && continue
    rm -rf -- "$entry"
  done
  rmdir "$state_root" 2>/dev/null || true
}

main() {
  [[ -n "${HOME:-}" ]] || error "HOME is not set; refusing to guess the state directory to remove."
  local agent="${PLATFORM_AGENT:-openclaw}"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --yes) ASSUME_YES=1 ;;
      --delete-models) DELETE_MODELS=1 ;;
      --keep-agent-data) KEEP_AGENT_DATA=1 ;;
      --agent) agent="$2"; shift ;;
      --help | -h) usage; exit 0 ;;
      *) usage; error "Unknown option: $1" ;;
    esac
    shift
  done
  export KEEP_AGENT_DATA

  local agent_desc
  if [[ -n "${PROJECT_CLI_BIN:-}" && -z "${PLATFORM_AGENT:-}" ]]; then
    agent_desc="'${PROJECT_CLI_BIN}'"
  else
    agent_desc="the installed agent ('$(canonical_agent_name "$agent")')"
    if [[ "$(canonical_agent_name "$agent")" == "hermes" && -z "$KEEP_AGENT_DATA" ]]; then
      agent_desc="${agent_desc}, including its ~/.hermes data (sessions/memories/skills)"
    fi
  fi

  printf "\n${C_YELLOW}${C_BOLD}Intel Agent Harness — Uninstall${C_RESET}\n\n"
  confirm_uninstall "$agent_desc"

  info "Removing sandboxes…"
  destroy_all_sandboxes || true
  ok "Sandboxes removed"

  info "Removing harness gateway (if used)…"
  remove_gateway
  ok "Harness gateway removed"

  if [[ -n "${PLATFORM_LLM_ROUTER_ENDPOINT:-}" ]]; then
    info "Skipping OpenVINO Model Server removal (routed externally to
${PLATFORM_LLM_ROUTER_ENDPOINT}; this installer never started it)."
  else
    info "Removing OpenVINO Model Server…"
    remove_openvino_model_server
    ok "OpenVINO Model Server removed"
  fi

  if [[ -n "${PROJECT_CLI_BIN:-}" && -z "${PLATFORM_AGENT:-}" ]]; then
    remove_cli_shim "$PROJECT_CLI_BIN" || true
    remove_project_cli || true
  else
    remove_cli_shim "$(agent_cli_bin "$(canonical_agent_name "$agent")")" || true
    remove_agent_package "$agent" || true
  fi

  if [[ -n "$DELETE_MODELS" ]]; then
    info "Deleting exported models (${PLATFORM_MODELS_DIR})…"
    rm -rf -- "${PLATFORM_MODELS_DIR:?}"
    ok "Models deleted"
  fi

  info "Removing state directory ($(platform_state_root))…"
  remove_state_dir
  ok "State directory removed"

  printf "\n${C_GREEN}${C_BOLD}=== Uninstall complete ===${C_RESET}\n"
  printf "  ${C_DIM}Docker, Node.js/nvm, and the Intel compute runtime were left installed.${C_RESET}\n\n"
}

main "$@"
