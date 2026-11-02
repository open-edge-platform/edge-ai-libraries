#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# vss-bootstrap.sh - Make the Video Search and Summarization (VSS) application
# source available and resolve its app root, regardless of where a VSS skill is
# invoked from.
#
# Behaviour
#   * If the current working directory is already somewhere inside a VSS checkout
#     (or the enclosing git repo contains one), that checkout is reused and NO
#     clone is performed.
#   * Otherwise the VSS application is fetched with a shallow, single-branch,
#     sparse checkout of only
#     `sample-applications/video-search-and-summarization` from `main`.
#
# Output
#   The resolved absolute VSS app root is printed on stdout as the ONLY stdout
#   line. All diagnostics go to stderr. Callers should do:
#       APP_ROOT="$(bash vss-bootstrap.sh)" && cd "$APP_ROOT"
#
# Environment overrides
#   VSS_REPO_URL     Git URL to clone (default: upstream open-edge-platform).
#   VSS_REPO_BRANCH  Branch to fetch (default: main).
#   VSS_CLONE_DIR    Where to place the checkout when cloning is required
#                    (default: ${XDG_CACHE_HOME:-$HOME/.cache}/vss-src/edge-ai-libraries).
#   VSS_FORCE_CLONE  If set to 1, skip local detection and always clone.
#
# Exit status
#   0 on success (app root printed), non-zero on failure.

set -euo pipefail

REPO_URL="${VSS_REPO_URL:-https://github.com/open-edge-platform/edge-ai-libraries.git}"
REPO_BRANCH="${VSS_REPO_BRANCH:-main}"
CACHE_BASE="${XDG_CACHE_HOME:-$HOME/.cache}"
CLONE_DIR="${VSS_CLONE_DIR:-$CACHE_BASE/vss-src/edge-ai-libraries}"
VSS_SUBPATH="sample-applications/video-search-and-summarization"

log() { printf '[vss-bootstrap] %s\n' "$*" >&2; }

# A directory is a VSS app root when it carries the app's unmistakable markers.
is_vss_root() {
  local d="$1"
  [ -n "$d" ] && [ -f "$d/setup.sh" ] \
    && [ -d "$d/docker" ] && [ -d "$d/pipeline-manager" ]
}

# Walk up from a starting directory looking for a VSS app root.
find_vss_root_upward() {
  local dir="$1"
  while [ -n "$dir" ] && [ "$dir" != "/" ]; do
    if is_vss_root "$dir"; then
      printf '%s\n' "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  is_vss_root "/" && { printf '/\n'; return 0; }
  return 1
}

# Try to locate an existing VSS checkout without cloning.
detect_local_vss_root() {
  local found
  # 1) Anywhere in the current directory's ancestry.
  if found="$(find_vss_root_upward "$PWD")"; then
    printf '%s\n' "$found"; return 0
  fi
  # 2) The enclosing git repository, if any, may hold VSS under its subpath.
  local git_root
  if git_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    if is_vss_root "$git_root/$VSS_SUBPATH"; then
      printf '%s\n' "$git_root/$VSS_SUBPATH"; return 0
    fi
    if is_vss_root "$git_root"; then
      printf '%s\n' "$git_root"; return 0
    fi
  fi
  # 3) A previous bootstrap clone that is already on disk.
  if is_vss_root "$CLONE_DIR/$VSS_SUBPATH"; then
    printf '%s\n' "$CLONE_DIR/$VSS_SUBPATH"; return 0
  fi
  return 1
}

# Sparse, shallow, single-branch clone of just the VSS subtree.
clone_vss() {
  if is_vss_root "$CLONE_DIR/$VSS_SUBPATH"; then
    log "Reusing existing bootstrap checkout at $CLONE_DIR"
    printf '%s\n' "$CLONE_DIR/$VSS_SUBPATH"; return 0
  fi

  command -v git >/dev/null 2>&1 || { log "ERROR: git is required but not found."; return 1; }

  log "VSS source not found locally; sparse-cloning $VSS_SUBPATH"
  log "  repo=$REPO_URL branch=$REPO_BRANCH dest=$CLONE_DIR"
  mkdir -p "$(dirname "$CLONE_DIR")"
  rm -rf "$CLONE_DIR"

  git clone --filter=blob:none --no-checkout --depth 1 \
    --single-branch --branch "$REPO_BRANCH" "$REPO_URL" "$CLONE_DIR" >&2

  git -C "$CLONE_DIR" sparse-checkout init --cone >&2
  git -C "$CLONE_DIR" sparse-checkout set "$VSS_SUBPATH" >&2
  git -C "$CLONE_DIR" checkout "$REPO_BRANCH" >&2

  if ! is_vss_root "$CLONE_DIR/$VSS_SUBPATH"; then
    log "ERROR: clone completed but $VSS_SUBPATH does not look like a VSS app root."
    return 1
  fi
  log "Clone complete."
  printf '%s\n' "$CLONE_DIR/$VSS_SUBPATH"
}

main() {
  local root
  if [ "${VSS_FORCE_CLONE:-0}" != "1" ] && root="$(detect_local_vss_root)"; then
    log "Found existing VSS source at: $root (no clone needed)"
    printf '%s\n' "$root"
    return 0
  fi
  root="$(clone_vss)"
  printf '%s\n' "$root"
}

main "$@"
