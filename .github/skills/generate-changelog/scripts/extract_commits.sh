#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# extract_commits.sh
# Usage: bash extract_commits.sh <repo_or_folder_path> <base_branch> <target_branch> [scope_path]
#
# Outputs one line per non-merge commit between base_branch and target_branch:
#   <short_hash> <subject>
# When a folder path is provided, only commits touching that folder are returned.
# If scope_path is omitted and repo_or_folder_path is a repository subfolder,
# that subfolder is used as the scope automatically. If repo_or_folder_path is
# the repository root and scope_path is omitted, the entire repository is used.
#
# Exit codes:
#   0 - success (may output zero lines if no commits differ)
#   1 - missing arguments
#   2 - repo path not a git repository
#   3 - one or both branch names not found
#   4 - scope path not found inside the repository

set -euo pipefail

INPUT_PATH="${1:-}"
BASE_BRANCH="${2:-}"
TARGET_BRANCH="${3:-}"
SCOPE_INPUT="${4:-}"

if [[ -z "$INPUT_PATH" || -z "$BASE_BRANCH" || -z "$TARGET_BRANCH" ]]; then
  echo "Usage: $0 <repo_or_folder_path> <base_branch> <target_branch> [scope_path]" >&2
  exit 1
fi

# Validate git repo
if ! git -C "$INPUT_PATH" rev-parse --git-dir > /dev/null 2>&1; then
  echo "ERROR: '$INPUT_PATH' is not a git repository or repository subfolder." >&2
  exit 2
fi

REPO_ROOT=$(git -C "$INPUT_PATH" rev-parse --show-toplevel)
INPUT_PATH_ABS=$(realpath "$INPUT_PATH")
REPO_ROOT_ABS=$(realpath "$REPO_ROOT")

resolve_scope_path() {
  local repo_root="$1"
  local input_path_abs="$2"
  local scope_input="$3"
  local candidate=""

  if [[ -n "$scope_input" ]]; then
    if [[ -d "$scope_input" || -f "$scope_input" ]]; then
      candidate=$(realpath "$scope_input")
    else
      candidate=$(realpath -m "$repo_root/$scope_input")
    fi
  elif [[ "$input_path_abs" != "$repo_root" ]]; then
    candidate="$input_path_abs"
  else
    echo ""
    return 0
  fi

  case "$candidate" in
    "$repo_root"/*|"$repo_root")
      ;;
    *)
      return 1
      ;;
  esac

  if [[ ! -e "$candidate" ]]; then
    return 1
  fi

  if [[ "$candidate" == "$repo_root" ]]; then
    echo ""
  else
    realpath --relative-to="$repo_root" "$candidate"
  fi
}

if ! SCOPE_PATH=$(resolve_scope_path "$REPO_ROOT_ABS" "$INPUT_PATH_ABS" "$SCOPE_INPUT"); then
  echo "ERROR: Scope path '${SCOPE_INPUT:-$INPUT_PATH}' was not found inside repository '$REPO_ROOT_ABS'." >&2
  exit 4
fi

# Fetch so we have up-to-date remote refs and tags (non-fatal if offline)
git -C "$REPO_ROOT" fetch --all --tags --quiet 2>/dev/null || true

# Resolve branches (local or remote)
resolve_ref() {
  local repo="$1"
  local branch="$2"
  # Try as-is, then origin/<branch>
  if git -C "$repo" rev-parse --verify "$branch" > /dev/null 2>&1; then
    echo "$branch"
  elif git -C "$repo" rev-parse --verify "origin/$branch" > /dev/null 2>&1; then
    echo "origin/$branch"
  else
    echo ""
  fi
}

BASE_REF=$(resolve_ref "$REPO_ROOT" "$BASE_BRANCH")
TARGET_REF=$(resolve_ref "$REPO_ROOT" "$TARGET_BRANCH")

if [[ -z "$BASE_REF" ]]; then
  echo "ERROR: Branch '$BASE_BRANCH' not found. Run 'git branch -a' to list branches." >&2
  exit 3
fi

if [[ -z "$TARGET_REF" ]]; then
  echo "ERROR: Branch '$TARGET_BRANCH' not found. Run 'git branch -a' to list branches." >&2
  exit 3
fi

# Output commits: <short_hash> <subject>
# --no-merges skips merge commits; format keeps it machine-readable
git_cmd=(
  git -C "$REPO_ROOT" log
  --no-merges
  --pretty=format:"%h %s"
  "${BASE_REF}..${TARGET_REF}"
)

if [[ -n "$SCOPE_PATH" ]]; then
  git_cmd+=(-- "$SCOPE_PATH")
fi

"${git_cmd[@]}"
