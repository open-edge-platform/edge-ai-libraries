#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
#
# Re-downloads each pinned upstream installer (dcode, Hermes) and checks its
# SHA-256 against the digest in scripts/lib/agents.sh. Needs only curl and
# sha256sum/shasum -- installs nothing. Run before a release or after bumping
# a pin; exits non-zero if any pin is stale, deleted, or mismatched.
#
# Usage: ./test/verify-pins.sh

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
agents_sh="${repo_root}/scripts/lib/agents.sh"

pin() {
  sed -n "s/^$1=\"\(.*\)\"\$/\1/p" "$agents_sh" | head -1
}

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

failures=0
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

check() {
  local label="$1" url="$2" expected="$3" actual
  if [[ -z "$expected" ]]; then
    echo "FAIL  ${label}: pin not found in ${agents_sh}"
    failures=$((failures + 1))
    return
  fi
  if ! curl -fsSL --proto '=https' --tlsv1.2 --retry 3 --max-time 60 -o "$tmp" "$url"; then
    echo "FAIL  ${label}: could not download ${url}"
    failures=$((failures + 1))
    return
  fi
  actual="$(sha256_of "$tmp")"
  if [[ "$actual" == "$expected" ]]; then
    echo "ok    ${label}: ${actual}"
  else
    echo "FAIL  ${label}: digest mismatch"
    echo "        expected ${expected}"
    echo "        actual   ${actual}"
    failures=$((failures + 1))
  fi
}

dcode_commit="$(pin DCODE_PINNED_COMMIT)"
hermes_commit="$(pin HERMES_PINNED_COMMIT)"

check "dcode installer" \
  "https://raw.githubusercontent.com/langchain-ai/deepagents/${dcode_commit}/libs/code/scripts/install.sh" \
  "$(pin DCODE_PINNED_SHA256)"
check "Hermes installer" \
  "https://raw.githubusercontent.com/NousResearch/hermes-agent/${hermes_commit}/scripts/install.sh" \
  "$(pin HERMES_PINNED_SHA256)"

if [[ "$failures" -gt 0 ]]; then
  echo "${failures} pin check(s) failed." >&2
  exit 1
fi
echo "All pins verified."
