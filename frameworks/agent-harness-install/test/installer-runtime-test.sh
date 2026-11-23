#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$SCRIPT_DIR/scripts/install.sh"
. "$SCRIPT_DIR/test/openshell-test-lib.sh"
TEST_ROOT="$(mktemp -d)"
trap 'rm -f -- "$TEST_LOG"; rm -rf -- "$TEST_ROOT"' EXIT

fixture() {
  export HOME TMPDIR
  HOME="$(mktemp -d "$TEST_ROOT/home.XXXXXX")"
  TMPDIR="$HOME/tmp"
  mkdir -p "$TMPDIR"
  HARNESS_STATE_DIRNAME=.harness-test
  HARNESS_MODELS_DIR="$HOME/models"
  HARNESS_SHIM_DIR="$HOME/bin"
  ACTIONS="$HOME/actions"
  : >"$ACTIONS"
  # Never allow these tests to fall through to real host lifecycle commands.
  docker() { printf 'unexpected docker: %s\n' "$*" >&2; return 98; }
  sudo() { printf 'unexpected sudo: %s\n' "$*" >&2; return 98; }
  openshell() { printf 'unexpected openshell: %s\n' "$*" >&2; return 98; }
}

profile_deferred_path() {
  fixture
  SHELL=/bin/bash
  ensure_local_bin_in_profile
  ensure_local_bin_in_profile
  [[ "$(grep -c '^export PATH=' "$HOME/.bashrc")" == 1 ]]
  grep -Fq '$PATH' "$HOME/.bashrc"
  local result
  result="$(PATH=/usr/bin:/bin bash --noprofile --norc -c '. "$HOME/.bashrc"; printf "%s" "$PATH"')"
  [[ "$result" == "$HARNESS_SHIM_DIR:/usr/bin:/bin" ]]
}

nvm_runtime_source() {
  fixture
  NVM_DIR="$HOME/nvm"
  ensure_nvm_loaded
  mkdir -p "$NVM_DIR"
  printf 'export HARNESS_NVM_FIXTURE=loaded\n' >"$NVM_DIR/nvm.sh"
  ensure_nvm_loaded
  [[ "$HARNESS_NVM_FIXTURE" == loaded ]]
}

bootstrap_cleanup() {
  local payload_status="$1"
  fixture
  local repo="$HOME/payload" standalone="$HOME/standalone" status
  mkdir -p "$repo/scripts/lib" "$standalone"
  printf '#!/bin/bash\nprintf "%%s" "$PWD" >"$HOME/payload-ran"\nexit %s\n' "$payload_status" >"$repo/scripts/install.sh"
  git -C "$repo" init -q
  git -C "$repo" add .
  git -C "$repo" -c user.name=Fixture -c user.email=fixture@example.invalid commit -qm fixture
  cp "$SCRIPT_DIR/install.sh" "$standalone/install.sh"
  # A local repository and disposable TMPDIR exercise the real bootstrap without network/install.
  set +e
  HARNESS_INSTALL_REPO="$repo" HARNESS_INSTALL_REF=HEAD \
    bash "$standalone/install.sh" >"$HOME/bootstrap.log" 2>&1
  status=$?
  set -e
  [[ "$status" == "$payload_status" ]]
  [[ -f "$HOME/payload-ran" ]]
  [[ -z "$(find "$TMPDIR" -mindepth 1 -print -quit)" ]]
}

bind_guard() {
  local component="$1" resolution="$2"
  fixture
  ensure_inference_router_image() { :; }
  ensure_backend_network() { :; }
  write_inference_router_config() { :; }
  ensure_ovms_config() { :; }
  intel_gpu_docker_device_args() { :; }
  intel_gpu_docker_group_add_args() { :; }
  docker_proxy_env_args_into() { :; }
  wait_for_inference_router_ready() { :; }
  HARNESS_LLM_ROUTER_ENDPOINT=""
  HARNESS_OVMS_EXTRA_ARGS=""
  docker() {
    case "$1" in
      inspect) return 1 ;;
      run) printf '%s\n' "$@" >>"$ACTIONS" ;;
      *) return 98 ;;
    esac
  }
  resolve_bind_host() {
    case "$resolution" in
      failure) printf '127.0.0.1'; return 1 ;;
      empty) return 0 ;;
      valid) printf '127.0.0.1' ;;
    esac
  }
  local target=ensure_inference_router
  [[ "$component" != ovms ]] || target=ensure_openvino_model_server
  if [[ "$resolution" == valid ]]; then
    "$target"
    grep -Eq '^127\.0\.0\.1:[0-9]+:8000$' "$ACTIONS"
  else
    expect_failure 'Could not resolve the address' "$target"
    [[ ! -s "$ACTIONS" ]]
  fi
}

port_guard() {
  local port="$1"
  fixture
  HARNESS_IR_PORT="$port"
  resolve_bind_host() { printf '127.0.0.1'; }
  docker() { printf 'docker reached\n' >>"$ACTIONS"; return 98; }
  expect_failure 'HARNESS_IR_PORT must be between' openshell_validate_shared_inference
  expect_failure 'HARNESS_IR_PORT must be between' _openshell_ensure_shared_inference
  [[ ! -s "$ACTIONS" ]]
  local output target
  for target in openshell_validate_shared_inference _openshell_ensure_shared_inference; do
    output="$( ("$target") 2>&1)" || true
    if grep -Eq 'value too great for base|syntax error.*arithmetic|expression recursion' <<<"$output"; then
      return 1
    fi
  done
}

valid_port_guard() {
  local port="$1"
  fixture
  HARNESS_IR_PORT="$port"
  resolve_bind_host() { printf '127.0.0.1'; }
  openshell_validate_recorded_ir_port() { :; }
  docker() { printf '%s\n' "$HARNESS_IR_PORT" >>"$ACTIONS"; printf 'fixture reached Docker\n' >&2; return 98; }
  expect_failure 'fixture reached Docker' openshell_validate_shared_inference
  expect_failure 'fixture reached Docker' _openshell_ensure_shared_inference
  [[ "$(cat "$ACTIONS")" == "$port"$'\n'"$port" ]]
}

config_publication() {
  local operation="$1" failure="$2"
  fixture
  local config="$HOME/config.json" before="$HOME/before" status
  printf '%s\n' '{"model_config_list":[{"config":{"name":"keep","base_path":"/models/keep"}}]}' >"$config"
  cp "$config" "$before"
  node() {
    if [[ "$failure" == generation ]]; then
      printf 'partial output'
      return 73
    fi
    command node "$@"
  }
  mv() {
    if [[ "$failure" == publication ]]; then return 74; fi
    command mv "$@"
  }
  set +e
  (
    set -euo pipefail
    if [[ "$operation" == add ]]; then
      _add_model_config_entry_locked "$config" added /models/added
    else
      _remove_model_from_ovms_config_locked "$config" keep
    fi
  )
  status=$?
  set -e
  if [[ "$failure" == none ]]; then
    [[ "$status" == 0 ]]
    command node -e '
      const assert = require("node:assert/strict"), fs = require("node:fs");
      const data = JSON.parse(fs.readFileSync(process.argv[1]));
      assert.equal(data.model_config_list.length, process.argv[2] === "add" ? 2 : 0);
    ' "$config" "$operation"
  else
    [[ "$status" != 0 ]]
    cmp "$config" "$before"
  fi
  [[ -z "$(find "$TMPDIR" -mindepth 1 -print -quit)" ]]
}

npm_version_fallback() {
  local npm_mode="$1"
  fixture
  installed_npm_global_version() { return 1; }
  command_exists() { [[ "$npm_mode" != absent ]]; }
  npm() {
    [[ "$1" == --version ]] || return 98
    [[ "$npm_mode" != failed ]] || return 72
    printf '11.16.0'
  }
  spin() { printf '%s\n' "$@" >"$ACTIONS"; }
  install_openclaw
  grep -Fxq 'npm install -g openclaw' "$ACTIONS"
  if [[ "$npm_mode" == valid ]]; then
    grep -Fxq -- '--allow-scripts=openclaw' "$ACTIONS"
  else
    ! grep -Fq -- '--allow-scripts=' "$ACTIONS"
  fi
}

hermes_stage() {
  local failure="$1"
  fixture
  local bin="$HOME/mock-bin" config="$HOME/hermes/config.yaml"
  mkdir -p "$bin" "$(dirname "$config")"
  printf 'user_setting: keep\n' >"$config"
  export HERMES_HOME="$HOME/hermes" HARNESS_AGENT=hermes
  export HARNESS_SANDBOX_MODEL=test-model HARNESS_SANDBOX_ENDPOINT=http://host.openshell.internal:8010/v1
  export HARNESS_MODEL_CONFIG_SCRIPT="$HOME/configure.mjs"
  export HARNESS_STAGE_FAILURE="$failure" HARNESS_STAGE_PARENT="$HERMES_HOME"
  cat >"$HARNESS_MODEL_CONFIG_SCRIPT" <<'JS'
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
assert.equal(process.env.HERMES_HOME, process.env.HARNESS_STAGE_PARENT);
const file = process.env.HARNESS_HERMES_CONFIG_FILE;
assert.notEqual(file, path.join(process.env.HERMES_HOME, "config.yaml"));
fs.appendFileSync(file, "staged: true\n");
if (process.env.HARNESS_STAGE_FAILURE === "yes") throw Error("injected staging failure");
const dir = process.env.HARNESS_MODEL_CONFIG_STAGE_DIR;
for (const name of [".harness-local-defaults.json", ".harness-model.pending.json", ".harness-model.json"])
  fs.writeFileSync(path.join(dir, name), JSON.stringify({applied: name === ".harness-model.json"}));
JS
  cat >"$bin/sleep" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
[[ "$*" == infinity ]]
[[ "$HERMES_HOME" == "$HARNESS_STAGE_PARENT" ]]
[[ -z "${HARNESS_HERMES_CONFIG_FILE:-}${HARNESS_MODEL_CONFIG_STAGE_DIR:-}" ]]
printf 'parent environment preserved\n' >"$HOME/parent-checked"
SH
  chmod 700 "$bin/sleep"
  export PATH="$bin:$PATH"
  if [[ "$failure" == yes ]]; then
    expect_failure 'injected staging failure' bash "$SCRIPT_DIR/openshell/agent-start.sh"
    cmp "$config" <(printf 'user_setting: keep\n')
    [[ ! -e "$HOME/.harness-model.json" && ! -e "$HOME/parent-checked" ]]
  else
    bash "$SCRIPT_DIR/openshell/agent-start.sh"
    grep -Fxq 'staged: true' "$config"
    [[ -f "$HOME/parent-checked" ]]
  fi
  [[ -z "$(find "$HOME" -name '.harness-config.*' -o -name '.harness-config-state.*')" ]]
}

hermes_child_retry() {
  fixture
  local installer="$HOME/installer.sh"
  cat >"$installer" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
[[ "$#" == 4 && "$1" == --skip-setup && "$2" == --non-interactive && "$3" == --commit && -n "$4" ]] || exit 98
if [[ ! -f "$HOME/retried" ]]; then
  touch "$HOME/retried"
  printf 'TLS connection reset\n'
  exit 73
fi
printf 'fixture install completed\n'
touch "$HOME/installed"
SH
  fetch_and_verify() { cp "$installer" "$2"; }
  assert_shell_script() { :; }
  sleep() { :; }
  unset HERMES_INSTALL_URL HERMES_INSTALL_SHA256
  install_hermes
  [[ -f "$HOME/retried" && -f "$HOME/installed" ]]
  [[ -z "$(find "$TMPDIR" -mindepth 1 -print -quit)" ]]
}

proxy_env_args_without_no_proxy() {
  fixture
  unset HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy
  HTTP_PROXY=http://proxy.invalid:3128 HTTPS_PROXY=http://proxy.invalid:3128
  local -a args=()
  docker_proxy_env_args_into args
  [[ "${args[*]}" == '-e HTTP_PROXY=http://proxy.invalid:3128 -e HTTPS_PROXY=http://proxy.invalid:3128' ]]
  unset HTTP_PROXY HTTPS_PROXY
  args=()
  docker_proxy_env_args_into args
  [[ "${#args[@]}" == 0 ]]
}

ovms_models_readable_by_other_uid() {
  fixture
  mkdir -p "$HARNESS_MODELS_DIR/org/model"
  printf '{}' >"$HARNESS_MODELS_DIR/org/model/generation_config.json"
  chmod 700 "$HARNESS_MODELS_DIR" "$HARNESS_MODELS_DIR/org" "$HARNESS_MODELS_DIR/org/model"
  chmod 600 "$HARNESS_MODELS_DIR/org/model/generation_config.json"
  # Filesystems that ignore chmod (e.g. NTFS under Git Bash) cannot exercise this.
  [[ "$(stat -c %a "$HARNESS_MODELS_DIR")" == 700 ]] || return 0
  ensure_ovms_models_readable
  [[ "$(stat -c %a "$HARNESS_MODELS_DIR")" == 705 ]]
  [[ "$(stat -c %a "$HARNESS_MODELS_DIR/org/model")" == 705 ]]
  [[ "$(stat -c %a "$HARNESS_MODELS_DIR/org/model/generation_config.json")" == 604 ]]
  rm -rf -- "$HARNESS_MODELS_DIR"
  ensure_ovms_models_readable
}

ovms_models_readable_skips_home() {
  fixture
  HARNESS_MODELS_DIR="$HOME"
  printf 'secret' >"$HOME/secret"
  chmod 600 "$HOME/secret"
  [[ "$(stat -c %a "$HOME/secret")" == 600 ]] || return 0
  ensure_ovms_models_readable 2>/dev/null
  [[ "$(stat -c %a "$HOME/secret")" == 600 ]]
}

node_loaded_from_nvm_for_models() {
  fixture
  NVM_DIR="$HOME/nvm"
  mkdir -p "$NVM_DIR/bin"
  printf '#!/bin/sh\n' >"$NVM_DIR/bin/node"
  chmod +x "$NVM_DIR/bin/node"
  printf 'export PATH="%s/bin:$PATH"\n' "$NVM_DIR" >"$NVM_DIR/nvm.sh"
  ensure_node_on_path
  [[ "$(command -v node)" == "$NVM_DIR/bin/node" ]]
}

unregistered_model_listing() {
  fixture
  local registry="$HOME/registry.json"
  mkdir -p "$HARNESS_MODELS_DIR"
  printf '%s\n' '{"fixture-model":{"hub":"huggingface"}}' >"$registry"
  unregistered_downloads_file() { printf '%s' "$registry"; }
  local listing
  listing="$(list_exported_models)"
  [[ "$listing" == $'  fixture-model\t(hub: huggingface, not served by OVMS)' ]]
}

printf 'TAP version 13\n'
run_case 'proxy env args do not abort under set -e when no_proxy is unset' proxy_env_args_without_no_proxy
run_case 'OVMS model files are made readable by the container uid and a missing dir is tolerated' ovms_models_readable_by_other_uid
run_case 'OVMS permission fix refuses a models dir that is the home directory' ovms_models_readable_skips_home
run_case 'models commands load nvm Node into PATH' node_loaded_from_nvm_for_models
run_case 'generated Bash PATH expands in the future shell and remains idempotent' profile_deferred_path
run_case 'nvm sources a runtime fixture and tolerates its absence' nvm_runtime_source
run_case 'bootstrap subshell cleans temporary clone after successful payload' bootstrap_cleanup 0
run_case 'bootstrap trap cleans and preserves payload failure' bootstrap_cleanup 17
for component in ir ovms; do
  for resolution in failure empty valid; do
    run_case "$component binding guard handles $resolution resolution" bind_guard "$component" "$resolution"
  done
done
for port in invalid 0 65536 08010 01000 00001 999999999999999999999999999999999999; do
  run_case "both OpenShell port guards reject $port before Docker access" port_guard "$port"
done
for port in 1 1000 8010 65535; do
  run_case "both OpenShell port guards accept canonical decimal $port" valid_port_guard "$port"
done
for operation in add remove; do
  for failure in generation publication none; do
    run_case "$operation config handles $failure failure and cleans temporary files" config_publication "$operation" "$failure"
  done
done
for npm_mode in absent failed valid; do
  run_case "OpenClaw install handles $npm_mode npm version query" npm_version_fallback "$npm_mode"
done
run_case 'Hermes staging preserves parent environment and cleans staged files' hermes_stage no
run_case 'Hermes staging failure preserves config and cleans staged files' hermes_stage yes
run_case 'Hermes child Bash preserves installer arguments and retries a transient failure' hermes_child_retry
run_case 'unregistered model listing executes its literal JavaScript with the registry argument' unregistered_model_listing
finish_tests
