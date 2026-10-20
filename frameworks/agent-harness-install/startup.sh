#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# agent-harness-install -- prerequisite setup. Installs/verifies the host
# tooling ./install.sh depends on but does not bootstrap itself: Docker,
# Node.js/npm (via nvm, needed by the openclaw agent), and Python 3 (venv +
# PyYAML, needed by the hf-snapshot/export-model-py OVMS exporters and
# test/full-flow-test.sh). Run this once per host before ./install.sh; safe
# to re-run -- every check is idempotent and skips what's already present.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
for lib in colors verify sudo docker-setup nodejs python-setup; do
  # shellcheck disable=SC1090
  . "${SCRIPT_DIR}/scripts/lib/${lib}.sh"
done

NON_INTERACTIVE="${NON_INTERACTIVE:-}"
SKIP_DOCKER="${SKIP_DOCKER:-}"
SKIP_NODEJS="${SKIP_NODEJS:-}"
SKIP_PYTHON="${SKIP_PYTHON:-}"
SKIP_BASE="${SKIP_BASE:-}"

# ensure_base_tools -- curl (fetch_and_verify's downloads) and git (the
# standalone-fetch bootstrap's clone) are hard requirements used throughout
# this installer, but nothing installed them before this -- a minimal/fresh
# Ubuntu server image commonly ships without either.
ensure_base_tools() {
  local -a missing=()
  command_exists curl || missing+=(curl)
  command_exists git || missing+=(git)
  [[ "${#missing[@]}" -eq 0 ]] && return 0
  if command_exists apt-get; then
    info "Installing missing base tools: ${missing[*]}…"
    sudo apt-get update -qq
    sudo apt-get install -y -qq "${missing[@]}"
  else
    error "Missing required tool(s): ${missing[*]}. This installer only knows
how to install them via apt-get -- install them yourself, then re-run."
  fi
}

usage() {
  cat <<EOF

  ${C_BOLD}agent-harness-install — Prerequisite Setup${C_RESET}

  Usage:
    ./startup.sh [options]

  Checks for, and installs if missing, the host tooling this installer
  depends on: curl/git, Docker, Node.js/npm (via nvm), and Python 3
  (venv + PyYAML). Safe to re-run — every check is idempotent and skips
  what's already present. Run this once before ./install.sh.

  Options:
    --non-interactive   Skip prompts (uses env vars / defaults)
    --skip-base          Skip the curl/git check/install
    --skip-docker        Skip the Docker check/install
    --skip-nodejs        Skip the Node.js/npm check/install
    --skip-python        Skip the Python (venv/PyYAML) check/install
    --help, -h           Show this help message and exit

  Environment:
    NON_INTERACTIVE=1, SKIP_BASE=1, SKIP_DOCKER=1, SKIP_NODEJS=1, SKIP_PYTHON=1
    DOCKER_INSTALL_SHA256            Pin get.docker.com's expected SHA-256 (non-apt hosts only; required unless DOCKER_ALLOW_UNVERIFIED_INSTALL=1)
    DOCKER_ALLOW_UNVERIFIED_INSTALL  Run the Docker convenience script without a pinned checksum (not recommended)
    HTTP_PROXY, HTTPS_PROXY, NO_PROXY  (either case) Also configures the
                                   Docker daemon's own proxy so it can pull
                                   images through it
    MIN_NODE_VERSION, HARNESS_NODE_VERSION

  Exit codes:
    0  Everything is ready.
    1  A real failure (see the printed error).
    2  Just added this user to the docker group, and couldn't refresh it in
       this shell automatically ('sg'/'sudo' both unavailable or failed) --
       open a new terminal (or run 'newgrp docker') and re-run. Rare:
       normally this is handled automatically by restarting under the new
       group, no new shell needed.

EOF
}

main() {
  local -a original_args=("$@")
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --non-interactive) NON_INTERACTIVE=1 ;;
      --skip-docker) SKIP_DOCKER=1 ;;
      --skip-nodejs) SKIP_NODEJS=1 ;;
      --skip-python) SKIP_PYTHON=1 ;;
      --skip-base) SKIP_BASE=1 ;;
      --help | -h) usage; exit 0 ;;
      *) usage; error "Unknown option: $1" ;;
    esac
    shift
  done
  export NON_INTERACTIVE

  printf "\n${C_GREEN}${C_BOLD}agent-harness-install — Prerequisite Setup${C_RESET}\n\n"

  if [[ -z "$SKIP_BASE" ]]; then
    info "Checking base tools (curl, git)…"
    ensure_base_tools
    ok "Base tools are ready"
  else
    info "Skipping base tools (--skip-base)."
  fi

  if [[ -z "$SKIP_DOCKER" ]]; then
    info "Checking Docker…"
    # A docker-group-just-granted condition (return 2) is handled by
    # ensure_docker_group_active re-exec'ing this whole script under the
    # new group below -- tolerate it here instead of letting set -e abort.
    ensure_docker || true
    ensure_docker_group_active "$0" "${original_args[@]}"
    docker info >/dev/null 2>&1 || error "Docker is installed but not reachable. Try: sudo systemctl start docker"
    ok "Docker is ready"
  else
    info "Skipping Docker (--skip-docker)."
  fi

  if [[ -z "$SKIP_NODEJS" ]]; then
    info "Checking Node.js…"
    install_nodejs
  else
    info "Skipping Node.js (--skip-nodejs)."
  fi

  if [[ -z "$SKIP_PYTHON" ]]; then
    info "Checking Python…"
    ensure_python_prereqs
  else
    info "Skipping Python (--skip-python)."
  fi

  printf "\n${C_GREEN}${C_BOLD}=== Prerequisites ready ===${C_RESET}\n\n"
  printf "  Run ${C_BOLD}./install.sh${C_RESET} next.\n\n"
}

main "$@"
