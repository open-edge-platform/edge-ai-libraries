#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# chatqna-bootstrap.sh - Make the Chat Question-and-Answer Core application
# source available and resolve its app root, regardless of where this skill is
# invoked from.
#
# Behavior
#   * If the current working directory is already inside a ChatQnA Core checkout
#     (or the enclosing git repo contains one), reuse it and do not clone.
#   * Otherwise fetch only
#     `sample-applications/chat-question-and-answer-core` from `main` using a
#     shallow, single-branch, sparse checkout.
#
# Output
#   Prints the resolved absolute ChatQnA app root on stdout as the ONLY stdout
#   line. Diagnostics are sent to stderr. Caller usage:
#       APP_ROOT="$(bash chatqna-bootstrap.sh)" && cd "$APP_ROOT"
#
# Environment overrides
#   CHATQNA_REPO_URL      Git URL to clone.
#   CHATQNA_REPO_BRANCH   Branch to fetch.
#   CHATQNA_CLONE_DIR     Checkout destination used when cloning is required.
#   CHATQNA_FORCE_CLONE   If 1, skip local detection and always clone.
#
# Exit status
#   0 on success (app root printed), non-zero on failure.

set -euo pipefail

REPO_URL="${CHATQNA_REPO_URL:-https://github.com/open-edge-platform/edge-ai-libraries.git}"
REPO_BRANCH="${CHATQNA_REPO_BRANCH:-main}"
CACHE_BASE="${XDG_CACHE_HOME:-$HOME/.cache}"
CLONE_DIR="${CHATQNA_CLONE_DIR:-$CACHE_BASE/chatqna-src/edge-ai-libraries}"
CHATQNA_SUBPATH="sample-applications/chat-question-and-answer-core"

log() { printf '[chatqna-bootstrap] %s\n' "$*" >&2; }

is_chatqna_root() {
  local d="$1"
  [ -n "$d" ] \
    && [ -f "$d/pyproject.toml" ] \
    && [ -f "$d/README.md" ] \
    && [ -f "$d/scripts/setup_env.sh" ] \
    && [ -d "$d/app" ] \
    && [ -d "$d/docker" ] \
    && [ -d "$d/docs/user-guide" ]
}

find_chatqna_root_upward() {
  local dir="$1"
  while [ -n "$dir" ] && [ "$dir" != "/" ]; do
    if is_chatqna_root "$dir"; then
      printf '%s\n' "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  is_chatqna_root "/" && { printf '/\n'; return 0; }
  return 1
}

detect_local_chatqna_root() {
  local found
  if found="$(find_chatqna_root_upward "$PWD")"; then
    printf '%s\n' "$found"
    return 0
  fi

  local git_root
  if git_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    if is_chatqna_root "$git_root/$CHATQNA_SUBPATH"; then
      printf '%s\n' "$git_root/$CHATQNA_SUBPATH"
      return 0
    fi
    if is_chatqna_root "$git_root"; then
      printf '%s\n' "$git_root"
      return 0
    fi
  fi

  if is_chatqna_root "$CLONE_DIR/$CHATQNA_SUBPATH"; then
    printf '%s\n' "$CLONE_DIR/$CHATQNA_SUBPATH"
    return 0
  fi

  return 1
}

clone_chatqna() {
  if is_chatqna_root "$CLONE_DIR/$CHATQNA_SUBPATH"; then
    log "Reusing existing bootstrap checkout at $CLONE_DIR"
    printf '%s\n' "$CLONE_DIR/$CHATQNA_SUBPATH"
    return 0
  fi

  command -v git >/dev/null 2>&1 || {
    log "ERROR: git is required but not found."
    return 1
  }

  log "ChatQnA source not found locally; sparse-cloning $CHATQNA_SUBPATH"
  log "  repo=$REPO_URL branch=$REPO_BRANCH dest=$CLONE_DIR"
  mkdir -p "$(dirname "$CLONE_DIR")"
  rm -rf "$CLONE_DIR"

  git clone --filter=blob:none --no-checkout --depth 1 \
    --single-branch --branch "$REPO_BRANCH" "$REPO_URL" "$CLONE_DIR" >&2

  git -C "$CLONE_DIR" sparse-checkout init --cone >&2
  git -C "$CLONE_DIR" sparse-checkout set "$CHATQNA_SUBPATH" >&2
  git -C "$CLONE_DIR" checkout "$REPO_BRANCH" >&2

  if ! is_chatqna_root "$CLONE_DIR/$CHATQNA_SUBPATH"; then
    log "ERROR: clone completed but $CHATQNA_SUBPATH does not look like a ChatQnA app root."
    return 1
  fi

  log "Clone complete."
  printf '%s\n' "$CLONE_DIR/$CHATQNA_SUBPATH"
}

main() {
  local root
  if [ "${CHATQNA_FORCE_CLONE:-0}" != "1" ] && root="$(detect_local_chatqna_root)"; then
    log "Found existing ChatQnA source at: $root (no clone needed)"
    printf '%s\n' "$root"
    return 0
  fi

  root="$(clone_chatqna)"
  printf '%s\n' "$root"
}

main "$@"
