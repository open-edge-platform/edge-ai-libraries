#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Offline tests; no Docker or OpenShell installation is performed.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for lib in colors state agents openshell; do
  # shellcheck disable=SC1090
  . "$SCRIPT_DIR/scripts/lib/$lib.sh"
done

assert_fails() {
  if ("$@") >/dev/null 2>&1; then
    printf 'Expected failure: %s\n' "$*" >&2
    exit 1
  fi
}

HARNESS_RUNTIME=host
validate_runtime
HARNESS_RUNTIME=openshell
for HARNESS_AGENT in openclaw hermes; do
  validate_runtime
  [[ "$(openshell_profile_dir)" == "$(harness_state_root)/openshell/$HARNESS_AGENT" ]]
done
HARNESS_AGENT=deepagents-code
assert_fails validate_runtime
HARNESS_AGENT=openclaw
HARNESS_RUNTIME=invalid
assert_fails validate_runtime
HARNESS_RUNTIME=""
NON_INTERACTIVE=1
select_runtime
[[ "$HARNESS_RUNTIME" == host ]]

OPENSHELL_NAME=ahi-0123456789ab
OPENSHELL_GATEWAY=openshell
OPENSHELL_OWNER=0123456789abcdef0123456789abcdef
openshell() {
  printf '{"labels":{"agent-harness.owner":"0123456789abcdef0123456789abcdef"}}'
}
openshell_assert_owned
OPENSHELL_OWNER=ffffffffffffffffffffffffffffffff
assert_fails openshell_assert_owned
openshell() { return 1; }
assert_fails openshell_assert_owned
openshell() { printf '{"sandboxes":[{"name":"ahi-0123456789ab"}],"next_page_token":""}'; }
openshell_resource_exists sandbox
openshell() { printf '{"sandboxes":[],"next_page_token":""}'; }
assert_fails openshell_resource_exists sandbox
openshell() { printf '{"providers":[{"name":"ahi-0123456789ab"}],"next_page_token":""}'; }
openshell_resource_exists provider
openshell() { printf '{"sandboxes":[],"next_page_token":"more"}'; }
assert_fails openshell_resource_exists sandbox

resolve_bind_host() { printf '0.0.0.0'; }
assert_fails openshell_validate_shared_inference
resolve_bind_host() { printf '127.0.0.1'; }
HARNESS_IR_PORT=invalid
assert_fails openshell_validate_shared_inference
HARNESS_IR_PORT=8010
HARNESS_IR_CONTAINER=ir
docker() { printf '{"8000/tcp":[{"HostIp":"0.0.0.0","HostPort":"8010"}]}'; }
assert_fails openshell_validate_shared_inference

bash "$SCRIPT_DIR/install.sh" --help | grep -q -- '--runtime'
bash "$SCRIPT_DIR/uninstall.sh" --help | grep -q -- '--runtime'
assert_fails bash "$SCRIPT_DIR/install.sh" --runtime invalid --non-interactive
assert_fails bash "$SCRIPT_DIR/install.sh" --runtime openshell --harness deepagents-code --non-interactive
assert_fails bash "$SCRIPT_DIR/install.sh" connect --runtime host
printf 'OpenShell offline tests passed.\n'
