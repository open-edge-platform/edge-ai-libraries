#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Uninstaller — removes the Inference Router and OpenVINO Model
# Server, the installed agent (package + CLI shim), and this installer's
# state directory. Leaves Docker, Node.js/nvm, and the Intel compute runtime
# installed, since those are system tools this installer doesn't own.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
for lib in colors state sudo shim gpu-intel docker-setup nodejs openvino inference-router agents; do
  # shellcheck disable=SC1090
  . "${SCRIPT_DIR}/scripts/lib/${lib}.sh"
done

ASSUME_YES=""
DELETE_MODELS=""
KEEP_AGENT_DATA="${KEEP_AGENT_DATA:-}"

usage() {
  cat <<EOF

  ${C_BOLD}agent-harness-install — Uninstall${C_RESET}

  Usage:
    ./uninstall.sh [--yes] [--delete-models] [--keep-agent-data] [--harness <name>]

  Removes the Inference Router and OpenVINO Model
  Server containers, the installed agent (its package, e.g. "npm uninstall
  -g", and its CLI shim), and this installer's state directory
  (~/.agent-harness-install). For Hermes, this also deletes its data directory
  (~/.hermes — config, sessions, memories, skills); for deepagents-code
  (dcode), ~/.deepagents (config, sessions) — unless --keep-agent-data is
  passed. Docker, Node.js/nvm, and the Intel compute runtime are left
  installed — remove those yourself if you no longer need them.

  Options:
    --yes               Skip the confirmation prompt
    --delete-models     Also delete exported OpenVINO models (HARNESS_MODELS_DIR)
    --keep-agent-data   Keep Hermes's ~/.hermes or dcode's ~/.deepagents data directory (sets KEEP_AGENT_DATA=1)
    --harness <name>     Agent to remove (default: HARNESS_AGENT, else the agent recorded at install time, else openclaw)
    --help, -h           Show this help message and exit

EOF
}

confirm_uninstall() {
  local target="$1"
  [[ -n "$ASSUME_YES" ]] && return 0
  local prompt answer=""
  prompt="  This removes the inference server, ${target}, and $(harness_state_root). Continue? [y/N]: "
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

# Refuses a models directory whose recursive deletion could take more than
# exported models with it: relative or empty paths, symlinks, /, the home
# directory, or any ancestor of it.
assert_models_dir_safe() {
  local dir="$1" resolved home_resolved
  [[ "$dir" == /* ]] || error "Refusing to delete HARNESS_MODELS_DIR='${dir}': not an absolute path."
  [[ ! -L "$dir" ]] || error "Refusing to delete HARNESS_MODELS_DIR='${dir}': it is a symlink."
  resolved="$(realpath -m -- "$dir" 2>/dev/null || true)"
  home_resolved="$(realpath -m -- "$HOME" 2>/dev/null || true)"
  [[ -n "$resolved" && -n "$home_resolved" ]] \
    || error "Refusing to delete HARNESS_MODELS_DIR='${dir}': could not resolve its canonical path."
  if [[ "$resolved" == "/" || "$resolved" == "$home_resolved" || "$home_resolved" == "$resolved"/* ]]; then
    error "Refusing to delete HARNESS_MODELS_DIR='${dir}': it is, or contains, your home directory."
  fi
}

# Clears the state directory's own files/locks, but keeps the models dir (and
# any entry that contains it) unless --delete-models already removed it.
remove_state_dir() {
  local state_root models_dir entry
  state_root="$(harness_state_root)"
  [[ -d "$state_root" ]] || return 0
  assert_state_path_safe "$state_root"
  models_dir="$HARNESS_MODELS_DIR"
  for entry in "$state_root"/* "$state_root"/.[!.]*; do
    [[ -e "$entry" ]] || continue
    if [[ -z "$DELETE_MODELS" ]]; then
      [[ "$entry" == "$models_dir" || "$models_dir" == "$entry"/* ]] && continue
    fi
    rm -rf -- "$entry"
  done
  rmdir "$state_root" 2>/dev/null || true
}

main() {
  [[ -n "${HOME:-}" ]] || error "HOME is not set; refusing to guess the state directory to remove."
  # Shared with run_agent_onboard/print_status (see resolve_installed_agent
  # in agents.sh) so all read paths agree on which agent was actually
  # installed instead of each re-deriving it slightly differently.
  local agent
  agent="$(resolve_installed_agent)"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --yes) ASSUME_YES=1 ;;
      --delete-models) DELETE_MODELS=1 ;;
      --keep-agent-data) KEEP_AGENT_DATA=1 ;;
      --harness)
        [[ -n "${2:-}" ]] || { usage; error "--harness requires a value (openclaw|deepagents-code|hermes)."; }
        agent="$2"; shift ;;
      --agent) usage; error "--agent was renamed to --harness." ;;
      --help | -h) usage; exit 0 ;;
      *) usage; error "Unknown option: $1" ;;
    esac
    shift
  done
  export KEEP_AGENT_DATA
  [[ -z "$DELETE_MODELS" ]] || assert_models_dir_safe "${HARNESS_MODELS_DIR:-}"

  local agent_desc
  agent_desc="the installed agent ('$(canonical_agent_name "$agent")')"
  if [[ -z "$KEEP_AGENT_DATA" ]]; then
    case "$(canonical_agent_name "$agent")" in
      hermes) agent_desc="${agent_desc}, including its ~/.hermes data (sessions/memories/skills)" ;;
      deepagents-code) agent_desc="${agent_desc}, including its ~/.deepagents data (sessions/config)" ;;
    esac
  fi

  printf "\n${C_YELLOW}${C_BOLD}agent-harness-install — Uninstall${C_RESET}\n\n"
  confirm_uninstall "$agent_desc"

  info "Removing Inference Router…"
  remove_inference_router
  ok "Inference Router removed"
  if ovms_is_managed; then
    info "Removing OpenVINO Model Server…"
    remove_openvino_model_server
    ok "OpenVINO Model Server removed"
  else
    info "Skipping OpenVINO Model Server removal (this install routed to an external
endpoint; this installer never started one)."
  fi

  # Only OpenClaw gets an installer-made shim; dcode and Hermes ship their own links.
  if [[ "$(canonical_agent_name "$agent")" == "openclaw" ]]; then
    remove_cli_shim "$(agent_cli_bin openclaw)" || true
  fi
  remove_agent_package "$agent" || true

  if [[ -n "$DELETE_MODELS" ]]; then
    assert_models_dir_safe "${HARNESS_MODELS_DIR:-}"
    info "Deleting exported models (${HARNESS_MODELS_DIR})…"
    rm -rf -- "${HARNESS_MODELS_DIR:?}"
    ok "Models deleted"
  fi

  info "Removing state directory ($(harness_state_root))…"
  remove_state_dir
  ok "State directory removed"

  printf "\n${C_GREEN}${C_BOLD}=== Uninstall complete ===${C_RESET}\n"
  printf "  ${C_DIM}Docker, Node.js/nvm, and the Intel compute runtime were left installed.${C_RESET}\n\n"
}

main "$@"
