#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# vsa-bootstrap.sh - Make the Video Summary Accuracy Analyzer source available
# and resolve its project root, regardless of where this skill is invoked from.
#
# Behavior
#   * If the current working directory is already inside an analyzer checkout
#     (or the enclosing git repo contains one), reuse it and do not clone.
#   * Otherwise fetch only `tools/video-summary-accuracy-analyzer` using a
#     shallow, single-branch, sparse checkout.
#
# Output
#   Prints the resolved absolute analyzer root on stdout as the ONLY stdout
#   line. Diagnostics are sent to stderr. Caller usage:
#       APP_ROOT="$(bash vsa-bootstrap.sh)" && cd "$APP_ROOT"
#
# Environment overrides
#   VSA_REPO_URL      Git URL to clone.
#   VSA_REPO_BRANCH   Branch to fetch.
#   VSA_CLONE_DIR     Checkout destination used when cloning is required.
#   VSA_FORCE_CLONE   If 1, skip local detection and always clone.
#
# Exit status
#   0 on success (analyzer root printed), non-zero on failure.

set -euo pipefail

REPO_URL="${VSA_REPO_URL:-https://github.com/rudra-intel/edge-ai-libraries.git}"  #"${VSA_REPO_URL:-https://github.com/open-edge-platform/edge-ai-libraries.git}"
REPO_BRANCH="video-summary-accuracy" #"${VSA_REPO_BRANCH:-main}"
CACHE_BASE="${XDG_CACHE_HOME:-$HOME/.cache}"
CLONE_DIR="${VSA_CLONE_DIR:-$CACHE_BASE/video-summary-accuracy-src/edge-ai-libraries}"
VSA_SUBPATH="tools/video-summary-accuracy-analyzer"

log() { printf '[vsa-bootstrap] %s\n' "$*" >&2; }

is_analyzer_root() {
  local d="$1"
  [ -n "$d" ] \
    && [ -f "$d/pyproject.toml" ] \
    && [ -f "$d/nginx.conf" ] \
    && [ -f "$d/scripts/setup_env.sh" ] \
    && [ -f "$d/src/evaluate.py" ] \
    && [ -f "$d/src/server.py" ] \
    && [ -f "$d/docker/compose.yaml" ]
}

find_analyzer_root_upward() {
  local dir="$1"
  while [ -n "$dir" ] && [ "$dir" != "/" ]; do
    if is_analyzer_root "$dir"; then
      printf '%s\n' "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  return 1
}

detect_local_analyzer_root() {
  local found
  if found="$(find_analyzer_root_upward "$PWD")"; then
    printf '%s\n' "$found"
    return 0
  fi

  local git_root
  if git_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    if is_analyzer_root "$git_root/$VSA_SUBPATH"; then
      printf '%s\n' "$git_root/$VSA_SUBPATH"
      return 0
    fi
    if is_analyzer_root "$git_root"; then
      printf '%s\n' "$git_root"
      return 0
    fi
  fi

  if is_analyzer_root "$CLONE_DIR/$VSA_SUBPATH"; then
    printf '%s\n' "$CLONE_DIR/$VSA_SUBPATH"
    return 0
  fi

  return 1
}

clone_analyzer() {
  if [ "${VSA_FORCE_CLONE:-0}" != "1" ] && is_analyzer_root "$CLONE_DIR/$VSA_SUBPATH"; then
    log "Reusing existing bootstrap checkout at $CLONE_DIR"
    printf '%s\n' "$CLONE_DIR/$VSA_SUBPATH"
    return 0
  fi

  command -v git >/dev/null 2>&1 || {
    log "ERROR: git is required but not found."
    return 1
  }

  log "Analyzer source not found locally; sparse-cloning $VSA_SUBPATH"
  log "  repo=$REPO_URL branch=$REPO_BRANCH dest=$CLONE_DIR"
  mkdir -p "$(dirname "$CLONE_DIR")"
  rm -rf "$CLONE_DIR"

  git clone --filter=blob:none --no-checkout --depth 1 \
    --single-branch --branch "$REPO_BRANCH" "$REPO_URL" "$CLONE_DIR" >&2

  git -C "$CLONE_DIR" sparse-checkout init --cone >&2
  git -C "$CLONE_DIR" sparse-checkout set "$VSA_SUBPATH" >&2
  git -C "$CLONE_DIR" checkout "$REPO_BRANCH" >&2

  if ! is_analyzer_root "$CLONE_DIR/$VSA_SUBPATH"; then
    log "ERROR: $VSA_SUBPATH was not found or is incomplete on $REPO_URL ($REPO_BRANCH)."
    log "       Set VSA_REPO_URL and/or VSA_REPO_BRANCH to a fork or branch that contains it."
    return 1
  fi

  log "Clone complete."
  printf '%s\n' "$CLONE_DIR/$VSA_SUBPATH"
}

main() {
  local root
  if [ "${VSA_FORCE_CLONE:-0}" != "1" ] && root="$(detect_local_analyzer_root)"; then
    log "Found existing analyzer source at: $root (no clone needed)"
    printf '%s\n' "$root"
    return 0
  fi

  root="$(clone_analyzer)"
  printf '%s\n' "$root"
}

main "$@"
