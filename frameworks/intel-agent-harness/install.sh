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
HARNESS_INSTALL_REPO="${HARNESS_INSTALL_REPO:-}"
HARNESS_INSTALL_REF="${HARNESS_INSTALL_REF:-}"
HARNESS_INSTALL_SUBDIR="${HARNESS_INSTALL_SUBDIR:-}"

is_source_checkout() {
  [[ -n "$SCRIPT_DIR" && -f "${SCRIPT_DIR}/scripts/install.sh" && -d "${SCRIPT_DIR}/scripts/lib" ]]
}

# Version resolution order: explicit env var, then a repo-local .version
# file. Standalone fetches (curl | bash) have no local .version to read, so
# they must set HARNESS_INSTALL_REF explicitly -- silently defaulting to a
# mutable ref like "main" would make the ref pinning below pointless (the
# fetched branch runs immediately, and could differ from what was reviewed).
resolve_install_ref() {
  if [[ -n "$HARNESS_INSTALL_REF" ]]; then
    printf '%s' "$HARNESS_INSTALL_REF"
  elif [[ -n "$SCRIPT_DIR" && -f "${SCRIPT_DIR}/.version" ]]; then
    tr -d '[:space:]' <"${SCRIPT_DIR}/.version"
  else
    echo "This script was fetched standalone, so there is no local .version file to" >&2
    echo "pin a ref from. Set HARNESS_INSTALL_REF=<tag-or-commit> explicitly --" >&2
    echo "this installer refuses to silently install from a mutable 'main'." >&2
    return 1
  fi
}

clone_installer_ref() {
  local ref="$1" dest="$2"
  command -v git >/dev/null 2>&1 || { echo "git is required to install." >&2; exit 1; }
  case "$HARNESS_INSTALL_REPO" in
    http://* | git://*)
      echo "HARNESS_INSTALL_REPO must use https:// or an SSH remote (git@...), not http:// or git://: $HARNESS_INSTALL_REPO" >&2
      exit 1
      ;;
  esac
  git init --quiet "$dest"
  git -C "$dest" remote add origin "$HARNESS_INSTALL_REPO"
  git -C "$dest" fetch --quiet --depth 1 origin "+${ref}:refs/installer-bootstrap/target" \
    || { echo "Could not fetch ref '${ref}' from ${HARNESS_INSTALL_REPO}." >&2; exit 1; }
  git -C "$dest" -c advice.detachedHead=false checkout --quiet --detach refs/installer-bootstrap/target
  # Git verifies object integrity itself (content-addressed by hash); print
  # the resolved commit so a mutable ref (e.g. a branch) is still auditable.
  echo "Resolved ${ref} -> $(git -C "$dest" rev-parse --verify HEAD)" >&2
}

# resolve_payload_dir clone_dir — locates scripts/install.sh within the
# clone. HARNESS_INSTALL_REPO may point at a monorepo where this installer
# lives under a subdirectory rather than at the repo root; set
# HARNESS_INSTALL_SUBDIR to skip searching and go straight there.
resolve_payload_dir() {
  local clone_dir="$1" candidate
  if [[ -n "$HARNESS_INSTALL_SUBDIR" ]]; then
    candidate="${clone_dir}/${HARNESS_INSTALL_SUBDIR}"
  elif [[ -f "${clone_dir}/scripts/install.sh" ]]; then
    candidate="$clone_dir"
  else
    local -a matches=()
    local match
    while IFS= read -r match; do
      matches+=("$(dirname "$(dirname "$match")")")
    done < <(find "$clone_dir" -maxdepth 5 \
      \( -name node_modules -o -name .git \) -prune -o \
      -type f -path '*/scripts/install.sh' -print 2>/dev/null)
    case "${#matches[@]}" in
      1) candidate="${matches[0]}" ;;
      0)
        echo "Could not find scripts/install.sh anywhere in the cloned repo. If" >&2
        echo "HARNESS_INSTALL_REPO is a monorepo, set HARNESS_INSTALL_SUBDIR to this" >&2
        echo "installer's subdirectory within it." >&2
        return 1
        ;;
      *)
        echo "Found multiple scripts/install.sh candidates in the cloned repo; set" >&2
        echo "HARNESS_INSTALL_SUBDIR explicitly to disambiguate:" >&2
        printf '  %s\n' "${matches[@]}" >&2
        return 1
        ;;
    esac
  fi
  [[ -f "${candidate}/scripts/install.sh" ]] || {
    echo "scripts/install.sh not found under '${candidate}' (HARNESS_INSTALL_SUBDIR)." >&2
    return 1
  }
  printf '%s' "$candidate"
}

main() {
  if is_source_checkout; then
    exec "${SCRIPT_DIR}/scripts/install.sh" "$@"
  fi

  [[ -n "$HARNESS_INSTALL_REPO" ]] || {
    echo "This script was fetched standalone (no local scripts/ checkout found)." >&2
    echo "Set HARNESS_INSTALL_REPO=<git-url> to this installer's own repo so it" >&2
    echo "can be cloned, or run it from a full checkout instead — this installer" >&2
    echo "refuses to guess where its own source lives." >&2
    exit 1
  }

  local ref clone_dir payload_dir
  ref="$(resolve_install_ref)" || exit 1
  clone_dir="$(mktemp -d)"
  trap 'rm -rf "$clone_dir"' EXIT
  echo "Fetching Intel Agent Harness @ ${ref}…" >&2
  clone_installer_ref "$ref" "$clone_dir"
  payload_dir="$(resolve_payload_dir "$clone_dir")" || exit 1
  "${payload_dir}/scripts/install.sh" "$@"
}

main "$@"


