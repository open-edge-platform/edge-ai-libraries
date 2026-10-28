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
  HOME="$(mktemp -d "$TEST_ROOT/home.XXXXXX")"
  export HOME
  HARNESS_STATE_DIRNAME=.agent-harness-test
  HARNESS_MODELS_DIR="$HOME/models"
  HARNESS_RUNTIME=openshell
  HARNESS_AGENT=openclaw
  HARNESS_HF_MODEL=""
  HARNESS_LLM_MODEL=""
  HARNESS_LLM_ROUTER_ENDPOINT=""
  HARNESS_LLM_ENDPOINT=""
  HARNESS_OVMS_EXPORTER=docker-pull
  HARNESS_OVMS_EXPORTER_WAS_SET=""
  HARNESS_MODEL_HUB=openvino
  HARNESS_MODEL_HUB_WAS_SET=""
  HARNESS_MODEL_OPTS_GIVEN=""
  HARNESS_MODEL_CONFIG_JSON=""
  OPENSHELL_MODEL_REQUESTED=""
  HARNESS_BIND_HOST=127.0.0.1
  CONTAINERS=""
  ACTIONS="$HOME/actions"
  : >"$ACTIONS"
}
assert_no_action() {
  if grep -q -- "$1" "$ACTIONS"; then
    printf 'Unexpected action matching %s\n' "$1" >&2
    return 1
  fi
}
default_model() {
  fixture
  openshell_apply_model_defaults
  [[ "$HARNESS_HF_MODEL" == OpenVINO/Qwen3.5-9B-int8-ov ]]
  [[ "$HARNESS_OVMS_EXPORTER" == hf-snapshot ]]
  apply_model_source_defaults
  NON_INTERACTIVE=1 require_model_selection
  [[ ! -d "$(harness_state_root)" ]]
}
host_model() {
  fixture
  HARNESS_RUNTIME=host
  openshell_apply_model_defaults
  [[ -z "$HARNESS_HF_MODEL" ]]
  [[ "$HARNESS_OVMS_EXPORTER" == docker-pull ]]
  NON_INTERACTIVE=1
  expect_failure 'No model selected' require_model_selection
}
explicit_model() {
  fixture
  HARNESS_HF_MODEL=org/custom-model
  openshell_apply_model_defaults
  [[ "$HARNESS_HF_MODEL" == org/custom-model && "$HARNESS_OVMS_EXPORTER" == docker-pull ]]
}
explicit_exporter() {
  fixture
  HARNESS_OVMS_EXPORTER_WAS_SET=1
  HARNESS_OVMS_EXPORTER=export-model-py
  openshell_apply_model_defaults
  [[ "$HARNESS_OVMS_EXPORTER" == export-model-py ]]
}
explicit_hub() {
  fixture
  HARNESS_MODEL_HUB=ollama
  HARNESS_MODEL_HUB_WAS_SET=1
  openshell_apply_model_defaults
  apply_model_source_defaults
  [[ -z "$HARNESS_HF_MODEL" && "$HARNESS_OVMS_EXPORTER" == model-download ]]
}
external_model() {
  fixture
  HARNESS_LLM_ROUTER_ENDPOINT=https://example.invalid/v1
  openshell_apply_model_defaults
  [[ -z "$HARNESS_HF_MODEL" ]]
}
registered_model() {
  fixture
  mkdir -p "$HARNESS_MODELS_DIR"
  printf '{"model_config_list":[{"config":{"name":"older-model","base_path":"older-model"}}]}' \
    >"$HARNESS_MODELS_DIR/config.json"
  openshell_apply_model_defaults
  [[ -z "$HARNESS_HF_MODEL" ]]
  [[ "$(resolve_onboarding_model_hint)" == older-model ]]
}
saved_model() {
  fixture
  atomic_write_file "$(ensure_state_dir)/openshell-model" custom-model
  openshell_apply_model_defaults
  [[ "$HARNESS_LLM_MODEL" == custom-model && -z "$HARNESS_HF_MODEL" ]]
}
saved_override() {
  fixture
  atomic_write_file "$(ensure_state_dir)/openshell-model" older-model
  HARNESS_HF_MODEL=org/new-model
  openshell_apply_model_defaults
  [[ "$HARNESS_HF_MODEL" == org/new-model && "$HARNESS_LLM_MODEL" == new-model ]]
}
invalid_saved() {
  fixture
  atomic_write_file "$(ensure_state_dir)/openshell-model" $'bad\nmodel'
  expect_failure 'Invalid saved OpenShell model' openshell_apply_model_defaults
}
symlink_saved() {
  fixture
  ensure_state_dir >/dev/null
  ln -s "$HOME/nonexistent" "$(harness_state_root)/openshell-model"
  expect_failure 'Refusing symlink' openshell_apply_model_defaults
}
profile_model() {
  fixture
  local dir
  dir="$(openshell_profile_dir)"
  ensure_state_dir >/dev/null
  mkdir -p "$dir"
  atomic_write_file "$dir/profile.json" \
    '{"owner":"0123456789abcdef0123456789abcdef","name":"ahi-0123456789ab","gateway":"openshell","agent":"openclaw","model":"profile-model"}'
  atomic_write_file "$(harness_state_root)/openshell-model" other-model
  openshell_apply_model_defaults
  [[ "$HARNESS_LLM_MODEL" == other-model ]]
}
mock_provisioning() {
  docker() { printf '%s\n' "$CONTAINERS"; }
  ensure_inference_backend() {
    printf 'provision %s %s\n' "$HARNESS_HF_MODEL" "$HARNESS_OVMS_EXPORTER" >>"$ACTIONS"
    mkdir -p "$HARNESS_MODELS_DIR"
    printf '{"model_config_list":[{"config":{"name":"%s","base_path":"%s"}}]}' \
      "$HARNESS_LLM_MODEL" "$HARNESS_LLM_MODEL" >"$HARNESS_MODELS_DIR/config.json"
  }
  openshell_validate_shared_inference() { printf 'validate IR\n' >>"$ACTIONS"; }
  openshell_validate_managed_backend() { printf 'validate OVMS\n' >>"$ACTIONS"; }
}
mock_cli() {
  mock_provisioning
  prepare_installer_prerequisites() { :; }
  prepare_installer_host() { printf 'prepare\n' >>"$ACTIONS"; }
  install_openshell_agent() { printf 'sandbox %s\n' "$HARNESS_AGENT" >>"$ACTIONS"; }
  onboard_openshell_agent() { printf 'onboard\n' >>"$ACTIONS"; }
  print_done() { printf 'done\n' >>"$ACTIONS"; }
}
cli_install() {
  fixture
  mock_cli
  (main --runtime openshell --harness openclaw --non-interactive)
  cmp "$ACTIONS" <(printf 'prepare\nprovision OpenVINO/Qwen3.5-9B-int8-ov hf-snapshot\nvalidate IR\nvalidate OVMS\nsandbox openclaw\nonboard\ndone\n')
  HARNESS_HF_MODEL=""; HARNESS_LLM_MODEL=""
  CONTAINERS="$HARNESS_IR_CONTAINER"$'\n'"$HARNESS_OVMS_CONTAINER"
  (main --runtime openshell --harness openclaw --non-interactive)
  [[ "$(grep -c '^provision ' "$ACTIONS")" == 1 ]]
  [[ "$(grep -c '^sandbox openclaw' "$ACTIONS")" == 2 ]]
}
cli_inference() {
  fixture
  mock_cli
  (main inference --runtime openshell --non-interactive)
  assert_no_action '^sandbox '
  [[ "$(cat "$(harness_state_root)/openshell-model")" == Qwen3.5-9B-int8-ov ]]
}
cli_mismatch() {
  fixture
  mock_cli
  CONTAINERS="$HARNESS_IR_CONTAINER"
  HARNESS_HF_MODEL=org/new-model
  openshell_validate_shared_inference() {
    [[ "$HARNESS_LLM_MODEL" == old-model ]] || error "model mismatch"
  }
  expect_failure 'model mismatch' main --runtime openshell --non-interactive
  grep -q '^provision org/new-model' "$ACTIONS"
  [[ -f "$(harness_state_root)/openshell-model-pending.json" ]]
  [[ ! -f "$(harness_state_root)/openshell-model-source.json" ]]
}
cli_host() {
  fixture
  mock_cli
  install_selected_agent() { printf 'host install\n' >>"$ACTIONS"; }
  run_agent_onboard() { printf 'host onboard\n' >>"$ACTIONS"; }
  (main --runtime host --harness hermes --model org/host-model --non-interactive)
  grep -Fxq 'provision org/host-model docker-pull' "$ACTIONS"
  grep -Fxq 'host install' "$ACTIONS"
  assert_no_action '^sandbox '
}
fresh_provisioning() {
  fixture
  mock_provisioning
  openshell_apply_model_defaults
  openshell_ensure_shared_inference
  grep -Fxq 'provision OpenVINO/Qwen3.5-9B-int8-ov hf-snapshot' "$ACTIONS"
  [[ "$(cat "$(harness_state_root)/openshell-model")" == Qwen3.5-9B-int8-ov ]]
  [[ "$(stat -c %a "$(harness_state_root)/openshell-model")" == 600 ]]
  CONTAINERS="$HARNESS_IR_CONTAINER"$'\n'"$HARNESS_OVMS_CONTAINER"
  HARNESS_HF_MODEL=""; HARNESS_LLM_MODEL=""
  openshell_apply_model_defaults
  openshell_ensure_shared_inference
  [[ "$(grep -c '^provision ' "$ACTIONS")" == 1 ]]
  [[ "$HARNESS_LLM_MODEL" == Qwen3.5-9B-int8-ov ]]
}
existing_provisioning() {
  fixture
  mock_provisioning
  CONTAINERS="$HARNESS_IR_CONTAINER"$'\n'"$HARNESS_OVMS_CONTAINER"
  HARNESS_LLM_MODEL=existing-model
  openshell_ensure_shared_inference
  assert_no_action '^provision '
  [[ "$(cat "$(harness_state_root)/openshell-model")" == existing-model ]]
}
partial_provisioning() {
  fixture
  mock_provisioning
  CONTAINERS="$HARNESS_OVMS_CONTAINER"
  openshell_apply_model_defaults
  OPENSHELL_MODEL_REQUESTED=""
  expect_failure 'Shared inference is incomplete' openshell_ensure_shared_inference
  [[ ! -s "$ACTIONS" ]]
}
docker_unavailable() {
  fixture
  docker() { return 1; }
  expect_failure 'Cannot inspect shared inference' openshell_ensure_shared_inference
}
invalid_route() {
  fixture
  mock_provisioning
  CONTAINERS="$HARNESS_IR_CONTAINER"
  openshell_validate_shared_inference() { error "model mismatch"; }
  expect_failure 'model mismatch' openshell_ensure_shared_inference
  [[ ! -s "$ACTIONS" && ! -e "$(harness_state_root)/openshell-model" ]]
}
lan_provisioning() {
  fixture
  mock_provisioning
  HARNESS_BIND_HOST=0.0.0.0
  expect_failure 'must not be LAN-published' openshell_ensure_shared_inference
  [[ ! -s "$ACTIONS" ]]
}
backend_response() {
  fixture
  local kind="$1" expected
  HARNESS_LLM_MODEL=Qwen3.5-9B-int8-ov
  MODEL_PORT_FILE="$HOME/port"
  node - "$MODEL_PORT_FILE" "$kind" <<'JS' &
const fs = require("node:fs"), http = require("node:http");
const [file, kind] = process.argv.slice(2);
const server = http.createServer((req, res) => {
  res.writeHead(kind === "unready" || req.url !== "/v2/models/Qwen3.5-9B-int8-ov/ready" ? 404 : 200);
  res.end();
});
server.listen(0, "127.0.0.1", () => fs.writeFileSync(file, String(server.address().port)));
JS
  MODEL_SERVER_PID=$!
  trap 'kill "$MODEL_SERVER_PID"; wait "$MODEL_SERVER_PID" 2>/dev/null || true' EXIT
  local attempt ip=127.0.0.1 network="$HARNESS_BACKEND_NETWORK"
  for attempt in {1..100}; do
    [[ ! -s "$MODEL_PORT_FILE" ]] || break
    sleep 0.05
  done
  [[ -s "$MODEL_PORT_FILE" ]]
  HARNESS_OVMS_REST_PORT="$(cat "$MODEL_PORT_FILE")"
  [[ "$kind" != lan ]] || ip=0.0.0.0
  [[ "$kind" != network ]] || network=other
  docker() {
    printf '[{"HostConfig":{"PortBindings":{"8000/tcp":[{"HostIp":"%s","HostPort":"%s"}]}},"NetworkSettings":{"Networks":{"%s":{}}}},{"NetworkSettings":{"Networks":{"%s":{}}}}]' \
      "$ip" "$HARNESS_OVMS_REST_PORT" "$network" "$HARNESS_BACKEND_NETWORK"
  }
  if [[ "$kind" == ready ]]; then
    openshell_validate_managed_backend
  else
    case "$kind" in
      lan) expected='OVMS must be published only on the expected host loopback port' ;;
      network) expected='OVMS and IR must share the configured private backend network' ;;
      unready) expected="OVMS model.*is not ready" ;;
    esac
    expect_failure "$expected" openshell_validate_managed_backend
  fi
}
skip_lan_prompt() {
  fixture
  HARNESS_ADVERTISED_HOST_WAS_SET=1
  HARNESS_ADVERTISED_HOST=192.0.2.1
  persist_advertised_host() { error "OpenShell must not offer or save a LAN publication"; }
  maybe_prompt_advertised_host
}
router_proxy() {
  fixture
  NO_PROXY=upper.example
  no_proxy=lower.example
  ensure_inference_router_image() { :; }
  ensure_backend_network() { printf 'network\n' >>"$ACTIONS"; }
  write_inference_router_config() { [[ "$1" == Qwen3.5-9B-int8-ov ]]; }
  intel_gpu_docker_device_args() { :; }
  docker_proxy_env_args_into() { :; }
  wait_for_inference_router_ready() { :; }
  docker() {
    [[ "$1" != inspect ]] || return 1
    printf '%s\n' "$@" >>"$ACTIONS"
  }
  ensure_inference_router Qwen3.5-9B-int8-ov
  grep -Fxq "NO_PROXY=upper.example,lower.example,$HARNESS_OVMS_CONTAINER" "$ACTIONS"
  grep -Fxq "no_proxy=upper.example,lower.example,$HARNESS_OVMS_CONTAINER" "$ACTIONS"
  grep -Fxq "$HARNESS_BACKEND_NETWORK" "$ACTIONS"
  grep -Fxq "127.0.0.1:$HARNESS_IR_PORT:8000" "$ACTIONS"
}
cached_snapshot() {
  fixture
  openshell_apply_model_defaults
  HARNESS_IR_WORKSPACE_DIR="$(harness_state_root)/inference-router/workspace"
  mkdir -p "$HARNESS_MODELS_DIR/Qwen3.5-9B-int8-ov"
  printf 'cached model graph\n' >"$HARNESS_MODELS_DIR/Qwen3.5-9B-int8-ov/graph.pbtxt"
  ensure_openvino_model_server() { printf 'OVMS start\n' >>"$ACTIONS"; }
  wait_for_ovms_model_ready() { [[ "$1" == Qwen3.5-9B-int8-ov ]]; }
  ensure_inference_router() {
    [[ "$1" == Qwen3.5-9B-int8-ov ]]
    write_inference_router_config "$1"
  }
  ensure_inference_backend
  ensure_inference_backend
  ovms_is_managed
  [[ "$(ovms_sole_registered_model_name)" == Qwen3.5-9B-int8-ov ]]
  grep -Fq "http://$HARNESS_OVMS_CONTAINER:8000/v3" "$HARNESS_IR_WORKSPACE_DIR/config.yaml"
  grep -Fq 'model: "Qwen3.5-9B-int8-ov"' "$HARNESS_IR_WORKSPACE_DIR/config.yaml"
  [[ "$(cat "$HARNESS_MODELS_DIR/Qwen3.5-9B-int8-ov/graph.pbtxt")" == 'cached model graph' ]]
}
snapshot_download() {
  fixture
  local kind="$1" out_dir="$HARNESS_MODELS_DIR/Qwen3.5-9B-int8-ov"
  openshell_apply_model_defaults
  mkdir -p "$HARNESS_MODELS_DIR/.hf-snapshot-venv/bin"
  printf 'deactivate() { :; }\n' >"$HARNESS_MODELS_DIR/.hf-snapshot-venv/bin/activate"
  python_venv_usable() { :; }
  spin() { shift; "$@"; }
  pip() { :; }
  python3() {
    [[ "$1" == - && "$2" == OpenVINO/Qwen3.5-9B-int8-ov ]]
    mkdir -p "$3"
    printf '{"model_type":"qwen3_5"}' >"$3/config.json"
    printf 'downloaded weights\n' >"$3/openvino_language_model.bin"
  }
  intel_gpu_docker_device_args() {
    if [[ "$kind" == gpu ]]; then printf '%s' '--device /dev/dri'; fi
  }
  docker() {
    printf '%s\n' "$@" >>"$ACTIONS"
    [[ "$kind" != failure ]] || return 1
    if [[ "$kind" != no-graph ]]; then
      printf 'native OVMS graph\n' >"$out_dir/graph.pbtxt"
    fi
  }
  if [[ "$kind" == failure ]]; then
    expect_failure 'Could not configure the OVMS graph' export_model_via_hf_snapshot "$HARNESS_HF_MODEL"
    [[ -f "$out_dir/openvino_language_model.bin" ]]
    [[ ! -f "$out_dir/graph.pbtxt" ]]
  elif [[ "$kind" == no-graph ]]; then
    expect_failure 'produced no graph.pbtxt' export_model_via_hf_snapshot "$HARNESS_HF_MODEL"
    [[ ! -f "$out_dir/graph.pbtxt" ]]
  else
    export_model_via_hf_snapshot "$HARNESS_HF_MODEL"
    [[ "$(ovms_sole_registered_model_name)" == Qwen3.5-9B-int8-ov ]]
    grep -Fxq -- --configure "$ACTIONS"
    grep -Fxq -- text_generation "$ACTIONS"
    grep -Fxq -- none "$ACTIONS"
    grep -Fxq -- "$HARNESS_OVMS_IMAGE" "$ACTIONS"
    if [[ "$kind" == gpu ]]; then
      grep -Fxq GPU "$ACTIONS"
    else
      grep -Fxq CPU "$ACTIONS"
    fi
  fi
}
printf 'TAP version 13\n'
run_case 'OpenShell defaults to Qwen3.5 snapshot download without creating state' default_model
run_case 'host mode still requires explicit model selection' host_model
run_case 'explicit model remains unchanged' explicit_model
run_case 'explicit exporter remains unchanged' explicit_exporter
run_case 'explicit nondefault hub does not receive an incompatible Qwen default' explicit_hub
run_case 'external endpoint has no Qwen default' external_model
run_case 'existing OVMS registry prevents implicit model replacement' registered_model
run_case 'shared model selection survives repeated installs' saved_model
run_case 'explicit model overrides saved shared selection' saved_override
run_case 'invalid saved model fails explicitly' invalid_saved
run_case 'symlinked saved model is rejected' symlink_saved
run_case 'shared model selection takes precedence over an older agent profile' profile_model
run_case 'fresh provisioning persists model and rerun does not reprovision' fresh_provisioning
run_case 'existing shared inference is validated without replacement' existing_provisioning
run_case 'partial inference deployment requires explicit repair' partial_provisioning
run_case 'Docker failure is not treated as a fresh host' docker_unavailable
run_case 'route mismatch does not provision or persist a model' invalid_route
run_case 'LAN publication fails before provisioning' lan_provisioning
run_case 'OpenShell skips the host LAN publication prompt' skip_lan_prompt
run_case 'managed OVMS serves exact model on private network and loopback' backend_response ready
run_case 'managed OVMS LAN publication is rejected' backend_response lan
run_case 'managed OVMS network mismatch is rejected' backend_response network
run_case 'managed OVMS unready model is rejected' backend_response unready
run_case 'IR retains both bypass lists and adds managed backend hostname' router_proxy
run_case 'normal snapshot flow registers cached Qwen idempotently and writes managed IR route' cached_snapshot
run_case 'Qwen download generates native OVMS graph for CPU before registration' snapshot_download cpu
run_case 'Qwen download generates native OVMS graph for GPU before registration' snapshot_download gpu
run_case 'graph-generation failure preserves downloaded Qwen weights and fails explicitly' snapshot_download failure
run_case 'graph-generation success without a graph is rejected' snapshot_download no-graph
run_case 'full CLI provisions inference before sandbox and preserves it on rerun' cli_install
run_case 'inference CLI uses Qwen default without installing an agent' cli_inference
run_case 'full CLI retains pending transition when selected model fails readiness validation' cli_mismatch
run_case 'host CLI retains existing installation flow and exporter' cli_host
finish_tests
