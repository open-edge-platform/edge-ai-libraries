#!/usr/bin/env bash

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# build-gpu-generator.sh — Build the official Intel CDI GPU specs generator
#
# Builds from the gpu-v0.10.1 tag of intel-resource-drivers-for-kubernetes.
# If no local clone exists, does a shallow clone automatically.
#
# Usage:
#   ./build-gpu-generator.sh                          # auto-clone or use existing
#   ./build-gpu-generator.sh --source /path/to/repo   # use specific local clone

set -euo pipefail

export PATH=$PATH:/usr/local/go/bin

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
OUTPUT="$SCRIPT_DIR/intel-cdi-specs-generator-gpu"
TAG="gpu-v0.10.1"
UPSTREAM_URL="https://github.com/intel/intel-resource-drivers-for-kubernetes.git"
SOURCE_DIR=""
CLEANUP_SOURCE=false

# Pin the current default tag to its immutable commit SHA for security.
# Only enforced when TAG matches the default and COMMIT is not explicitly provided.
DEFAULT_TAG="gpu-v0.10.1"
DEFAULT_COMMIT="5ed70dac2c31c020bdf82fc5b913e807e7127436"
EXPECTED_COMMIT=""

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Build the official Intel CDI GPU specs generator from source (tag: ${TAG}).

Options:
  --source DIR      Path to existing intel-resource-drivers-for-kubernetes clone
  --output FILE     Output binary path (default: ${OUTPUT})
  --tag TAG         Git tag to build from (default: ${TAG})
  --commit SHA      Expected commit SHA for the tag (enables independent verification)
  -h, --help        Show this help

If --source is not given, the script looks for the repo at common locations.
If not found, it does a shallow clone into /tmp (cleaned up after build).

Verification:
  When TAG matches the default (${DEFAULT_TAG}), the checkout is verified against
  the pinned commit ${DEFAULT_COMMIT}. To override with a custom tag, use --commit
  to provide the expected commit SHA for independent verification.

Output:
  ${OUTPUT}

Requirements:
  - Go 1.22+ (go version)
  - git
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) SOURCE_DIR="$2"; shift 2 ;;
    --output) OUTPUT="$2"; shift 2 ;;
    --tag)    TAG="$2"; shift 2 ;;
    --commit) EXPECTED_COMMIT="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# Set default expected commit if using the default tag and no explicit override
if [[ "$TAG" == "$DEFAULT_TAG" && -z "$EXPECTED_COMMIT" ]]; then
  EXPECTED_COMMIT="$DEFAULT_COMMIT"
fi

if ! command -v go &>/dev/null; then
  echo "ERROR: Go compiler not found. Install Go 1.22+ from https://go.dev/dl/" >&2
  exit 1
fi

GO_VERSION=$(go version | grep -oP 'go\K[0-9]+\.[0-9]+')
if awk "BEGIN{exit !($GO_VERSION < 1.22)}"; then
  echo "ERROR: Go 1.22+ required, found go${GO_VERSION}" >&2
  exit 1
fi

# --- Locate or clone the source repo ------------------------------------------

if [[ -n "$SOURCE_DIR" ]]; then
  if [[ ! -d "$SOURCE_DIR/.git" ]]; then
    echo "ERROR: Not a git repo: $SOURCE_DIR" >&2
    exit 1
  fi
elif [[ -d "${SCRIPT_DIR}/../../../intel-resource-drivers-for-kubernetes/.git" ]]; then
  SOURCE_DIR="${SCRIPT_DIR}/../../../intel-resource-drivers-for-kubernetes"
else
  SOURCE_DIR=$(mktemp -d)/intel-resource-drivers-for-kubernetes
  CLEANUP_SOURCE=true
  echo "No local clone found. Shallow-cloning tag ${TAG}..."
  echo "  ${UPSTREAM_URL} -> ${SOURCE_DIR}"
  echo ""
  git clone --depth 1 --branch "$TAG" "$UPSTREAM_URL" "$SOURCE_DIR"

  # After cloning, verify the commit if a pin is set
  if [[ -n "$EXPECTED_COMMIT" ]]; then
    cd "$SOURCE_DIR"
    ACTUAL_COMMIT=$(git rev-parse HEAD)
    if [[ "$ACTUAL_COMMIT" != "$EXPECTED_COMMIT" ]]; then
      echo "ERROR: Commit verification failed for tag ${TAG}" >&2
      echo "  expected: $EXPECTED_COMMIT" >&2
      echo "  got:      $ACTUAL_COMMIT" >&2
      exit 1
    fi
    echo "✓ Tag ${TAG} verified against commit ${EXPECTED_COMMIT}" >&2
    cd - > /dev/null
  fi
fi

echo "Building intel-cdi-specs-generator-gpu from tag: ${TAG}"
echo "Source: ${SOURCE_DIR}"
echo "Output: ${OUTPUT}"
echo ""

cd "$SOURCE_DIR"

# If using an existing repo, save state to restore later
if ! $CLEANUP_SOURCE; then
  PREV_HEAD=$(git rev-parse HEAD)
  PREV_REF=$(git symbolic-ref -q HEAD 2>/dev/null || echo "detached")

  echo "Fetching tag ${TAG}..."
  git fetch origin "refs/tags/${TAG}:refs/tags/${TAG}" 2>/dev/null || \
    git fetch upstream "refs/tags/${TAG}:refs/tags/${TAG}" 2>/dev/null || true

  echo "Checking out ${TAG}..."
  git checkout "$TAG" 2>/dev/null

  # Verify commit if a pin is set
  if [[ -n "$EXPECTED_COMMIT" ]]; then
    ACTUAL_COMMIT=$(git rev-parse HEAD)
    if [[ "$ACTUAL_COMMIT" != "$EXPECTED_COMMIT" ]]; then
      echo "ERROR: Commit verification failed for tag ${TAG}" >&2
      echo "  expected: $EXPECTED_COMMIT" >&2
      echo "  got:      $ACTUAL_COMMIT" >&2
      # Restore previous state before aborting
      if [[ "$PREV_REF" == "detached" ]]; then
        git checkout "$PREV_HEAD" 2>/dev/null
      else
        git checkout "${PREV_REF#refs/heads/}" 2>/dev/null
      fi
      exit 1
    fi
    echo "✓ Tag ${TAG} verified against commit ${EXPECTED_COMMIT}" >&2
  fi
fi

echo "Syncing vendor..."
go mod vendor 2>&1 | tail -3

echo "Building..."
GOOS=linux GOARCH=amd64 \
  go build -a -ldflags "-s -w" \
  -mod vendor -o "$OUTPUT" ./cmd/cdi-specs-generator

# --- Restore / cleanup --------------------------------------------------------

if $CLEANUP_SOURCE; then
  rm -rf "$(dirname "$SOURCE_DIR")"
else
  echo ""
  echo "Restoring previous checkout..."
  if [[ "$PREV_REF" == "detached" ]]; then
    git checkout "$PREV_HEAD" 2>/dev/null
  else
    git checkout "${PREV_REF#refs/heads/}" 2>/dev/null
  fi
fi

echo ""
echo "Built: ${OUTPUT}"
echo "Size: $(du -h "$OUTPUT" | cut -f1)"
