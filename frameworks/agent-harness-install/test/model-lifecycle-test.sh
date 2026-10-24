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
  export HOME
  HOME="$(mktemp -d "$TEST_ROOT/home.XXXXXX")"
  HARNESS_STATE_DIRNAME=.harness-test
  HARNESS_RUNTIME=openshell
  HARNESS_AGENT=openclaw
  HARNESS_HF_MODEL=org/new-model
  HARNESS_LLM_MODEL=new-model
  HARNESS_LLM_ROUTER_ENDPOINT=""
  HARNESS_MODEL_HUB=openvino
  HARNESS_MODEL_HUB_WAS_SET=""
  HARNESS_MODEL_CONFIG_JSON=""
  HARNESS_MODEL_TYPE=llm
  HARNESS_MODEL_PRECISION=int8
  HARNESS_MODEL_DEVICE=CPU
  HARNESS_MODEL_DOWNLOAD_REVISION=""
  HARNESS_HF_MODEL_REVISION=""
  HARNESS_OVMS_EXPORTER=docker-pull
  HARNESS_OVMS_EXPORTER_WAS_SET=""
  HARNESS_MODELS_DIR="$HOME/models"
  HARNESS_BIND_HOST=127.0.0.1
  OPENSHELL_MODEL_REQUESTED=1
  DELAY_STARTUP=""
  ACTIONS="$HOME/actions"
  : >"$ACTIONS"
}
profiles() {
  local agent dir
  for agent in openclaw deepagents-code hermes; do
    dir="$(HARNESS_AGENT="$agent" openshell_profile_dir)"
    mkdir -p "$dir"
    atomic_write_file "$dir/profile.json" \
      "{\"owner\":\"0123456789abcdef0123456789abcdef\",\"name\":\"ahi-0123456789ab\",\"gateway\":\"openshell\",\"agent\":\"$agent\",\"model\":\"old-model\"}"
    atomic_write_file "$dir/provider.json" \
      "{\"endpoints\":[{\"host\":\"host.openshell.internal\",\"port\":$HARNESS_IR_PORT}]}"
    mkdir -p "$HOME/sandboxes/$agent/.openclaw"
    printf '%s\n' '{"models":{"providers":{"ovms":{"baseUrl":"http://host.openshell.internal:8010/v1","models":[{"id":"old-model","name":"old-model","contextWindow":32768}]}}},"agents":{"defaults":{"model":{"primary":"ovms/old-model"},"workspace":"/sandbox"}},"gateway":{"auth":{"token":"preserved-token"}},"userSetting":true}' \
      >"$HOME/sandboxes/$agent/.openclaw/openclaw.json"
    printf 'history must survive\n' >"$HOME/sandboxes/$agent/history"
  done
}
mock_sandboxes() {
  PHASE=Ready
  openshell_resource_exists() { return 0; }
  openshell_assert_owned() { :; }
  openshell_agent_exec() {
    if [[ "$1" == /usr/bin/test ]]; then return 0; fi
    shift
    HOME="$HOME/sandboxes/$HARNESS_AGENT" node "$@"
  }
  openshell() {
    case "$1 ${2:-}" in
      'sandbox stop') PHASE=Stopped; printf 'stop %s\n' "$HARNESS_AGENT" >>"$ACTIONS" ;;
      'sandbox start')
        apply_startup_model() {
          if [[ "$HARNESS_AGENT" == openclaw ]]; then
            HOME="$HOME/sandboxes/$HARNESS_AGENT" node "$SCRIPT_DIR/openshell/model-config.mjs" \
              "$HARNESS_AGENT" "$HARNESS_LLM_MODEL" "http://host.openshell.internal:${HARNESS_IR_PORT}/v1"
          else
            HOME="$HOME/sandboxes/$HARNESS_AGENT" node -e '
              const fs = require("node:fs"), file = `${process.env.HOME}/.harness-model.json`;
              const selection = JSON.parse(fs.readFileSync(file, "utf8"));
              selection.applied = true;
              fs.writeFileSync(file, JSON.stringify(selection));
            '
          fi
        }
        if [[ -n "$DELAY_STARTUP" ]]; then
          (sleep 0.1; apply_startup_model) &
        else
          apply_startup_model
        fi
        PHASE=Ready
        printf 'start %s\n' "$HARNESS_AGENT" >>"$ACTIONS" ;;
      'sandbox get') printf '{"phase":"%s"}\n' "$PHASE" ;;
      *) printf 'Unexpected OpenShell call: %s\n' "$*" >&2; return 1 ;;
    esac
  }
}
mock_inference() {
  docker() { printf '%s\n' "$HARNESS_IR_CONTAINER" "$HARNESS_OVMS_CONTAINER"; }
  ensure_inference_backend() { printf 'backend %s\n' "$HARNESS_HF_MODEL" >>"$ACTIONS"; }
  openshell_validate_shared_inference() { :; }
  openshell_validate_managed_backend() { :; }
}
switch_both() {
  fixture
  profiles
  mock_sandboxes
  mock_inference
  openshell_ensure_shared_inference
  local agent
  for agent in openclaw deepagents-code hermes; do
    [[ "$(HARNESS_AGENT="$agent" openshell_load_profile; printf '%s' "$OPENSHELL_MODEL")" == new-model ]]
    node - "$HOME/sandboxes/$agent/.harness-model.json" <<'JS'
const assert = require("node:assert/strict"), fs = require("node:fs");
assert.equal(JSON.parse(fs.readFileSync(process.argv[2])).model, "new-model");
JS
    [[ "$(cat "$HOME/sandboxes/$agent/history")" == 'history must survive' ]]
    grep -Fxq "start $agent" "$ACTIONS"
  done
  node - "$HOME/sandboxes/openclaw/.openclaw/openclaw.json" <<'JS'
const assert = require("node:assert/strict"), fs = require("node:fs");
const c = JSON.parse(fs.readFileSync(process.argv[2]));
assert.equal(c.agents.defaults.model.primary, "ovms/new-model");
assert.equal(c.models.providers.ovms.models[0].id, "new-model");
assert.equal(c.gateway.auth.token, "preserved-token");
assert.equal(c.userSetting, true);
JS
  [[ ! -f "$(harness_state_root)/openshell-model-pending.json" ]]
  [[ "$(cat "$(harness_state_root)/openshell-model")" == new-model ]]
}
source_roundtrip() {
  fixture
  HARNESS_MODEL_HUB=huggingface
  HARNESS_OVMS_EXPORTER=model-download
  HARNESS_HF_MODEL_REVISION=pinned
  HARNESS_MODEL_DOWNLOAD_REVISION=download-pinned
  HARNESS_MODEL_CONFIG_JSON=$'{\n  "task": "text-generation"\n}'
  atomic_write_file "$(ensure_state_dir)/openshell-model-source.json" "$(openshell_model_source)"
  HARNESS_HF_MODEL=""; HARNESS_LLM_MODEL=""
  HARNESS_MODEL_HUB=openvino; HARNESS_OVMS_EXPORTER=docker-pull
  openshell_apply_model_defaults
  [[ "$HARNESS_HF_MODEL" == org/new-model && "$HARNESS_LLM_MODEL" == new-model ]]
  [[ "$HARNESS_OVMS_EXPORTER" == model-download && "$HARNESS_MODEL_HUB" == huggingface ]]
  [[ "$HARNESS_HF_MODEL_REVISION" == pinned && "$HARNESS_MODEL_DOWNLOAD_REVISION" == download-pinned ]]
  [[ "$HARNESS_MODEL_CONFIG_JSON" == '{"task":"text-generation"}' ]]
}
delayed_startup() {
  fixture
  profiles
  mock_sandboxes
  mock_inference
  DELAY_STARTUP=1
  openshell_ensure_shared_inference
  [[ ! -f "$(harness_state_root)/openshell-model-pending.json" ]]
  grep -Fxq 'start hermes' "$ACTIONS"
}
select_served_model() {
  fixture
  mkdir -p "$HARNESS_MODELS_DIR/old-model" "$HARNESS_MODELS_DIR/new-model"
  printf 'old weights\n' >"$HARNESS_MODELS_DIR/old-model/weights"
  printf '{"model_config_list":[{"config":{"name":"old-model","base_path":"old-model"}},{"config":{"name":"new-model","base_path":"new-model"}}]}' \
    >"$HARNESS_MODELS_DIR/config.json"
  with_state_lock ovms-config _select_ovms_model_locked new-model
  [[ "$(ovms_sole_registered_model_name)" == new-model ]]
  [[ "$(cat "$HARNESS_MODELS_DIR/old-model/weights")" == 'old weights' ]]
  cp "$HARNESS_MODELS_DIR/config.json" "$HOME/before"
  expect_failure 'existing configuration was preserved' _select_ovms_model_locked absent
  cmp "$HOME/before" "$HARNESS_MODELS_DIR/config.json"
  : >"$HARNESS_MODELS_DIR/old-model/graph.pbtxt"
  export_model_to_openvino org/old-model old-model
  with_state_lock ovms-config _select_ovms_model_locked old-model
  [[ "$(ovms_sole_registered_model_name)" == old-model ]]
  [[ -d "$HARNESS_MODELS_DIR/new-model" ]]
}
qwen_alias() {
  fixture
  HARNESS_HF_MODEL=Qwen3.5-9B-int8-ov
  HARNESS_LLM_MODEL=""
  openshell_apply_model_defaults
  [[ "$HARNESS_HF_MODEL" == OpenVINO/Qwen3.5-9B-int8-ov ]]
  [[ "$HARNESS_OVMS_EXPORTER" == hf-snapshot && "$HARNESS_LLM_MODEL" == Qwen3.5-9B-int8-ov ]]
}
external_model_id_is_preserved() {
  fixture
  HARNESS_LLM_ROUTER_ENDPOINT=https://router.example/v1
  HARNESS_HF_MODEL=org/llama3.1:8b
  HARNESS_LLM_MODEL=""
  openshell_apply_model_defaults
  [[ "$HARNESS_LLM_MODEL" == org/llama3.1:8b ]]
  node - "$(openshell_model_source)" <<'JS'
const assert = require("node:assert/strict");
assert.equal(JSON.parse(process.argv[2]).model, "org/llama3.1:8b");
JS
}
ir_port_change_is_rejected_before_backend_update() {
  fixture
  profiles
  mock_inference
  HARNESS_IR_PORT=8011
  expect_failure 'HARNESS_IR_PORT changed from 8010' openshell_ensure_shared_inference
  [[ ! -s "$ACTIONS" ]]
}
model_sync_locks_agents_without_sandboxes() {
  fixture
  profiles
  mock_inference
  openshell_resource_exists() { return 1; }
  with_state_lock() {
    local lock_name="$1"
    shift
    printf 'lock %s\n' "$lock_name" >>"$ACTIONS"
    "$@"
    printf 'unlock %s\n' "$lock_name" >>"$ACTIONS"
  }
  openshell_ensure_shared_inference
  cmp "$ACTIONS" <(printf 'lock openshell-inference\nbackend org/new-model\nlock openshell-openclaw\nunlock openshell-openclaw\nlock openshell-deepagents-code\nunlock openshell-deepagents-code\nlock openshell-hermes\nunlock openshell-hermes\nunlock openshell-inference\n')
  [[ "$(HARNESS_AGENT=openclaw openshell_load_profile; printf '%s' "$OPENSHELL_MODEL")" == new-model ]]
  [[ "$(HARNESS_AGENT=hermes openshell_load_profile; printf '%s' "$OPENSHELL_MODEL")" == new-model ]]
}
retry_transition() {
  fixture
  profiles
  mock_sandboxes
  mock_inference
  atomic_write_file "$(ensure_state_dir)/openshell-model" old-model
  openshell_validate_managed_backend() { error "backend not ready"; }
  expect_failure 'backend not ready' openshell_ensure_shared_inference
  [[ "$(cat "$(harness_state_root)/openshell-model")" == old-model ]]
  [[ -f "$(harness_state_root)/openshell-model-pending.json" ]]
  HARNESS_HF_MODEL=""; HARNESS_LLM_MODEL=""
  openshell_apply_model_defaults
  [[ "$HARNESS_HF_MODEL" == org/new-model ]]
  openshell_validate_managed_backend() { :; }
  openshell_ensure_shared_inference
  [[ "$(cat "$(harness_state_root)/openshell-model")" == new-model ]]
  [[ ! -f "$(harness_state_root)/openshell-model-pending.json" ]]
}
pending_conflict() {
  fixture
  atomic_write_file "$(ensure_state_dir)/openshell-model-pending.json" "$(openshell_model_source)"
  HARNESS_HF_MODEL=org/different
  expect_failure 'transition is pending' openshell_apply_model_defaults
}
legacy_image() {
  fixture
  profiles
  mock_sandboxes
  mock_inference
  openshell_agent_exec() { return 1; }
  expect_failure 'predates restart-safe' openshell_ensure_shared_inference
  [[ ! -s "$ACTIONS" ]]
  [[ ! -f "$(harness_state_root)/openshell-model-pending.json" ]]
}
uninstall_fixture() {
  fixture
  . "$SCRIPT_DIR/uninstall.sh"
  ASSUME_YES=1
  HARNESS_RUNTIME=openshell
  mkdir -p "$HARNESS_MODELS_DIR"
  printf 'model data\n' >"$HARNESS_MODELS_DIR/weights"
  ensure_state_dir >/dev/null
  atomic_write_file "$(harness_state_root)/openshell-model" old-model
  remove_all_openshell_agents() { printf 'sandboxes\n' >>"$ACTIONS"; }
  openshell_remove_owned_runtime() { printf 'runtime\n' >>"$ACTIONS"; }
  remove_deployment_container() { printf 'container %s\n' "$1" >>"$ACTIONS"; }
  remove_deployment_network() { printf 'network\n' >>"$ACTIONS"; }
  ensure_nvm_loaded() { :; }
  remove_agent_package() { error "Unexpected host package removal"; }
}
explicit_host_agent_selection() {
  uninstall_fixture
  HARNESS_RUNTIME=host
  atomic_write_file "$(harness_state_root)/installed-agent" hermes
  remove_cli_shim() { printf 'shim %s\n' "$1" >>"$ACTIONS"; }
  remove_agent_package() { printf 'package %s\n' "$1" >>"$ACTIONS"; }
  ovms_is_managed() { return 1; }
  (main --runtime host --harness openclaw --yes)
  grep -Fxq 'package openclaw' "$ACTIONS"
  ! grep -Fxq 'package hermes' "$ACTIONS"
}
full_openshell_with_host_agent() {
  uninstall_fixture
  atomic_write_file "$(harness_state_root)/installed-agent" deepagents-code
  remove_agent_package() { printf 'package %s\n' "$1" >>"$ACTIONS"; }
  ovms_is_managed() { return 1; }
  HARNESS_AGENT=hermes
  (main --runtime openshell --harness openclaw --yes)
  grep -Fxq 'sandboxes' "$ACTIONS"
  grep -Fxq 'runtime' "$ACTIONS"
  grep -Fxq 'package deepagents-code' "$ACTIONS"
  ! grep -Eq '^package (openclaw|hermes)$' "$ACTIONS"
}
complete_uninstall() {
  uninstall_fixture
  (main --runtime openshell --yes)
  [[ ! -e "$HARNESS_MODELS_DIR" && ! -e "$(harness_state_root)" ]]
  cmp "$ACTIONS" <(printf 'sandboxes\nruntime\ncontainer %s\ncontainer %s\nnetwork\n' "$HARNESS_IR_CONTAINER" "$HARNESS_OVMS_CONTAINER")
}
failed_uninstall() {
  uninstall_fixture
  remove_deployment_container() { error "Docker removal denied"; }
  expect_failure 'Docker removal denied' main --runtime openshell --yes
  [[ -f "$HARNESS_MODELS_DIR/weights" && -f "$(harness_state_root)/openshell-model" ]]
}
scoped_uninstall() {
  uninstall_fixture
  remove_openshell_agent() { printf 'one sandbox\n' >>"$ACTIONS"; }
  (main --runtime openshell --sandbox-only --harness hermes --yes)
  cmp "$ACTIONS" <(printf 'one sandbox\n')
  [[ -f "$HARNESS_MODELS_DIR/weights" && -f "$(harness_state_root)/openshell-model" ]]
}
owned_runtime_fixture() {
  fixture
  atomic_write_file "$(ensure_state_dir)/openshell-owned" "$HARNESS_OPENSHELL_VERSION"
  AVAILABLE=1
  command_exists() { [[ "$1" != openshell || "$AVAILABLE" == 1 ]]; }
  openshell() {
    case "$1 ${2:-}" in
      '--version ') printf 'openshell %s\n' "$HARNESS_OPENSHELL_VERSION" ;;
      'gateway list') printf '[{"name":"openshell","type":"local","is_remote":false}]' ;;
      'sandbox list')
        [[ "$*" == 'sandbox list --all-workspaces -g openshell -o json' ]] || return 1
        printf '{"sandboxes":[]}' ;;
      'provider list')
        [[ "$*" == 'provider list --all-workspaces -g openshell -o json' ]] || return 1
        printf '{"providers":[]}' ;;
      *) return 1 ;;
    esac
  }
  ps() { printf '%s bash\n' "$(id -u)"; }
  docker() { printf 'unrelated-inference\n'; }
  require_sudo_or_fail() { printf 'sudo-authorized\n' >>"$ACTIONS"; }
  systemctl() {
    printf 'service %s\n' "$*" >>"$ACTIONS"
    if [[ "$*" == *"enable --now openshell-gateway.service"* && "${RESTORE_FAIL:-0}" == 1 ]]; then
      return 1
    fi
  }
  sudo() { printf 'purge %s\n' "$*" >>"$ACTIONS"; AVAILABLE=0; }
}
owned_runtime_remove() {
  owned_runtime_fixture
  load_openshell_node() { :; }
  mkdir -p "$HOME/.config/openshell" "$HOME/.local/state/openshell"
  openshell_remove_owned_runtime
  grep -Fxq 'purge dpkg --purge openshell' "$ACTIONS"
  cmp "$ACTIONS" <(printf 'sudo-authorized\nservice --user disable --now openshell-gateway.service\npurge dpkg --purge openshell\nservice --user daemon-reload\n')
  [[ ! -e "$(harness_state_root)/openshell-owned" ]]
  [[ ! -e "$HOME/.config/openshell" && ! -e "$HOME/.local/state/openshell" ]]
}
owned_runtime_loads_node() {
  owned_runtime_fixture
  NODE_LOAD_CALLED=""
  load_openshell_node() { NODE_LOAD_CALLED=1; }
  openshell_remove_owned_runtime
  [[ "$NODE_LOAD_CALLED" == 1 ]]
}
shared_runtime_refused() {
  owned_runtime_fixture
  openshell() {
    case "$1 ${2:-}" in
      '--version ') printf 'openshell %s\n' "$HARNESS_OPENSHELL_VERSION" ;;
      'gateway list') printf '[{"name":"openshell","type":"local","is_remote":false}]' ;;
      'sandbox list') printf '{"sandboxes":[{"name":"unrelated"}]}' ;;
      *) return 1 ;;
    esac
  }
  expect_failure 'resources remain' openshell_remove_owned_runtime
  [[ ! -s "$ACTIONS" && -f "$(harness_state_root)/openshell-owned" ]]
}
preexisting_runtime() {
  fixture
  openshell() { error "Pre-existing runtime must not be modified"; }
  openshell_remove_owned_runtime
  [[ ! -s "$ACTIONS" ]]
}
runtime_other_workspace() {
  owned_runtime_fixture
  docker() { printf 'openshell-another-workspace--foreign-sandbox\n'; }
  expect_failure 'runtime containers remain' openshell_remove_owned_runtime
  [[ ! -s "$ACTIONS" && -f "$(harness_state_root)/openshell-owned" ]]
}
runtime_global_resource_check() {
  owned_runtime_fixture
  local kind="$1" response="$2"
  OPENSHELL_WORKSPACE=installed-agent-workspace
  openshell() {
    case "$1 ${2:-}" in
      '--version ') printf 'openshell %s\n' "$HARNESS_OPENSHELL_VERSION" ;;
      'gateway list') printf '[{"name":"openshell","type":"local","is_remote":false}]' ;;
      'sandbox list' | 'provider list')
        if [[ "$1" == "$kind" && " $* " == *" --all-workspaces "* ]]; then
          printf '%s' "$response"
        elif [[ "$1" == sandbox ]]; then
          printf '{"sandboxes":[]}'
        else
          printf '{"providers":[]}'
        fi ;;
      *) return 1 ;;
    esac
  }
  expect_failure 'resources remain' openshell_remove_owned_runtime
  [[ ! -s "$ACTIONS" && -f "$(harness_state_root)/openshell-owned" ]]
}
runtime_purge_failure() {
  owned_runtime_fixture
  sudo() { return 1; }
  expect_failure 'gateway was restarted' openshell_remove_owned_runtime
  cmp "$ACTIONS" <(printf 'sudo-authorized\nservice --user disable --now openshell-gateway.service\nservice --user enable --now openshell-gateway.service\n')
  [[ -f "$(harness_state_root)/openshell-owned" ]]
}
runtime_sudo_authorization_failure() {
  owned_runtime_fixture
  require_sudo_or_fail() { error "sudo authorization denied"; }
  expect_failure 'sudo authorization denied' openshell_remove_owned_runtime
  [[ ! -s "$ACTIONS" && -f "$(harness_state_root)/openshell-owned" ]]
}
runtime_purge_and_restore_failure() {
  owned_runtime_fixture
  RESTORE_FAIL=1
  sudo() { return 1; }
  expect_failure "Manually run 'systemctl --user enable --now openshell-gateway.service'" openshell_remove_owned_runtime
  cmp "$ACTIONS" <(printf 'sudo-authorized\nservice --user disable --now openshell-gateway.service\nservice --user enable --now openshell-gateway.service\n')
  [[ -f "$(harness_state_root)/openshell-owned" ]]
}
owned_service_retry() {
  owned_runtime_fixture
  ensure_openshell_cli
  grep -Fq 'enable --now openshell-gateway.service' "$ACTIONS"
  [[ -f "$(harness_state_root)/openshell-owned" ]]
}
register_owned_gateway() {
  owned_runtime_fixture
  openshell() {
    case "$1 ${2:-}" in
      '--version ') printf 'openshell %s\n' "$HARNESS_OPENSHELL_VERSION" ;;
      'gateway list') printf '[]' ;;
      'gateway add') printf '%s\n' "$*" >>"$ACTIONS" ;;
      *) return 1 ;;
    esac
  }
  ensure_openshell_cli
  grep -Fxq 'gateway add https://127.0.0.1:17670 --local --name openshell' "$ACTIONS"
}
validate_all_profiles() {
  fixture
  . "$SCRIPT_DIR/uninstall.sh"
  profiles
  openshell_resource_exists() { return 0; }
  openshell_assert_owned() { :; }
  remove_openshell_agent() { printf 'remove %s\n' "$HARNESS_AGENT" >>"$ACTIONS"; }
  remove_all_openshell_agents
  cmp "$ACTIONS" <(printf 'remove openclaw\nremove deepagents-code\nremove hermes\n')
}
reject_unowned_profile() {
  fixture
  . "$SCRIPT_DIR/uninstall.sh"
  profiles
  openshell_resource_exists() { return 0; }
  openshell_assert_owned() {
    [[ "$HARNESS_AGENT" != hermes ]] || error "Sandbox owner mismatch"
  }
  remove_openshell_agent() { printf 'remove %s\n' "$HARNESS_AGENT" >>"$ACTIONS"; }
  expect_failure 'owner mismatch' remove_all_openshell_agents
  [[ ! -s "$ACTIONS" ]]
}
no_profiles_without_node() {
  fixture
  . "$SCRIPT_DIR/uninstall.sh"
  load_openshell_node() { error "No OpenShell profiles: Node must not be required"; }
  remove_all_openshell_agents
}
deployment_lock_worker() {
  printf '%s start\n' "$1" >>"$ACTIONS"
  sleep 0.1
  printf '%s end\n' "$1" >>"$ACTIONS"
}
deployment_lock_serializes_mutations() {
  fixture
  (with_deployment_lock deployment_lock_worker first) &
  local first_pid=$!
  (with_deployment_lock deployment_lock_worker second) &
  local second_pid=$!
  wait "$first_pid"
  wait "$second_pid"
  mapfile -t events <"$ACTIONS"
  [[ "${#events[@]}" == 4 ]]
  [[ "${events[0]#* }" == start && "${events[1]#* }" == end ]]
  [[ "${events[0]%% *}" == "${events[1]%% *}" ]]
  [[ "${events[2]#* }" == start && "${events[3]#* }" == end ]]
  [[ "${events[2]%% *}" == "${events[3]%% *}" ]]
  [[ -f "$HOME/${HARNESS_STATE_DIRNAME}.deployment.lock" ]]
  [[ ! -e "$(harness_state_root)/${HARNESS_STATE_DIRNAME}.deployment.lock" ]]
}
status_and_connect_skip_deployment_lock() {
  fixture
  with_deployment_lock() { error "Unexpected deployment lock"; }
  prepare_installer_prerequisites() { error "Unexpected prerequisite setup"; }
  status_openshell_agent() { printf 'status\n' >>"$ACTIONS"; }
  connect_openshell_agent() { printf 'connect %s\n' "$HARNESS_AGENT" >>"$ACTIONS"; }
  (main --runtime openshell status)
  (main status --runtime openshell)
  (main connect --runtime openshell --harness hermes)
  (main --runtime openshell --harness deepagents-code connect)
  cmp "$ACTIONS" <(printf 'status\nstatus\nconnect hermes\nconnect deepagents-code\n')
}
missing_option_values_fail_promptly() {
  fixture
  local option
  for option in --harness --runtime --model --model-hub --model-config \
    --model-revision --model-type --model-precision --model-device; do
    expect_failure "$option requires a value|$option requires host or openshell" \
      timeout 5 bash "$SCRIPT_DIR/install.sh" "$option"
  done
}
installer_cli_fixture() {
  export ACTIONS HARNESS_STATE_DIRNAME
  CLI_ROOT="$HOME/cli-fixture"
  mkdir -p "$CLI_ROOT/scripts"
  cp "$SCRIPT_DIR/scripts/install.sh" "$CLI_ROOT/scripts/install.sh"
  cp -R "$SCRIPT_DIR/scripts/lib" "$CLI_ROOT/scripts/lib"
}
connect_works_while_deployment_is_locked() {
  fixture
  installer_cli_fixture
  cat >>"$CLI_ROOT/scripts/lib/openshell.sh" <<'SH'
connect_openshell_agent() { printf 'connect %s\n' "$HARNESS_AGENT" >>"$ACTIONS"; }
SH
  (
    flock -n 201
    timeout 5 bash "$CLI_ROOT/scripts/install.sh" --runtime openshell --harness openclaw connect
    timeout 5 bash "$CLI_ROOT/scripts/install.sh" connect --runtime openshell --harness hermes
  ) 201>"$HOME/${HARNESS_STATE_DIRNAME}.deployment.lock"
  cmp "$ACTIONS" <(printf 'connect openclaw\nconnect hermes\n')
}
group_refresh_precedes_deployment_lock() {
  fixture
  installer_cli_fixture
  local bin="$HOME/bin"
  mkdir -p "$bin"
  printf '#!/usr/bin/env bash\nprintf "startup\\n" >>"$ACTIONS"\n' >"$CLI_ROOT/startup.sh"
  cat >"$bin/sg" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
[[ "$1" == docker && "$2" == -c ]]
exec bash -c "$3"
SH
  chmod 755 "$bin/sg"
  cat >>"$CLI_ROOT/scripts/lib/openshell.sh" <<'SH'
docker() {
  [[ "${HARNESS_DOCKER_GROUP_REEXEC_DONE:-}" == 1 ]] && return 0
  printf 'permission denied\n' >&2
  return 1
}
id() {
  if [[ "${1:-}" == -nG ]]; then printf 'user docker\n'; else command id "$@"; fi
}
openshell_ensure_shared_inference() {
  [[ "$HARNESS_AGENT" == deepagents-code && "$HARNESS_HF_MODEL" == org/reexec ]]
  # The replacement process must hold a fresh lock during deployment mutation.
  if flock -n 202; then
    error "Deployment mutation ran without the deployment lock"
  fi 202>>"$HOME/${HARNESS_STATE_DIRNAME}.deployment.lock"
  printf 'mutation\n' >>"$ACTIONS"
}
SH
  PATH="$bin:$PATH" SKIP_DOCKER="" HARNESS_DOCKER_GROUP_REEXEC_DONE="" \
    timeout 10 bash "$CLI_ROOT/scripts/install.sh" inference --runtime openshell \
      --harness deepagents-code --model org/reexec --non-interactive --skip-gpu-check
  cmp "$ACTIONS" <(printf 'startup\nstartup\nmutation\n')
}

printf 'TAP version 13\n'
run_case 'model change updates all agents, restarts them and preserves token/history' switch_both
run_case 'model source hub/exporter/revisions/config survive install reruns' source_roundtrip
run_case 'model readback waits for agent startup after sandbox phase becomes Ready' delayed_startup
run_case 'OVMS serves only the new model while previous downloaded weights remain cached' select_served_model
run_case 'bare Qwen3.5 model name resolves to the preconfigured OpenVINO source' qwen_alias
run_case 'external model identifiers are preserved verbatim' external_model_id_is_preserved
run_case 'IR port changes are rejected before changing shared inference' ir_port_change_is_rejected_before_backend_update
run_case 'model synchronization locks profiles even when sandboxes are absent' model_sync_locks_agents_without_sandboxes
run_case 'failed switch retains old selection and resumes pending model on rerun' retry_transition
run_case 'another model cannot overwrite an interrupted transition' pending_conflict
run_case 'legacy sandbox images fail before shared inference is modified' legacy_image
run_case 'complete uninstall removes all owned deployment data by default' complete_uninstall
run_case 'explicit host harness selection wins over recorded installed agent' explicit_host_agent_selection
run_case 'full OpenShell uninstall ignores sandbox selectors when choosing the recorded host agent' full_openshell_with_host_agent
run_case 'uninstall failure retains models and recovery state' failed_uninstall
run_case 'explicit sandbox-only removal preserves shared services and model data' scoped_uninstall
run_case 'owned OpenShell gateway service, package and state are removed' owned_runtime_remove
run_case 'owned OpenShell runtime cleanup loads Node before ownership inspection' owned_runtime_loads_node
run_case 'unrelated sandbox blocks gateway and CLI purge' shared_runtime_refused
run_case 'pre-existing OpenShell runtime is not adopted or removed' preexisting_runtime
run_case 'runtime containers in another workspace block OpenShell package removal' runtime_other_workspace
run_case 'sandbox in another workspace blocks global runtime removal' runtime_global_resource_check sandbox '{"sandboxes":[{"name":"unrelated","workspace":"another"}]}'
run_case 'provider without a sandbox in another workspace blocks global runtime removal' runtime_global_resource_check provider '{"providers":[{"name":"unrelated","workspace":"another"}]}'
run_case 'paginated global provider list blocks runtime removal' runtime_global_resource_check provider '{"providers":[],"next_page_token":"more"}'
run_case 'malformed global resource JSON blocks runtime removal' runtime_global_resource_check sandbox 'not-json'
run_case 'invalid global resource list schema blocks runtime removal' runtime_global_resource_check provider '{"providers":{}}'
run_case 'failed OpenShell package purge retains its installation receipt' runtime_purge_failure
run_case 'sudo authorization fails before stopping the owned gateway' runtime_sudo_authorization_failure
run_case 'gateway is restored when owned OpenShell package purge fails' runtime_purge_failure
run_case 'manual gateway recovery is reported if restoration also fails' runtime_purge_and_restore_failure
run_case 'owned OpenShell gateway startup is retried on installer reruns' owned_service_retry
run_case 'fresh owned gateway registers local package TLS with the CLI' register_owned_gateway
run_case 'complete cleanup includes all recorded agent profiles' validate_all_profiles
run_case 'all profile ownership is checked before deleting the first sandbox' reject_unowned_profile
run_case 'host-only cleanup does not require Node to inspect absent sandbox profiles' no_profiles_without_node
run_case 'deployment mutations serialize on a lock outside the removable state root' deployment_lock_serializes_mutations
run_case 'status and interactive connect bypass deployment locks and setup' status_and_connect_skip_deployment_lock
run_case 'missing installer option values fail promptly with their intended diagnostics' missing_option_values_fail_promptly
run_case 'connections to different agents work while a deployment mutation holds the lock' connect_works_while_deployment_is_locked
run_case 'Docker group reexecution precedes deployment locking and retains CLI arguments' group_refresh_precedes_deployment_lock
finish_tests
