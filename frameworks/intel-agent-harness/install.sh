#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Thin installer bootstrap. When run from a source checkout it just
# delegates to scripts/install.sh; when fetched standalone (e.g. via
# `curl | bash`) it clones the pinned ref of this installer's own repo to a
# temp dir first, then execs the versioned payload from there. See
# scripts/install.sh for the actual install flow, and uninstall.sh to remove
# what this installer set up.
set -euo pipefail

# Only trust BASH_SOURCE when it points at a real file on disk — piped
# execution (curl | bash) has no backing file, so falling back to $0 would
# silently resolve to the caller's cwd instead of signaling standalone mode.
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
  SCRIPT_DIR=""
fi
PLATFORM_INSTALL_REPO="${PLATFORM_INSTALL_REPO:-}"
PLATFORM_INSTALL_REF="${PLATFORM_INSTALL_REF:-}"

is_source_checkout() {
  [[ -n "$SCRIPT_DIR" && -f "${SCRIPT_DIR}/scripts/install.sh" && -d "${SCRIPT_DIR}/scripts/lib" ]]
}

# Version resolution order: explicit env var, then a repo-local .version
# file, then "main" — mirrors checking an env var / git tag / version file.
resolve_install_ref() {
  if [[ -n "$PLATFORM_INSTALL_REF" ]]; then
    printf '%s' "$PLATFORM_INSTALL_REF"
  elif [[ -n "$SCRIPT_DIR" && -f "${SCRIPT_DIR}/.version" ]]; then
    tr -d '[:space:]' <"${SCRIPT_DIR}/.version"
  else
    printf 'main'
  fi
}

clone_installer_ref() {
  local ref="$1" dest="$2"
  command -v git >/dev/null 2>&1 || { echo "git is required to install." >&2; exit 1; }
  case "$PLATFORM_INSTALL_REPO" in
    http://*)
      echo "PLATFORM_INSTALL_REPO must use https:// or an SSH remote (git@...), not plain http://: $PLATFORM_INSTALL_REPO" >&2
      exit 1
      ;;
  esac
  git init --quiet "$dest"
  git -C "$dest" remote add origin "$PLATFORM_INSTALL_REPO"
  git -C "$dest" fetch --quiet --depth 1 origin "+${ref}:refs/installer-bootstrap/target" \
    || { echo "Could not fetch ref '${ref}' from ${PLATFORM_INSTALL_REPO}." >&2; exit 1; }
  git -C "$dest" -c advice.detachedHead=false checkout --quiet --detach refs/installer-bootstrap/target
  # Git verifies object integrity itself (content-addressed by hash); print
  # the resolved commit so a mutable ref (e.g. a branch) is still auditable.
  echo "Resolved ${ref} -> $(git -C "$dest" rev-parse --verify HEAD)" >&2
}

main() {
  if is_source_checkout; then
    exec "${SCRIPT_DIR}/scripts/install.sh" "$@"
  fi

  [[ -n "$PLATFORM_INSTALL_REPO" ]] || {
    echo "This script was fetched standalone (no local scripts/ checkout found)." >&2
    echo "Set PLATFORM_INSTALL_REPO=<git-url> to this installer's own repo so it" >&2
    echo "can be cloned, or run it from a full checkout instead — this installer" >&2
    echo "refuses to guess where its own source lives." >&2
    exit 1
  }

  local ref clone_dir
  ref="$(resolve_install_ref)"
  clone_dir="$(mktemp -d)"
  trap 'rm -rf "$clone_dir"' EXIT
  echo "Fetching Intel Agent Harness @ ${ref}…" >&2
  clone_installer_ref "$ref" "$clone_dir"
  "${clone_dir}/scripts/install.sh" "$@"
}

main "$@"


