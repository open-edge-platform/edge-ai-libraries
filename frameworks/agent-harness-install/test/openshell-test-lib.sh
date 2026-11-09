#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash

TEST_COUNT=0
TEST_FAILURES=0
TEST_LOG="$(mktemp)"

run_case() {
  local name="$1" rc
  shift
  TEST_COUNT=$((TEST_COUNT + 1))
  # Do not use "if function": Bash would disable errexit inside the test function.
  set +e
  (set -euo pipefail; "$@") >"$TEST_LOG" 2>&1
  rc=$?
  set -e
  if [[ "$rc" == 0 ]]; then
    printf 'ok %s - %s\n' "$TEST_COUNT" "$name"
  else
    TEST_FAILURES=$((TEST_FAILURES + 1))
    printf 'not ok %s - %s\n' "$TEST_COUNT" "$name"
    sed 's/^/# /' "$TEST_LOG"
  fi
}

finish_tests() {
  printf '1..%s\n' "$TEST_COUNT"
  [[ "$TEST_FAILURES" == 0 ]]
}

expect_failure() {
  local pattern="$1" output rc
  shift
  set +e
  output="$( (set -euo pipefail; "$@") 2>&1)"
  rc=$?
  set -e
  if [[ "$rc" == 0 ]] || ! grep -Eq -- "$pattern" <<<"$output"; then
    printf 'Expected nonzero exit matching %s; got exit %s:\n%s\n' "$pattern" "$rc" "$output" >&2
    return 1
  fi
}
