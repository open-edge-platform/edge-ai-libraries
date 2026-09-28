# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# Pluggable "install your own CLI" step — mirrors the source-checkout vs.
# git-clone-a-release-ref pattern, but points at whatever repo/CLI you
# configure instead of a hardcoded product.
#
# Configure via env vars (or --repo/--ref/--cli-bin flags):
#   PROJECT_REPO_URL   git remote to clone when not running from a checkout
#   PROJECT_INSTALL_REF  git ref/tag to install (default: main)
#   PROJECT_CLI_BIN      expected binary name after `npm link` (default: myagent)

resolve_repo_root() {
  local base="${PROJECT_REPO_ROOT:-$SCRIPT_DIR/..}"
  (cd "$base" && pwd)
}

is_source_checkout() {
  local repo_root="$1"
  [[ -f "${repo_root}/package.json" ]]
}

clone_project_ref() {
  local repo_url="$1" ref="$2" dest="$3"
  command_exists git || error "git is required to install from ${repo_url}."
  git init --quiet "$dest"
  git -C "$dest" remote add origin "$repo_url"
  git -C "$dest" fetch --quiet --depth 1 origin "+${ref}:refs/project-install/target" \
    || error "Requested ref '$ref' is not available from ${repo_url}."
  git -C "$dest" -c advice.detachedHead=false checkout --quiet --detach refs/project-install/target
}

install_project_cli() {
  local repo_root cli_bin="${PROJECT_CLI_BIN:-myagent}"
  repo_root="$(resolve_repo_root)"

  if is_source_checkout "$repo_root"; then
    info "Installing ${cli_bin} from the local source checkout at ${repo_root}…"
    spin "Installing dependencies" bash -c "cd \"$repo_root\" && npm install --prefer-offline"
    spin "Building" bash -c "cd \"$repo_root\" && npm run --if-present build"
    spin "Linking CLI" bash -c "cd \"$repo_root\" && npm link"
  else
    [[ -n "${PROJECT_REPO_URL:-}" ]] || error "Set PROJECT_REPO_URL (or run --repo <git-url>) to install
${cli_bin} — no local package.json checkout was found at ${repo_root}."
    local ref="${PROJECT_INSTALL_REF:-main}"
    local src_dir="${HOME}/.local/share/${cli_bin}/source"
    info "Installing ${cli_bin} from ${PROJECT_REPO_URL}@${ref}…"
    rm -rf "$src_dir"
    mkdir -p "$(dirname "$src_dir")"
    spin "Cloning ${cli_bin} source" clone_project_ref "$PROJECT_REPO_URL" "$ref" "$src_dir"
    spin "Installing dependencies" bash -c "cd \"$src_dir\" && npm install --prefer-offline"
    spin "Building" bash -c "cd \"$src_dir\" && npm run --if-present build"
    spin "Linking CLI" bash -c "cd \"$src_dir\" && npm link"
  fi
}

verify_project_cli() {
  local cli_bin="${PROJECT_CLI_BIN:-myagent}"
  if command_exists "$cli_bin"; then
    ok "Verified: ${cli_bin} is available at $(command -v "$cli_bin")"
    return 0
  fi
  warn "Could not resolve '${cli_bin}' on PATH. If npm's global bin isn't on PATH yet,
open a new terminal or add it manually."
  return 1
}

# Undoes install_project_cli's `npm link`. Only removes the managed clone
# under ~/.local/share/<cli_bin>/source — never a local source checkout,
# since that's the user's own project, not something this installer owns.
remove_project_cli() {
  local cli_bin="${PROJECT_CLI_BIN:-myagent}" src_dir
  if command_exists npm; then
    npm rm -g "$cli_bin" >/dev/null 2>&1 || true
  fi
  src_dir="${HOME}/.local/share/${cli_bin}/source"
  if [[ -d "$src_dir" && ! -L "$src_dir" ]]; then
    info "Removing ${cli_bin} source checkout (${src_dir})…"
    rm -rf -- "$src_dir"
  fi
}
