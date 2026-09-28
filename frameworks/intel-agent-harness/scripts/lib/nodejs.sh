# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# Node.js bootstrap via nvm — vendor-agnostic, reused as-is from the pattern.
# Floor matches openclaw's real published engines constraint (>=24.16.0
# <25 || >=26.1.0); a lower default would silently accept a system Node too
# old for the agent catalog to actually install.
MIN_NODE_VERSION="${MIN_NODE_VERSION:-24.16.0}"
# Pinned to a specific LTS release (rather than a floating --lts) for
# reproducible installs; bump deliberately when validating a newer LTS.
PLATFORM_NODE_VERSION="${PLATFORM_NODE_VERSION:-24.21.0}"

version_gte() {
  [[ "$1" =~ ^[0-9]+(\.[0-9]+){0,2}$ ]] || return 1
  [[ "$2" =~ ^[0-9]+(\.[0-9]+){0,2}$ ]] || return 1
  local -a a b
  IFS=. read -ra a <<<"$1"
  IFS=. read -ra b <<<"$2"
  for i in 0 1 2; do
    local ai=${a[$i]:-0} bi=${b[$i]:-0}
    ((ai > bi)) && return 0
    ((ai < bi)) && return 1
  done
  return 0
}

ensure_nvm_loaded() {
  # Always set NVM_DIR and (re-)source nvm.sh — sourcing it repeatedly is
  # safe/idempotent. A prior early-return here on "any node already on
  # PATH" was wrong whenever that node was a pre-existing system install
  # rather than nvm's own: NVM_DIR never got set, and the next line's
  # unguarded "$NVM_DIR" reference crashed under `set -u`.
  [[ -z "${NVM_DIR:-}" ]] && export NVM_DIR="$HOME/.nvm"
  [[ -s "$NVM_DIR/nvm.sh" ]] && \. "$NVM_DIR/nvm.sh"
}

# A system-package Node (e.g. apt) commonly puts npm's global prefix under
# /usr, which a non-root user can't write to — `npm install -g` then fails
# with EACCES even though the Node version itself is fine. Checking the
# version alone isn't enough; this catches that case so it falls through to
# the per-user nvm install below instead of silently trusting a broken Node.
npm_global_prefix_writable() {
  command_exists npm || return 1
  local prefix modules_dir
  prefix="$(npm config get prefix 2>/dev/null)" || return 1
  [[ -n "$prefix" ]] || return 1
  modules_dir="${prefix}/lib/node_modules"
  if [[ -d "$modules_dir" ]]; then
    [[ -w "$modules_dir" ]]
  else
    [[ -w "$prefix" ]]
  fi
}

install_nodejs() {
  if command_exists node && version_gte "$(node --version | tr -d v)" "$MIN_NODE_VERSION" \
    && npm_global_prefix_writable; then
    info "Node.js found: $(node --version)"
    return 0
  fi

  info "Installing Node.js (>=${MIN_NODE_VERSION}) via nvm…"
  local nvm_version="v0.40.4"
  # IMPORTANT: update this hash whenever nvm_version above changes.
  local nvm_sha256="4b7412c49960c7d31e8df72da90c1fb5b8cccb419ac99537b737028d497aba4f"
  local nvm_tmp
  nvm_tmp="$(mktemp)"
  fetch_and_verify "https://raw.githubusercontent.com/nvm-sh/nvm/${nvm_version}/install.sh" \
    "$nvm_tmp" "nvm installer" "$nvm_sha256"
  assert_shell_script "$nvm_tmp" "nvm installer"
  spin "Installing nvm" bash "$nvm_tmp"
  rm -f "$nvm_tmp"

  # nvm.sh itself isn't written to be `set -u`-safe — it references internal
  # variables (e.g. PROVIDED_VERSION) that are conditionally unset depending
  # on the code path. Nounset must be off for anything that sources it or
  # calls the `nvm` function, restored before returning either way.
  set +u
  ensure_nvm_loaded
  spin "Installing Node.js ${PLATFORM_NODE_VERSION}" bash -c "set +u; . \"$NVM_DIR/nvm.sh\" && nvm install ${PLATFORM_NODE_VERSION} --no-progress"
  ensure_nvm_loaded
  nvm use "$PLATFORM_NODE_VERSION" --silent
  set -u
  ok "Node.js installed: $(node --version)"
  warn "Open a new terminal, or run: source \"\${NVM_DIR:-\$HOME/.nvm}/nvm.sh\" && nvm use ${PLATFORM_NODE_VERSION}"
}
