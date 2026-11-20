#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Unit tests for `./install.sh observability <enable|disable|show>` (scripts/lib/metrics.sh).
# Docker and the Hermes CLI are replaced by shell functions; nothing touches the host.
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
  HARNESS_RUNTIME=host
  HARNESS_AGENT=hermes
  HARNESS_BIND_HOST=127.0.0.1
  HARNESS_LLM_ROUTER_ENDPOINT=""
  HARNESS_IR_WORKSPACE_DIR="$HOME/ir"
  HERMES_HOME="$HOME/hermes"
  export HERMES_HOME
  ACTIONS="$HOME/actions"
  : >"$ACTIONS"
  mkdir -p "$HARNESS_IR_WORKSPACE_DIR" "$HERMES_HOME"
  printf 'log_level: "INFO"\nrouting:\n  policy: "Balanced"\ntelemetry:\n  backend: "memory"\n  enabled: true\n' \
    >"$HARNESS_IR_WORKSPACE_DIR/config.yaml"
  ensure_nvm_loaded() { :; }
  M_BACKEND_GIVEN=1 M_CONTENT_GIVEN=1 M_CLEAN="" M_KEEP_JAEGER=""
  wait_for_inference_router_ready() { :; }
  docker() {
    case "$1" in
      inspect)
        if [[ "${2:-}" == -f ]]; then
          case "$3" in
            *GroupAdd*) printf '%s\n' "${TEST_IR_GROUPADD-[\"$(id -g)\"]}" ;;
            *Labels*) printf '%s\n' "${TEST_JAEGER_LABEL-metrics-jaeger}" ;;
            *PortBindings*)
              if [[ -n "${TEST_JAEGER_BINDINGS:-}" ]]; then
                printf '%s\n' "$TEST_JAEGER_BINDINGS"
              else
                printf '{"16686/tcp":[{"HostIp":"127.0.0.1","HostPort":"%s"}],"4318/tcp":[{"HostIp":"127.0.0.1","HostPort":"%s"}]}\n' \
                  "${TEST_JAEGER_UI_PUBLISHED:-$HARNESS_JAEGER_UI_PORT}" "$HARNESS_JAEGER_OTLP_PORT"
              fi ;;
            *) printf 'true\n' ;;
          esac
        fi ;;
      container)
        [[ -z "${TEST_DOCKER_LS_FAILS:-}" ]] || return 1
        printf '%s\n' "${TEST_CONTAINERS-$HARNESS_JAEGER_CONTAINER
$HARNESS_IR_CONTAINER}" ;;
      info) printf '%s\n' "${TEST_DOCKER_SECOPTS-[name=apparmor name=seccomp,profile=builtin name=cgroupns]}" ;;
      restart | rm | start | run | pull) printf 'docker %s %s\n' "$1" "${*: -1}" >>"$ACTIONS" ;;
      image) return 0 ;;
    esac
  }
  hermes() {
    case "$1 ${2:-}" in
      'plugins install')
        [[ "${TEST_HERMES_FAILS:-}" != install ]] || return 1
        mkdir -p "$HERMES_HOME/plugins/hermes_otel"; printf 'hermes install %s%s\n' "$3" "${4:+ $4 $5}" >>"$ACTIONS" ;;
      'plugins enable') printf 'hermes enable\n' >>"$ACTIONS" ;;
      'plugins disable')
        [[ "${TEST_HERMES_FAILS:-}" != disable ]] || return 1
        printf 'hermes disable\n' >>"$ACTIONS" ;;
      'plugins list') printf 'hermes_otel  %s\n' "${TEST_HERMES_PLUGIN_STATE:-enabled}" ;;
    esac
  }
}

parse_defaults() {
  fixture
  metrics_parse_args enable
  [[ "$M_TARGET" == all && "$M_BACKEND" == sqlite && "$M_CONTENT" == off && -z "$M_ENDPOINT" ]]
  metrics_parse_args enable --target harness --backend=jaeger --endpoint http://h:4318/v1/traces --content full
  [[ "$M_TARGET" == harness && "$M_BACKEND" == jaeger && "$M_CONTENT" == full ]]
  [[ "$M_ENDPOINT" == http://h:4318/v1/traces ]]
}

parse_rejections() {
  fixture
  expect_failure '--target must be' metrics_parse_args show --target bogus
  expect_failure '--backend must be' metrics_parse_args enable --backend prometheus
  expect_failure '--backend must be sqlite or jaeger' metrics_parse_args enable --backend otlp --endpoint http://h:4318/v1/traces
  expect_failure '--content must be' metrics_parse_args enable --content all
  expect_failure 'cannot be combined with --backend sqlite' \
    metrics_parse_args enable --backend sqlite --endpoint http://h:4318/v1/traces
  expect_failure 'plain http\(s\) URL' \
    metrics_parse_args enable --backend jaeger --endpoint 'http://user:pw@h:4318/v1/traces'
  expect_failure 'plain http\(s\) URL' \
    metrics_parse_args enable --backend jaeger --endpoint 'http://h:4318/v1/traces?token=x'
  expect_failure 'only valid with .observability enable' metrics_parse_args disable --backend jaeger
  expect_failure 'apply to the harness' metrics_parse_args enable --target router --content full
  expect_failure 'requires a value' metrics_parse_args enable --endpoint
  expect_failure 'given more than once' metrics_parse_args enable --backend sqlite --backend=jaeger
  expect_failure 'given more than once' metrics_parse_args show --target router --target all
  expect_failure 'port must be between' \
    metrics_parse_args enable --backend jaeger --endpoint http://h:99999/v1/traces
  expect_failure 'port must be between' \
    metrics_parse_args enable --backend jaeger --endpoint 'http://[::1]:0/v1/traces'
  metrics_parse_args enable --backend jaeger --endpoint 'http://[::1]:4318/v1/traces'
  [[ "$M_ENDPOINT" == 'http://[::1]:4318/v1/traces' ]]
  metrics_parse_args enable --backend jaeger --endpoint http://h:65535
  expect_failure 'plain http\(s\) URL' \
    metrics_parse_args enable --backend jaeger --endpoint 'http://[::1]x:4318/v1/traces'
}

router_toggle() {
  fixture
  local cfg="$HARNESS_IR_WORKSPACE_DIR/config.yaml"
  metrics_router_apply true
  grep -Fq 'backend: "file"' "$cfg"
  grep -Fq 'file_path: "/app/ir_metrics.jsonl"' "$cfg"
  grep -Fq 'policy: "Balanced"' "$cfg"
  [[ -f "$HARNESS_IR_WORKSPACE_DIR/ir_metrics.jsonl" ]]
  [[ "$(metrics_state_get router.enabled)" == true ]]
  [[ "$(grep -c '^telemetry:' "$cfg")" == 1 ]]
  grep -Fxq "docker restart $HARNESS_IR_CONTAINER" "$ACTIONS"
  metrics_router_apply false
  grep -Fq 'backend: "memory"' "$cfg"
  refute grep -Fq 'file_path' "$cfg"
  [[ "$(metrics_state_get router.enabled)" == false ]]
  [[ -f "$HARNESS_IR_WORKSPACE_DIR/ir_metrics.jsonl" ]]
}

router_setting_survives_config_regeneration() {
  fixture
  ovms_internal_endpoint() { printf 'http://ovms:8000/v3'; }
  metrics_router_apply true
  _write_inference_router_config_locked test-model
  grep -Fq 'backend: "file"' "$HARNESS_IR_WORKSPACE_DIR/config.yaml"
  grep -Fq 'model: "test-model"' "$HARNESS_IR_WORKSPACE_DIR/config.yaml"
  metrics_router_apply false
  _write_inference_router_config_locked test-model
  grep -Fq 'backend: "memory"' "$HARNESS_IR_WORKSPACE_DIR/config.yaml"
}

router_rewrite_keeps_blocks_after_telemetry() {
  fixture
  local cfg="$HARNESS_IR_WORKSPACE_DIR/config.yaml"
  printf 'telemetry:\n  backend: "memory"\n  enabled: true\nplugins:\n  - name: "x"\n' >>"$cfg"
  metrics_router_apply true
  grep -Fq 'name: "x"' "$cfg"
  [[ "$(grep -c '^telemetry:' "$cfg")" == 1 ]]
}

router_without_config_defers() {
  fixture
  rm -f "$HARNESS_IR_WORKSPACE_DIR/config.yaml"
  metrics_router_apply true
  [[ "$(metrics_state_get router.enabled)" == true ]]
  refute grep -q restart "$ACTIONS"
}

harness_enable_disable() {
  fixture
  local cfg="$HERMES_HOME/hermes_otel.yaml"
  # An external Jaeger: exported to, but not managed, so no query_port is written.
  M_TARGET=harness M_BACKEND=jaeger M_ENDPOINT=http://collector:4318/v1/traces M_CONTENT=preview
  metrics_enable_harness
  grep -Fxq 'hermes install hermes_otel' "$ACTIONS"
  grep -Fxq 'hermes enable' "$ACTIONS"
  grep -Fxq 'content_capture: "preview"' "$cfg"
  grep -Fq 'type: jaeger' "$cfg"
  grep -Fq 'endpoint: "http://collector:4318/v1/traces"' "$cfg"
  refute grep -Fq 'query_port' "$cfg"
  refute grep -q 'docker run' "$ACTIONS"
  [[ "$(uname -s)" != Linux || "$(stat -c '%a' "$cfg")" == 600 ]]
  [[ "$(metrics_state_get harness.backend)" == jaeger && "$(metrics_state_get harness.managed_jaeger)" == false ]]
  # sqlite means no exporter entry, and "off" must stay a quoted string.
  M_BACKEND=sqlite M_ENDPOINT="" M_CONTENT=off
  metrics_enable_harness
  grep -Fxq 'content_capture: "off"' "$cfg"
  refute grep -q 'backends:' "$cfg"
  metrics_disable_harness
  grep -Fxq 'hermes disable' "$ACTIONS"
  [[ ! -e "$cfg" && -d "$HERMES_HOME/plugins/hermes_otel" ]]
  [[ "$(metrics_state_get harness.enabled)" == false ]]
}

harness_managed_jaeger() {
  fixture
  # An existing container is started/kept, never recreated.
  M_TARGET=harness M_BACKEND=jaeger M_ENDPOINT="" M_CONTENT=off
  metrics_enable_harness
  grep -Fq 'type: jaeger' "$HERMES_HOME/hermes_otel.yaml"
  grep -Fq "endpoint: \"http://127.0.0.1:${HARNESS_JAEGER_OTLP_PORT}/v1/traces\"" "$HERMES_HOME/hermes_otel.yaml"
  grep -Fq "query_port: ${HARNESS_JAEGER_UI_PORT}" "$HERMES_HOME/hermes_otel.yaml"
  [[ "$(metrics_state_get harness.managed_jaeger)" == true ]]
  metrics_disable_harness
  grep -Fxq "docker rm $HARNESS_JAEGER_CONTAINER" "$ACTIONS"
  [[ "$(metrics_state_get harness.managed_jaeger)" == false ]]
}

jaeger_port_mismatch_is_rejected() {
  fixture
  M_TARGET=harness M_BACKEND=jaeger M_ENDPOINT="" M_CONTENT=off
  TEST_JAEGER_UI_PUBLISHED=1 expect_failure 'must publish exactly' metrics_enable_harness
  [[ ! -e "$HERMES_HOME/hermes_otel.yaml" ]]
  # A wildcard or IPv6-any binding would expose the trace UI to the network.
  TEST_JAEGER_BINDINGS='{"16686/tcp":[{"HostIp":"0.0.0.0","HostPort":"16686"}],"4318/tcp":[{"HostIp":"127.0.0.1","HostPort":"4318"}]}' \
    expect_failure 'must publish exactly' metrics_enable_harness
  TEST_JAEGER_BINDINGS='{"16686/tcp":[{"HostIp":"::","HostPort":"16686"}],"4318/tcp":[{"HostIp":"127.0.0.1","HostPort":"4318"}]}' \
    expect_failure 'must publish exactly' metrics_enable_harness
  # An extra published port is refused too.
  TEST_JAEGER_BINDINGS='{"16686/tcp":[{"HostIp":"127.0.0.1","HostPort":"16686"}],"4318/tcp":[{"HostIp":"127.0.0.1","HostPort":"4318"}],"14250/tcp":[{"HostIp":"0.0.0.0","HostPort":"14250"}]}' \
    expect_failure 'must publish exactly' metrics_enable_harness
  [[ ! -d "$HERMES_HOME/plugins/hermes_otel" ]]
}

foreign_jaeger_is_never_reused_or_removed() {
  fixture
  M_TARGET=harness M_BACKEND=jaeger M_ENDPOINT="" M_CONTENT=off
  TEST_JAEGER_LABEL='' expect_failure 'not created by this installer' metrics_enable_harness
  [[ ! -s "$ACTIONS" && ! -d "$HERMES_HOME/plugins/hermes_otel" ]]
  # Removal (also used by uninstall) leaves a same-named container that is not ours.
  TEST_JAEGER_LABEL='' metrics_remove_jaeger
  refute grep -q 'docker rm' "$ACTIONS"
  metrics_remove_jaeger
  grep -Fxq "docker rm $HARNESS_JAEGER_CONTAINER" "$ACTIONS"
  # With no container at all, nothing is removed.
  : >"$ACTIONS"
  TEST_CONTAINERS='' metrics_remove_jaeger
  [[ ! -s "$ACTIONS" ]]
}

docker_query_failure_is_not_absence() {
  fixture
  M_TARGET=harness M_BACKEND=jaeger M_ENDPOINT="" M_CONTENT=off
  TEST_DOCKER_LS_FAILS=1 expect_failure 'Cannot inspect Docker containers' metrics_enable_harness
  [[ ! -s "$ACTIONS" ]]
  TEST_DOCKER_LS_FAILS=1 expect_failure 'Cannot inspect Docker containers' metrics_remove_jaeger
  refute grep -q 'docker run' "$ACTIONS"
}

rejected_endpoint_is_not_echoed() {
  fixture
  local out
  out="$( (metrics_parse_args enable --backend jaeger --endpoint 'http://user:s3cr3t@h:4318/v1/traces?token=abc') 2>&1 || true)"
  grep -Fq 'plain http(s) URL' <<<"$out"
  refute grep -Fq 's3cr3t' <<<"$out"
  out="$( (metrics_parse_args enable --backend jaeger --endpoint 'http://h:99999/s3cr3t') 2>&1 || true)"
  grep -Fq 'port must be between' <<<"$out"
  refute grep -Fq 's3cr3t' <<<"$out"
}

saved_settings_are_resolved_before_validation() {
  fixture
  M_TARGET=harness M_BACKEND=jaeger M_ENDPOINT=http://collector:4318/v1/traces M_CONTENT=preview
  metrics_enable_harness
  # Only the endpoint changes: the saved backend and content are kept.
  metrics_parse_args enable --target harness --endpoint http://other:4318/v1/traces
  metrics_enable_harness
  [[ "$(metrics_state_get harness.backend)" == jaeger && "$(metrics_state_get harness.content)" == preview ]]
  [[ "$(metrics_state_get harness.endpoint)" == http://other:4318/v1/traces ]]
  # Naming the same backend again, without an endpoint, keeps the saved one.
  metrics_parse_args enable --target harness --backend jaeger
  metrics_enable_harness
  [[ "$(metrics_state_get harness.endpoint)" == http://other:4318/v1/traces ]]
  [[ "$(metrics_state_get harness.managed_jaeger)" == false ]]
  # An endpoint saved while another backend was active is never inherited.
  metrics_parse_args enable --target harness --backend sqlite
  metrics_enable_harness
  metrics_parse_args enable --target harness --backend jaeger
  metrics_enable_harness
  [[ "$(metrics_state_get harness.managed_jaeger)" == true ]]
  # Genuinely unusable combinations are still rejected.
  expect_failure 'cannot be combined with --backend sqlite' \
    metrics_parse_args enable --target harness --backend sqlite --endpoint http://h:4318/v1/traces
  fixture
  metrics_parse_args enable --target harness --endpoint http://h:4318/v1/traces
  expect_failure 'needs an exporting backend' metrics_enable_harness
}

plugin_source_is_validated() {
  fixture
  M_TARGET=harness M_BACKEND=sqlite M_ENDPOINT="" M_CONTENT=off
  HARNESS_HERMES_OTEL_PLUGIN='--evil' expect_failure 'HARNESS_HERMES_OTEL_PLUGIN must be' metrics_enable_harness
  HARNESS_HERMES_OTEL_PLUGIN='a b' expect_failure 'HARNESS_HERMES_OTEL_PLUGIN must be' metrics_enable_harness
  HARNESS_HERMES_OTEL_PLUGIN='briancaffey/hermes-otel/hermes_otel' metrics_enable_harness
  grep -Fxq 'hermes install briancaffey/hermes-otel/hermes_otel' "$ACTIONS"
}

plugin_ref_pins_the_install() {
  fixture
  M_TARGET=harness M_BACKEND=sqlite M_ENDPOINT="" M_CONTENT=off
  HARNESS_HERMES_OTEL_REF='main' expect_failure 'HARNESS_HERMES_OTEL_REF must be' metrics_enable_harness
  HARNESS_HERMES_OTEL_REF='ABCDEF0123456789abcdef0123456789abcdef01' expect_failure 'HARNESS_HERMES_OTEL_REF must be' metrics_enable_harness
  [[ ! -d "$HERMES_HOME/plugins/hermes_otel" ]]
  HARNESS_HERMES_OTEL_REF=f15b3e67fa9fd0e5ce9a08cf9cc8d7d2c356ceea metrics_enable_harness
  grep -Fxq 'hermes install hermes_otel --ref f15b3e67fa9fd0e5ce9a08cf9cc8d7d2c356ceea' "$ACTIONS"
}

router_file_is_not_world_writable() {
  [[ "$(uname -s)" == Linux ]] || { echo "# skipped: needs GNU stat"; return 0; }
  fixture
  local file="$HARNESS_IR_WORKSPACE_DIR/ir_metrics.jsonl"
  if [[ "$(metrics_router_host_gid)" == 0 ]]; then
    # Group 0 cannot be shared safely, so 664 must not silently become 666.
    expect_failure 'HARNESS_IR_TELEMETRY_FILE_MODE=666' metrics_router_apply true
    [[ "$(metrics_state_get router.enabled)" != true && ! -e "$file" ]]
    [[ -z "$(metrics_router_file_group)" ]]
    HARNESS_IR_TELEMETRY_FILE_MODE=666 metrics_router_apply true
    [[ "$(stat -c '%a' "$file")" == 666 ]]
  else
    metrics_router_apply true
    [[ "$(stat -c '%a' "$file")" == 664 ]]
    [[ "$(metrics_router_file_group)" == "$(id -g)" ]]
  fi
  HARNESS_IR_TELEMETRY_FILE_MODE=666 metrics_router_prepare_file
  [[ "$(stat -c '%a' "$file")" == 666 && -z "$(HARNESS_IR_TELEMETRY_FILE_MODE=666 metrics_router_file_group)" ]]
  HARNESS_IR_TELEMETRY_FILE_MODE=777 expect_failure 'must be 664 or 666' metrics_router_prepare_file
}

router_state_is_unchanged_when_file_preparation_fails() {
  fixture
  HARNESS_IR_TELEMETRY_FILE_MODE=666 HARNESS_IR_TELEMETRY_MAX_BYTES=big \
    expect_failure 'must be a non-negative integer' metrics_router_apply true
  [[ -z "$(metrics_state_get router.enabled)" && ! -e "$HARNESS_IR_WORKSPACE_DIR/ir_metrics.jsonl" ]]
  refute grep -q restart "$ACTIONS"
  if [[ "$(metrics_router_host_gid)" != 0 ]]; then
    TEST_DOCKER_LS_FAILS=1 expect_failure 'Cannot inspect Docker containers' metrics_router_apply true
    [[ -z "$(metrics_state_get router.enabled)" ]]
  fi
}

router_enable_rejects_a_container_without_the_group() {
  [[ "$(metrics_router_host_gid)" != 0 ]] || { echo "# skipped: root has no private group"; return 0; }
  fixture
  TEST_IR_GROUPADD='null' expect_failure 'cannot write the telemetry file' metrics_router_apply true
  [[ -z "$(metrics_state_get router.enabled)" && ! -e "$HARNESS_IR_WORKSPACE_DIR/ir_metrics.jsonl" ]]
  TEST_IR_GROUPADD='null' HARNESS_IR_TELEMETRY_FILE_MODE=666 metrics_router_apply true
  [[ "$(metrics_state_get router.enabled)" == true ]]
}

all_target_fails_before_touching_the_harness() {
  [[ "$(metrics_router_host_gid)" != 0 ]] || { echo "# skipped: root has no private group"; return 0; }
  fixture
  TEST_IR_GROUPADD='null' expect_failure 'cannot write the telemetry file' run_metrics_command enable --target all
  [[ ! -d "$HERMES_HOME/plugins/hermes_otel" && ! -e "$HERMES_HOME/hermes_otel.yaml" && -z "$(metrics_state_get harness.enabled)" ]]
}

remapped_docker_warns_about_the_664_file() {
  fixture
  local out
  out="$(metrics_router_warn_if_remapped 2>&1)"
  [[ -z "$out" ]]
  out="$(TEST_DOCKER_SECOPTS='[name=seccomp,profile=builtin name=rootless]' metrics_router_warn_if_remapped 2>&1)"
  grep -Fq 'HARNESS_IR_TELEMETRY_FILE_MODE=666' <<<"$out"
  out="$(TEST_DOCKER_SECOPTS='[name=userns]' metrics_router_warn_if_remapped 2>&1)"
  grep -Fq 'user-namespace remapping' <<<"$out"
  out="$(TEST_DOCKER_SECOPTS='[name=rootless]' HARNESS_IR_TELEMETRY_FILE_MODE=666 metrics_router_warn_if_remapped 2>&1)"
  [[ -z "$out" ]]
}

host_gid_ignores_a_switched_primary_group() {
  command -v getent >/dev/null || { echo "# skipped: getent not found"; return 0; }
  fixture
  local want
  want="$(getent passwd "$(id -un)" | cut -d: -f4)"
  # After a re-run under `sg docker`, `id -g` reports the docker group.
  [[ "$(id() { if [[ "${1:-}" == -g ]]; then echo 973; else command id "$@"; fi; }; metrics_router_host_gid)" == "$want" ]]
}

router_file_is_rotated_when_large() {
  fixture
  local file="$HARNESS_IR_WORKSPACE_DIR/ir_metrics.jsonl"
  printf '0123456789\n' >"$file"
  HARNESS_IR_TELEMETRY_MAX_BYTES=100 metrics_router_prepare_file
  [[ "$(cat "$file")" == 0123456789 && ! -e "$file.1" ]]
  HARNESS_IR_TELEMETRY_MAX_BYTES=5 metrics_router_prepare_file
  [[ -f "$file" && ! -s "$file" && "$(cat "$file.1")" == 0123456789 ]]
  [[ "$(uname -s)" != Linux || "$(stat -c '%a' "$file.1")" == 600 ]]
  # Only one previous generation is kept.
  printf 'abcdefghij\n' >"$file"
  HARNESS_IR_TELEMETRY_MAX_BYTES=5 metrics_router_prepare_file
  [[ "$(cat "$file.1")" == abcdefghij ]]
  # 0 turns rotation off.
  printf 'abcdefghij\n' >"$file"
  HARNESS_IR_TELEMETRY_MAX_BYTES=0 metrics_router_prepare_file
  [[ -s "$file" && "$(cat "$file.1")" == abcdefghij ]]
  HARNESS_IR_TELEMETRY_MAX_BYTES=big expect_failure 'must be a non-negative integer' metrics_router_prepare_file
  HARNESS_IR_TELEMETRY_MAX_BYTES=1234567890123456 expect_failure 'must be a non-negative integer' metrics_router_prepare_file
  # A leading zero is decimal, not (invalid) octal.
  printf 'abcdefghij\n' >"$file"
  HARNESS_IR_TELEMETRY_MAX_BYTES=08 metrics_router_prepare_file
  [[ ! -s "$file" && "$(cat "$file.1")" == abcdefghij ]]
  printf 'abcdefghij\n' >"$file"
  # Clean removes the rotated generation too, and a symlinked one is never followed.
  M_CLEAN=1
  metrics_disable_router
  [[ ! -e "$file.1" && ! -s "$file" ]]
  printf 'keep\n' >"$HOME/elsewhere"
  ln -s "$HOME/elsewhere" "$file.1"
  [[ -L "$file.1" ]] || { echo "# skipped: symlinks unavailable"; return 0; }
  refute metrics_clean_router
  expect_failure 'symlinked telemetry file' metrics_router_prepare_file
  [[ "$(cat "$HOME/elsewhere")" == keep ]]
}

sqlite_warns_about_exporter_env() {
  fixture
  M_TARGET=harness M_BACKEND=sqlite M_ENDPOINT="" M_CONTENT=off
  local out
  out="$(OTEL_JAEGER_ENDPOINT=http://x:4318 metrics_enable_harness)"
  grep -Fq 'OTEL_JAEGER_ENDPOINT' <<<"$out"
}

router_state_reverts_when_rewrite_fails() {
  fixture
  _metrics_router_rewrite_config_locked() { return 1; }
  expect_failure 'Could not update the Inference Router config' metrics_router_apply true
  [[ "$(metrics_state_get router.enabled)" == false ]]
}

harness_refuses_foreign_config() {
  fixture
  printf 'enabled: true\n' >"$HERMES_HOME/hermes_otel.yaml"
  M_TARGET=harness M_BACKEND=sqlite M_ENDPOINT="" M_CONTENT=off
  expect_failure 'not managed by this installer' metrics_enable_harness
  grep -Fxq 'enabled: true' "$HERMES_HOME/hermes_otel.yaml"
  metrics_disable_harness
  [[ -f "$HERMES_HOME/hermes_otel.yaml" ]]
}

unsupported_harness_is_reported() {
  fixture
  HARNESS_AGENT=hermes HARNESS_RUNTIME=openshell
  expect_failure 'no network egress' run_metrics_command enable --target harness
  # With --target all the Router is still configured and the harness skipped.
  local out
  out="$(run_metrics_command enable --target all)"
  grep -Fq 'Skipping the harness' <<<"$out"
  [[ "$(metrics_state_get router.enabled)" == true ]]
  # A supported agent whose CLI is missing is an error, not a silent skip.
  HARNESS_RUNTIME=host HARNESS_AGENT=openclaw
  if ! command -v openclaw >/dev/null; then
    expect_failure 'OpenClaw CLI not found' run_metrics_command enable --target harness
  fi
}

enable_keeps_saved_harness_settings() {
  fixture
  M_TARGET=harness M_BACKEND=jaeger M_ENDPOINT="" M_CONTENT=full
  metrics_enable_harness
  # A later 'enable' that names no harness flags (e.g. to turn the Router on) keeps them.
  : >"$ACTIONS"
  M_BACKEND="sqlite" M_CONTENT="off" M_BACKEND_GIVEN="" M_CONTENT_GIVEN=""
  metrics_enable_harness
  [[ "$(metrics_state_get harness.backend)" == jaeger && "$(metrics_state_get harness.content)" == full ]]
  [[ "$(metrics_state_get harness.managed_jaeger)" == true ]]
  grep -Fq 'type: jaeger' "$HERMES_HOME/hermes_otel.yaml"
  grep -Fxq 'content_capture: "full"' "$HERMES_HOME/hermes_otel.yaml"
  refute grep -q "docker rm" "$ACTIONS"
  # An explicitly named flag still wins.
  M_BACKEND=sqlite M_BACKEND_GIVEN=1
  metrics_enable_harness
  [[ "$(metrics_state_get harness.backend)" == sqlite && "$(metrics_state_get harness.content)" == full ]]
  grep -Fxq "docker rm $HARNESS_JAEGER_CONTAINER" "$ACTIONS"
}

foreign_config_fails_before_side_effects() {
  fixture
  printf 'enabled: true\n' >"$HERMES_HOME/hermes_otel.yaml"
  M_TARGET=harness M_BACKEND=jaeger M_ENDPOINT="" M_CONTENT=off
  expect_failure 'not managed by this installer' metrics_enable_harness
  [[ ! -s "$ACTIONS" ]]
  [[ "$(metrics_state_get harness.managed_jaeger)" != true ]]
}

managed_config_removal_is_marker_gated() {
  fixture
  M_TARGET=harness M_BACKEND=sqlite M_ENDPOINT="" M_CONTENT=off
  metrics_enable_harness
  metrics_remove_managed_config
  [[ ! -e "$HERMES_HOME/hermes_otel.yaml" ]]
  printf 'enabled: true\n' >"$HERMES_HOME/hermes_otel.yaml"
  metrics_remove_managed_config
  [[ -f "$HERMES_HOME/hermes_otel.yaml" ]]
}

parse_disable_options() {
  fixture
  metrics_parse_args disable
  [[ -z "$M_CLEAN" && -z "$M_KEEP_JAEGER" ]]
  metrics_parse_args disable --clean --target router
  [[ -n "$M_CLEAN" && "$M_TARGET" == router ]]
  metrics_parse_args disable --keep-jaeger
  [[ -n "$M_KEEP_JAEGER" && -z "$M_CLEAN" ]]
  expect_failure 'only valid with .observability disable' metrics_parse_args enable --clean
  expect_failure 'only valid with .observability disable' metrics_parse_args show --keep-jaeger
  expect_failure 'conflict' metrics_parse_args disable --clean --keep-jaeger
  expect_failure 'applies to the harness' metrics_parse_args disable --keep-jaeger --target router
  expect_failure 'Unknown option' metrics_parse_args disable --clean=1
}

router_disable_clean_is_opt_in() {
  fixture
  local file="$HARNESS_IR_WORKSPACE_DIR/ir_metrics.jsonl"
  metrics_router_apply true
  printf '{"event_type":"request_completed"}\n{"event_type":"request_completed"}\n' >"$file"
  M_CLEAN=""
  metrics_disable_router
  [[ "$(wc -l <"$file" | tr -d ' ')" == 2 ]]
  # The file is no longer written once the Router is back on memory telemetry.
  [[ "$(uname -s)" != Linux || "$(stat -c '%a' "$file")" == 600 ]]
  metrics_router_apply true
  [[ "$(uname -s)" != Linux || "$(stat -c '%a' "$file")" != 600 ]]
  M_CLEAN=1
  metrics_disable_router
  [[ -f "$file" && ! -s "$file" ]]
  [[ "$(metrics_state_get router.enabled)" == false ]]
  # A symlinked telemetry file must never be followed.
  printf 'keep\n' >"$HOME/elsewhere"
  rm -f "$file"
  ln -s "$HOME/elsewhere" "$file"
  [[ -L "$file" ]] || { echo "# skipped: symlinks unavailable"; return 0; }
  refute metrics_clean_router
  [[ "$(cat "$HOME/elsewhere")" == keep ]]
}

make_hermes_store() {
  python3 - "$HERMES_HOME/hermes_otel_live.db" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
con.execute("PRAGMA journal_mode=WAL")
con.execute("CREATE TABLE events (seq INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, ts INTEGER NOT NULL, "
            "data TEXT NOT NULL, trace_id TEXT, span_id TEXT, parent_span_id TEXT, session_id TEXT, name TEXT, "
            "status TEXT, start_ns INTEGER, end_ns INTEGER, duration_ms REAL, level INTEGER, logger TEXT, value REAL)")
rows = [("span", 1_700_000_000_000_000_000, "s1", "tool.read", "OK", 10.0),
        ("span", 1_700_000_001_000_000_000, "s1", "tool.read", "ERROR", 30.0),
        ("span", 1_700_000_002_000_000_000, "s2", "evil\x1b[31mname", "OK", 5.0),
        ("log", 1_700_000_003_000_000_000, None, None, None, None)]
for kind, ts, sess, name, status, dur in rows:
    con.execute("INSERT INTO events (kind, ts, data, session_id, name, status, duration_ms) VALUES (?,?,?,?,?,?,?)",
                (kind, ts, "{}", sess, name, status, dur))
con.commit()
con.close()
PY
}

harness_disable_clean_empties_store() {
  command -v python3 >/dev/null || { echo "# skipped: python3 not found"; return 0; }
  fixture
  local db="$HERMES_HOME/hermes_otel_live.db" out
  M_TARGET=harness M_BACKEND=sqlite M_ENDPOINT="" M_CONTENT=off
  metrics_enable_harness
  make_hermes_store
  out="$(metrics_show_harness_store "$db")"
  grep -Fq 'records: 4 (log=1, span=3); sessions: 2; error spans: 1' <<<"$out"
  grep -Fq 'tool.read: n=2 avg=20.0ms max=30.0ms' <<<"$out"
  refute grep -q $'\x1b' <<<"$out"
  M_CLEAN=""
  metrics_disable_harness
  [[ "$(sqlite_event_count "$db")" == 4 ]]
  metrics_enable_harness
  M_CLEAN=1
  metrics_disable_harness
  [[ -f "$db" && "$(sqlite_event_count "$db")" == 0 ]]
  out="$(metrics_show_harness_store "$db")"
  grep -Fq 'no records yet' <<<"$out"
  [[ ! -e "$HERMES_HOME/hermes_otel.yaml" ]]
}

sqlite_event_count() {
  python3 -c 'import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute("SELECT COUNT(*) FROM events").fetchone()[0])' "$1"
}

harness_keep_jaeger_on_disable() {
  fixture
  M_TARGET=harness M_BACKEND=jaeger M_ENDPOINT="" M_CONTENT=off
  metrics_enable_harness
  M_KEEP_JAEGER=1
  metrics_disable_harness
  refute grep -Fxq "docker rm $HARNESS_JAEGER_CONTAINER" "$ACTIONS"
  # The container is kept, but it is no longer the active backend.
  [[ "$(metrics_state_get harness.kept_jaeger)" == true && "$(metrics_state_get harness.managed_jaeger)" == false ]]
  [[ "$(metrics_state_get harness.enabled)" == false ]]
  M_KEEP_JAEGER=""
  metrics_disable_harness
  grep -Fxq "docker rm $HARNESS_JAEGER_CONTAINER" "$ACTIONS"
  [[ "$(metrics_state_get harness.kept_jaeger)" == false && "$(metrics_state_get harness.managed_jaeger)" == false ]]
}

kept_jaeger_survives_a_later_enable() {
  fixture
  M_TARGET=harness M_BACKEND=jaeger M_ENDPOINT="" M_CONTENT=off
  metrics_enable_harness
  M_KEEP_JAEGER=1
  metrics_disable_harness
  # e.g. 'observability enable --target all' later, defaulting the harness to sqlite
  M_BACKEND=sqlite M_ENDPOINT="" M_BACKEND_GIVEN="" M_CONTENT_GIVEN=""
  metrics_enable_harness
  refute grep -Fxq "docker rm $HARNESS_JAEGER_CONTAINER" "$ACTIONS"
  [[ "$(metrics_state_get harness.kept_jaeger)" == true && "$(metrics_state_get harness.managed_jaeger)" == false ]]
  # Actively switching to Jaeger uses the kept container again; switching away removes it.
  M_BACKEND=jaeger M_BACKEND_GIVEN=1
  metrics_enable_harness
  [[ "$(metrics_state_get harness.managed_jaeger)" == true && "$(metrics_state_get harness.kept_jaeger)" == false ]]
  M_BACKEND=sqlite
  metrics_enable_harness
  grep -Fxq "docker rm $HARNESS_JAEGER_CONTAINER" "$ACTIONS"
  [[ "$(metrics_state_get harness.managed_jaeger)" == false && "$(metrics_state_get harness.kept_jaeger)" == false ]]
}

disable_fails_when_the_plugin_cannot_be_disabled() {
  fixture
  M_TARGET=harness M_BACKEND=sqlite M_ENDPOINT="" M_CONTENT=off
  metrics_enable_harness
  TEST_HERMES_FAILS=disable expect_failure "plugins disable hermes_otel' failed" metrics_disable_harness
  # Neither the config nor the saved state claims the harness is off.
  [[ -f "$HERMES_HOME/hermes_otel.yaml" && "$(metrics_state_get harness.enabled)" == true ]]
  # Without the CLI the plugin cannot be disabled either.
  local command_exists_def
  command_exists_def="$(declare -f command_exists)"
  command_exists() { [[ "$1" != hermes ]] && command -v "$1" >/dev/null 2>&1; }
  expect_failure 'Hermes CLI not found' metrics_disable_harness
  [[ -f "$HERMES_HOME/hermes_otel.yaml" && "$(metrics_state_get harness.enabled)" == true ]]
  eval "$command_exists_def"
  # A failing command is accepted when the plugin is already reported disabled.
  TEST_HERMES_FAILS=disable TEST_HERMES_PLUGIN_STATE=disabled metrics_disable_harness
  [[ ! -e "$HERMES_HOME/hermes_otel.yaml" && "$(metrics_state_get harness.enabled)" == false ]]
}

wal_checkpoint_busy_is_reported() {
  command -v python3 >/dev/null || { echo "# skipped: python3 not found"; return 0; }
  fixture
  local db="$HERMES_HOME/hermes_otel_live.db" holder out
  make_hermes_store
  python3 - "$db" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
con.execute("PRAGMA journal_mode=WAL")
con.commit()
con.close()
PY
  # An open read transaction stops the checkpoint from truncating the WAL.
  python3 - "$db" "$HOME/reader-ready" <<'PY' &
import sqlite3, sys, time, pathlib
con = sqlite3.connect(sys.argv[1], isolation_level=None)
con.execute("BEGIN")
con.execute("SELECT COUNT(*) FROM events").fetchone()
pathlib.Path(sys.argv[2]).touch()
time.sleep(20)
PY
  holder=$!
  for _ in $(seq 1 50); do [[ -e "$HOME/reader-ready" ]] && break; sleep 0.1; done
  out="$( (metrics_clean_harness_store "$db") 2>&1 || true)"
  kill "$holder" 2>/dev/null || true
  wait "$holder" 2>/dev/null || true
  grep -Fq 'may still contain their text' <<<"$out"
  refute grep -Fq 'cleaned' <<<"$out"
}

all_target_rolls_the_router_back_when_the_harness_fails() {
  fixture
  local out
  # A bad harness option is caught before the Router is changed at all.
  HARNESS_HERMES_OTEL_REF=main expect_failure 'HARNESS_HERMES_OTEL_REF must be' run_metrics_command enable --target all
  [[ -z "$(metrics_state_get router.enabled)" ]]
  # A harness failure after the Router was changed reverts the Router.
  TEST_HERMES_FAILS=install expect_failure . run_metrics_command enable --target all
  [[ "$(metrics_state_get router.enabled)" == false ]]
  grep -Fq 'backend: "memory"' "$HARNESS_IR_WORKSPACE_DIR/config.yaml"
  # An already-enabled Router stays enabled.
  metrics_router_apply true
  TEST_HERMES_FAILS=install expect_failure . run_metrics_command enable --target all
  [[ "$(metrics_state_get router.enabled)" == true ]]
  out="$(run_metrics_command enable --target all 2>&1)"
  grep -Fq 'Harness telemetry enabled' <<<"$out"
}

all_target_disable_reaches_the_router_after_a_harness_failure() {
  fixture
  M_TARGET=harness M_BACKEND=sqlite M_ENDPOINT="" M_CONTENT=off
  metrics_enable_harness
  metrics_router_apply true
  TEST_HERMES_FAILS=disable expect_failure "plugins disable hermes_otel' failed" run_metrics_command disable --target all
  [[ "$(metrics_state_get router.enabled)" == false && "$(metrics_state_get harness.enabled)" == true ]]
}

content_capture_warns_for_remote_endpoints() {
  fixture
  local out
  M_TARGET=harness M_BACKEND=jaeger M_ENDPOINT=http://collector.example:4318/v1/traces M_CONTENT=full
  out="$(metrics_enable_harness 2>&1)"
  grep -Fq 'not on this machine' <<<"$out"
  M_ENDPOINT=http://localhost:4318/v1/traces
  out="$(metrics_enable_harness 2>&1)"
  refute grep -Fq 'not on this machine' <<<"$out"
  M_ENDPOINT=http://127.0.0.1.evil.example:4318/v1/traces
  out="$(metrics_enable_harness 2>&1)"
  grep -Fq 'not on this machine' <<<"$out"
  M_ENDPOINT='http://[::1]:4318/v1/traces'
  out="$(metrics_enable_harness 2>&1)"
  refute grep -Fq 'not on this machine' <<<"$out"
  M_ENDPOINT='http://[2001:db8::1]:4318/v1/traces'
  out="$(metrics_enable_harness 2>&1)"
  grep -Fq 'not on this machine' <<<"$out"
  M_ENDPOINT=http://collector.example:4318/v1/traces M_CONTENT=off
  out="$(metrics_enable_harness 2>&1)"
  refute grep -Fq 'not on this machine' <<<"$out"
}

clean_failures_are_reported() {
  fixture
  local file="$HARNESS_IR_WORKSPACE_DIR/ir_metrics.jsonl" out
  printf 'keep\n' >"$HOME/elsewhere"
  ln -s "$HOME/elsewhere" "$file"
  [[ -L "$file" ]] || { echo "# skipped: symlinks unavailable"; return 0; }
  M_CLEAN=1
  out="$(metrics_disable_router 2>&1)"
  grep -Fq 'was not cleaned' <<<"$out"
  refute grep -Fq 'and collected data cleaned' <<<"$out"
  ln -s "$HOME/elsewhere" "$HERMES_HOME/hermes_otel_live.db"
  refute metrics_clean_harness_store "$HERMES_HOME/hermes_otel_live.db"
  [[ "$(cat "$HOME/elsewhere")" == keep ]]
}

router_summary_lists_providers() {
  local out
  out="$(metrics_format_router_metrics <<'JSON'
{"token_metrics":{"overall":{"total_requests":3,"total_input_tokens":30,"total_output_tokens":9},
 "by_provider":{"ovms/Qwen3":{"request_count":2,"input_tokens":20,"output_tokens":6,"token_share":0.5},
                "ovms/we\u001b[31mird":{"request_count":1,"input_tokens":10,"output_tokens":3}}},
 "latency_metrics":{"overall":{"avg_latency_ms":12.5,"avg_ttft_ms":3,"avg_tpot_ms":1}}}
JSON
  )"
  grep -Fq 'requests=3 input_tokens=30 output_tokens=9' <<<"$out"
  grep -Fq 'ovms/Qwen3: requests=2 in=20 out=6 (50.0% of tokens)' <<<"$out"
  grep -Fq '(0.0% of tokens)' <<<"$out"
  refute grep -q $'\x1b' <<<"$out"
}

show_surfaces_a_failed_plugin_load() {
  fixture
  local out
  M_TARGET=harness M_BACKEND=sqlite M_ENDPOINT="" M_CONTENT=off
  metrics_enable_harness
  mkdir -p "$HERMES_HOME/logs"
  # No logs at all: nothing to warn about.
  out="$(metrics_show_harness 2>&1)"
  refute grep -Fq 'could not import its dependencies' <<<"$out"
  printf '2026-11-16 09:17:28,018 WARNING hermes_otel: [hermes-otel] OpenTelemetry import error: No module named opentelemetry.exporter\n' >"$HERMES_HOME/logs/errors.log"
  out="$(metrics_show_harness 2>&1)"
  grep -Fq 'could not import its dependencies' <<<"$out"
  grep -Fq 'hermes gateway restart' <<<"$out"
  # A later successful load clears it; an earlier one does not.
  printf '2026-11-16 09:17:34,118 INFO hermes_otel: [hermes-otel] Registered 15 hooks\n' >"$HERMES_HOME/logs/agent.log"
  out="$(metrics_show_harness 2>&1)"
  refute grep -Fq 'could not import its dependencies' <<<"$out"
  printf '2026-11-16 09:17:20,000 INFO hermes_otel: [hermes-otel] Registered 15 hooks\n' >"$HERMES_HOME/logs/agent.log"
  out="$(metrics_show_harness 2>&1)"
  grep -Fq 'could not import its dependencies' <<<"$out"
  # Not reported while the harness is disabled.
  metrics_disable_harness
  out="$(metrics_show_harness 2>&1)"
  refute grep -Fq 'could not import its dependencies' <<<"$out"
}

show_does_not_summarise_a_stale_store_under_jaeger() {
  fixture
  local out store
  M_TARGET=harness M_BACKEND=sqlite M_ENDPOINT="" M_CONTENT=off
  metrics_enable_harness
  store="$(metrics_harness_store "$M_AGENT")"
  mkdir -p "$(dirname "$store")"; : >"$store"
  out="$(metrics_show_harness 2>&1)"
  grep -Fq 'no records yet' <<<"$out"
  metrics_state_set harness.backend jaeger harness.endpoint http://127.0.0.1:4318/v1/traces
  out="$(metrics_show_harness 2>&1)"
  grep -Fq 'the local store is not written with this backend' <<<"$out"
  refute grep -Fq 'no records yet' <<<"$out"
}

# agent_fixture <agent> -- fixture with stub OpenClaw/dcode executables (the exporter
# commands run under `timeout`, which cannot call shell functions) and no real receiver.
agent_fixture() {
  fixture
  HARNESS_AGENT="$1"
  OPENCLAW_STATE_DIR="$HOME/openclaw"
  DEEPAGENTS_HOME="$HOME/dcode"
  export ACTIONS OPENCLAW_STATE_DIR DEEPAGENTS_HOME
  mkdir -p "$HOME/bin" "$OPENCLAW_STATE_DIR" "$DEEPAGENTS_HOME"
  PATH="$HOME/bin:$PATH"
  printf '#!/usr/bin/env bash\nexit 0\n' >"$HOME/bin/dcode"
  cat >"$HOME/bin/openclaw" <<'STUB'
#!/usr/bin/env bash
d="$HOME/oc-stub"; mkdir -p "$d"
case "$1 ${2:-}" in
  'plugins list') [[ ! -f "$d/plugin" ]] || printf '[{"id":"diagnostics-otel","status":"%s"}]\n' "$(cat "$d/plugin")" ;;
  'plugins install') printf 'openclaw install %s\n' "$3" >>"$ACTIONS"; echo enabled >"$d/plugin" ;;
  'plugins enable') printf 'openclaw enable\n' >>"$ACTIONS"; echo enabled >"$d/plugin" ;;
  'plugins disable') printf 'openclaw disable\n' >>"$ACTIONS"; echo disabled >"$d/plugin" ;;
  'config set')
    printf 'openclaw config set %s %s\n' "$3" "${4:-}" >>"$ACTIONS"
    case "$3" in
      diagnostics) echo true >"$d/otel" ;;
      diagnostics.otel.enabled) printf '%s\n' "$4" >"$d/otel" ;;
    esac ;;
  'config get') if [[ "$3" == diagnostics.otel.enabled && -f "$d/otel" ]]; then cat "$d/otel"; else exit 1; fi ;;
esac
STUB
  chmod +x "$HOME/bin/dcode" "$HOME/bin/openclaw"
  metrics_receiver_start() { printf 'receiver start %s %s %s\n' "$1" "$2" "$3" >>"$ACTIONS"; }
  metrics_receiver_stop() { printf 'receiver stop\n' >>"$ACTIONS"; }
  metrics_harness_check
}

openclaw_enable_disable() {
  agent_fixture openclaw
  [[ "$M_AGENT" == openclaw ]]
  M_TARGET=harness M_BACKEND=sqlite M_ENDPOINT="" M_CONTENT=full
  metrics_enable_harness
  grep -Fq 'openclaw install @openclaw/diagnostics-otel@' "$ACTIONS"
  grep -Fq "\"endpoint\":\"http://127.0.0.1:${HARNESS_OTLP_RECEIVER_PORT}\"" "$ACTIONS"
  grep -Fq '"captureContent":true' "$ACTIONS"
  grep -Fxq "receiver start openclaw $OPENCLAW_STATE_DIR/openclaw_otel_live.db full" "$ACTIONS"
  [[ "$(metrics_state_get harness.enabled)" == true && "$(metrics_state_get harness.agent)" == openclaw ]]
  metrics_disable_harness
  grep -Fxq 'openclaw config set diagnostics.otel.enabled false' "$ACTIONS"
  grep -Fxq 'openclaw disable' "$ACTIONS"
  grep -Fxq 'receiver stop' "$ACTIONS"
  [[ "$(metrics_state_get harness.enabled)" == false ]]
  # The plugin stays installed but disabled; a later enable must turn it back on.
  : >"$ACTIONS"
  metrics_enable_harness
  refute grep -Fq 'openclaw install' "$ACTIONS"
  grep -Fxq 'openclaw enable' "$ACTIONS"
  [[ "$(metrics_state_get harness.enabled)" == true ]]
}

openclaw_jaeger_and_foreign_exporter() {
  agent_fixture openclaw
  M_TARGET=harness M_BACKEND=jaeger M_ENDPOINT="" M_CONTENT=off
  metrics_enable_harness
  grep -Fq "\"endpoint\":\"http://127.0.0.1:${HARNESS_JAEGER_OTLP_PORT}\"" "$ACTIONS"
  grep -Fq '"captureContent":false' "$ACTIONS"
  refute grep -Fq 'receiver start' "$ACTIONS"
  M_CONTENT=preview
  expect_failure 'needs --backend sqlite' metrics_resolve_harness_settings
  # An exporter this installer did not configure is never overwritten.
  agent_fixture openclaw
  mkdir -p "$HOME/oc-stub"
  echo true >"$HOME/oc-stub/otel"
  M_TARGET=harness M_BACKEND=sqlite M_ENDPOINT="" M_CONTENT=off
  expect_failure 'already has diagnostics.otel enabled' metrics_enable_harness
  refute grep -Fq 'openclaw install' "$ACTIONS"
  refute grep -Fq 'receiver start' "$ACTIONS"
}

dcode_env_block_lifecycle() {
  agent_fixture deepagents-code
  local env="$DEEPAGENTS_HOME/.env"
  printf 'USER_KEY=keep\n' >"$env"
  M_TARGET=harness M_BACKEND=sqlite M_ENDPOINT="" M_CONTENT=off
  metrics_enable_harness
  grep -Fxq 'USER_KEY=keep' "$env"
  grep -Fxq 'LANGSMITH_TRACING_MODE=otel' "$env"
  grep -Fxq "OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:${HARNESS_OTLP_RECEIVER_PORT}" "$env"
  grep -Fxq 'LANGSMITH_HIDE_INPUTS=true' "$env"
  grep -Fxq 'LANGSMITH_HIDE_OUTPUTS=true' "$env"
  [[ "$(stat -c %a "$env")" == 600 ]]
  grep -Fxq "receiver start dcode $DEEPAGENTS_HOME/dcode_otel_live.db off" "$ACTIONS"
  # Re-enabling replaces the block instead of adding a second one.
  M_BACKEND=jaeger M_CONTENT=full
  metrics_enable_harness
  [[ "$(grep -Fxc "$METRICS_ENV_BEGIN" "$env")" == 1 ]]
  grep -Fxq "OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:${HARNESS_JAEGER_OTLP_PORT}" "$env"
  refute grep -Fq 'LANGSMITH_HIDE' "$env"
  grep -Fxq 'receiver stop' "$ACTIONS"
  metrics_disable_harness
  [[ "$(cat "$env")" == USER_KEY=keep ]]
  [[ "$(metrics_state_get harness.enabled)" == false ]]
  # A file that held only the block goes away with it.
  rm -f "$env"
  M_BACKEND=sqlite M_CONTENT=off
  metrics_enable_harness
  [[ -f "$env" ]]
  metrics_disable_harness
  [[ ! -e "$env" ]]
}

dcode_refuses_foreign_env() {
  agent_fixture deepagents-code
  local env="$DEEPAGENTS_HOME/.env"
  M_TARGET=harness M_BACKEND=sqlite M_ENDPOINT="" M_CONTENT=off
  printf 'LANGSMITH_TRACING=true\n' >"$env"
  expect_failure 'did not write' metrics_enable_harness
  [[ "$(cat "$env")" == LANGSMITH_TRACING=true ]]
  refute grep -Fq 'receiver start' "$ACTIONS"
  rm -f "$env"
  printf 'keep\n' >"$HOME/elsewhere"
  ln -s "$HOME/elsewhere" "$env" || { echo "# skipped: symlinks unavailable"; return 0; }
  expect_failure 'symlink' metrics_enable_harness
  [[ "$(cat "$HOME/elsewhere")" == keep ]]
  # Variables outside an existing managed block, with or without spaces before '=', are refused too.
  rm -f "$env"
  metrics_enable_harness
  printf 'OTEL_SERVICE_NAME = mine\n' >>"$env"
  expect_failure 'did not write' metrics_enable_harness
}

openclaw_disable_needs_installer_ownership() {
  agent_fixture openclaw
  mkdir -p "$HOME/oc-stub"
  echo enabled >"$HOME/oc-stub/plugin"
  echo true >"$HOME/oc-stub/otel"
  # No recorded enable: the user's own exporter and plugin stay as they are.
  metrics_disable_harness
  refute grep -Fq 'openclaw config set' "$ACTIONS"
  refute grep -Fq 'openclaw disable' "$ACTIONS"
  [[ "$(cat "$HOME/oc-stub/otel")" == true ]]
}

only_one_harness_exporter_is_recorded() {
  agent_fixture deepagents-code
  local out
  M_TARGET=harness M_BACKEND=sqlite M_ENDPOINT="" M_CONTENT=off
  metrics_enable_harness
  # Another agent cannot be enabled while dcode's exporter is on.
  M_AGENT=openclaw
  expect_failure 'enabled for Deep Agents Code' metrics_enable_harness
  refute grep -Fq 'openclaw install' "$ACTIONS"
  # Show and disable follow the recorded owner, whichever agent is selected.
  out="$(metrics_show_harness 2>&1)"
  grep -Fq 'Enabled for Deep Agents Code' <<<"$out"
  M_AGENT=openclaw
  metrics_disable_harness
  refute grep -Fq 'LANGSMITH_TRACING' "$DEEPAGENTS_HOME/.env" 2>/dev/null
  [[ "$(metrics_state_get harness.enabled)" == false ]]
  M_AGENT=openclaw
  metrics_enable_harness
  [[ "$(metrics_state_get harness.agent)" == openclaw ]]
}

openclaw_failed_enable_can_be_disabled() {
  agent_fixture openclaw
  M_TARGET=harness M_BACKEND=sqlite M_ENDPOINT="" M_CONTENT=off
  metrics_write_openclaw_otel_config() { return 1; }
  expect_failure '' metrics_enable_harness
  [[ "$(metrics_state_get harness.enabled)" == true && "$(metrics_state_get harness.agent)" == openclaw ]]
  : >"$ACTIONS"
  metrics_disable_harness
  grep -Fxq 'openclaw config set diagnostics.otel.enabled false' "$ACTIONS"
  grep -Fxq 'receiver stop' "$ACTIONS"
}

receiver_stores_filtered_spans() {
  command -v python3 >/dev/null || { echo "# skipped: python3 not found"; return 0; }
  python3 - "$SCRIPT_DIR/scripts/lib/metrics-otlp-receiver.py" "$TEST_ROOT" <<'PY'
import gzip, http.client, socket, sqlite3, struct, subprocess, sys, time, urllib.error, urllib.request

script, root = sys.argv[1:3]
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))


def varint(n):
    out = b""
    while n > 0x7F:
        out += bytes([n & 0x7F | 0x80])
        n >>= 7
    return out + bytes([n])


def ld(field, body):
    return varint(field << 3 | 2) + varint(len(body)) + body


def span(name, attrs, parent=b"", status=0):
    m = ld(1, b"\xaa" * 16) + ld(2, b"\x01" * 8) + (ld(4, parent) if parent else b"") + ld(5, name.encode())
    m += varint(7 << 3 | 1) + struct.pack("<Q", 1_000_000) + varint(8 << 3 | 1) + struct.pack("<Q", 3_000_000)
    for key, val in attrs.items():
        m += ld(9, ld(1, key.encode()) + ld(2, ld(1, val.encode())))
    return m + (ld(15, varint(3 << 3) + varint(status)) if status else b"")


def request(*spans):
    return ld(1, ld(2, b"".join(ld(2, s) for s in spans)))


def start(agent, content, db):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    proc = subprocess.Popen([sys.executable, script, "--port", str(port), "--db", db, "--agent", agent, "--content", content])
    for _ in range(100):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1)
            return proc, port
        except OSError:
            time.sleep(0.1)
    proc.kill()
    raise SystemExit("receiver did not start")


def post(port, body, ctype="application/x-protobuf", path="/v1/traces", headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, headers={"Content-Type": ctype, **(headers or {})})
    try:
        return urllib.request.urlopen(req, timeout=5).status
    except urllib.error.HTTPError as e:
        return e.code


def rows(db):
    con = sqlite3.connect(db)
    try:
        return con.execute("SELECT name, status, duration_ms, data, parent_span_id FROM events ORDER BY seq").fetchall()
    finally:
        con.close()


def run(agent, content, body_fn):
    db = f"{root}/{agent}-{content}.db"
    proc, port = start(agent, content, db)
    try:
        body_fn(port)
    finally:
        proc.terminate()
        proc.wait(10)
    return rows(db)


prompt = {"gen_ai.prompt": "x" * 500, "gen_ai.tool.call.arguments": "y" * 500, "gen_ai.system_instructions": "z" * 500, "openclaw.model": "m"}
oc = request(span("openclaw.run", prompt), span("openclaw.model.call", {}, status=2), span("http.noise", {}))


def oc_body(port):
    assert post(port, oc) == 200
    assert post(port, gzip.compress(oc), headers={"Content-Encoding": "gzip"}) == 200
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", "/v1/traces", body=iter([oc[:7], oc[7:]]), headers={"Content-Type": "application/x-protobuf"}, encode_chunked=True)
    assert conn.getresponse().status == 200
    conn.close()
    assert post(port, b"{}", "application/json") == 415
    assert post(port, oc, path="/other") == 404
    assert post(port, b"\xff\xff") == 400
    # A negative length or an oversized chunk is refused before any body is read.
    for extra, tail in ((b"Content-Length: -1\r\n", b""), (b"Transfer-Encoding: chunked\r\n", b"ffffffff\r\n")):
        s = socket.create_connection(("127.0.0.1", port), timeout=5)
        s.sendall(b"POST /v1/traces HTTP/1.1\r\nHost: x\r\nContent-Type: application/x-protobuf\r\n" + extra + b"\r\n" + tail)
        assert b" 400 " in s.recv(64), extra
        s.close()


for content in ("off", "preview", "full"):
    got = run("openclaw", content, oc_body)
    # Three posts, two kept spans each; the unrelated span is dropped.
    assert [r[0] for r in got] == ["openclaw.run", "openclaw.model.call"] * 3, got
    run_row, call_row = got[0], got[1]
    assert call_row[1] == "ERROR" and run_row[1] == "OK" and run_row[2] == 2.0, got
    assert "openclaw.model" in run_row[3]
    if content == "off":
        assert "gen_ai.prompt" not in run_row[3]
        assert "gen_ai.tool.call.arguments" not in run_row[3] and "gen_ai.system_instructions" not in run_row[3]
    elif content == "preview":
        assert "x" * 200 in run_row[3] and "x" * 201 not in run_row[3]
        assert "y" * 200 in run_row[3] and "y" * 201 not in run_row[3]
    else:
        assert "x" * 500 in run_row[3] and "y" * 500 in run_row[3]

dc = request(
    span("agent", {}),
    span("ChatOpenAI", {"langsmith.span.kind": "llm"}, parent=b"\x02" * 8),
    span("Middleware.before_agent", {"langsmith.span.kind": "chain"}, parent=b"\x02" * 8),
)
got = run("dcode", "off", lambda port: post(port, dc) == 200 or sys.exit("post failed"))
assert [r[0] for r in got] == ["agent", "ChatOpenAI"], got
print("receiver ok")
PY
}

dispatch() {
  fixture
  with_deployment_lock() { printf 'lock\n' >>"$ACTIONS"; "$@"; }
  run_metrics_command() { printf 'metrics %s\n' "$*" >>"$ACTIONS"; }
  (main observability show --target router)
  (main --runtime openshell observability enable --target router)
  cmp "$ACTIONS" <(printf 'metrics show --target router\nlock\nmetrics enable --target router\n')
  expect_failure 'Unknown command: metrics' main metrics show --target router
}

run_case 'metrics flags default and parse in both --flag value and --flag=value form' parse_defaults
run_case 'metrics rejects invalid, unsafe and misplaced arguments' parse_rejections
run_case 'router enable/disable rewrites only the telemetry block and restarts IR' router_toggle
run_case 'router telemetry choice survives config regeneration' router_setting_survives_config_regeneration
run_case 'router change is deferred when IR has no generated config' router_without_config_defers
run_case 'router rewrite keeps blocks that follow telemetry' router_rewrite_keeps_blocks_after_telemetry
run_case 'harness enable/disable manages plugin, config and state' harness_enable_disable
run_case 'harness jaeger without endpoint uses and cleans up the managed container' harness_managed_jaeger
run_case 'harness refuses to overwrite an unmanaged hermes_otel.yaml' harness_refuses_foreign_config
run_case 'existing Jaeger container that is not loopback-only on exactly the two ports is rejected' jaeger_port_mismatch_is_rejected
run_case 'plugin source reference is validated' plugin_source_is_validated
run_case 'HARNESS_HERMES_OTEL_REF pins the plugin install to an exact commit' plugin_ref_pins_the_install
run_case 'router telemetry file is group-writable, not world-writable, unless 666 is chosen' router_file_is_not_world_writable
run_case 'router enable rejects an existing container that cannot write the file' router_enable_rejects_a_container_without_the_group
run_case '--target all checks the Router before touching the harness' all_target_fails_before_touching_the_harness
run_case 'the Router group id is the account primary group, not the current effective one' host_gid_ignores_a_switched_primary_group
run_case 'rootless or remapped Docker warns that the 664 file may not be writable' remapped_docker_warns_about_the_664_file
run_case 'router telemetry file is rotated once and cleaned with --clean' router_file_is_rotated_when_large
run_case 'sqlite backend warns about exporter env vars' sqlite_warns_about_exporter_env
run_case 'router state reverts when the config rewrite fails' router_state_reverts_when_rewrite_fails
run_case 'OpenShell runtime and a missing agent CLI are reported, router still applied for --target all' unsupported_harness_is_reported
run_case 'observability show skips the deployment lock; mutations take it, in any runtime' dispatch
run_case 'show warns when the last Hermes process could not load the plugin' show_surfaces_a_failed_plugin_load
run_case 'show does not summarise a stale local store under the jaeger backend' show_does_not_summarise_a_stale_store_under_jaeger
run_case 'enable without harness flags keeps the saved harness settings' enable_keeps_saved_harness_settings
run_case 'a foreign hermes_otel.yaml fails before Jaeger or the plugin is touched' foreign_config_fails_before_side_effects
run_case 'managed-config removal only touches files this installer wrote' managed_config_removal_is_marker_gated
run_case 'disable takes --clean and --keep-jaeger; misuse is rejected' parse_disable_options
run_case 'router disable keeps the JSONL unless --clean, and never follows a symlink' router_disable_clean_is_opt_in
run_case 'harness disable --clean empties the store in place; show summarises it' harness_disable_clean_empties_store
run_case 'disable --keep-jaeger keeps the managed container until a later disable' harness_keep_jaeger_on_disable
run_case 'a kept Jaeger survives a later enable that does not use it' kept_jaeger_survives_a_later_enable
run_case 'a failed --clean is reported, not claimed as done' clean_failures_are_reported
run_case 'content capture warns when the endpoint is not local' content_capture_warns_for_remote_endpoints
run_case 'router summary lists providers and sanitises names' router_summary_lists_providers
run_case 'a Jaeger container this installer did not create is never reused or removed' foreign_jaeger_is_never_reused_or_removed
run_case 'a failed Docker query is an error, not an absent container' docker_query_failure_is_not_absence
run_case 'a rejected endpoint is not echoed back' rejected_endpoint_is_not_echoed
run_case 'saved harness settings are resolved before the arguments are validated' saved_settings_are_resolved_before_validation
run_case 'router state is unchanged when file preparation fails' router_state_is_unchanged_when_file_preparation_fails
run_case 'disable fails, keeping state, when the plugin cannot be disabled' disable_fails_when_the_plugin_cannot_be_disabled
run_case 'a busy WAL checkpoint makes --clean report the leftover text' wal_checkpoint_busy_is_reported
run_case '--target all validates up front and reverts the Router if the harness fails' all_target_rolls_the_router_back_when_the_harness_fails
run_case '--target all disable still disables the Router when the harness cannot be disabled' all_target_disable_reaches_the_router_after_a_harness_failure
run_case 'OpenClaw plugin lifecycle: install once, re-enable after disable, receiver follows the backend' openclaw_enable_disable
run_case 'OpenClaw with Jaeger, preview rejected, a foreign diagnostics exporter is never overwritten' openclaw_jaeger_and_foreign_exporter
run_case 'dcode .env block is managed, replaced in place and removed without touching user lines' dcode_env_block_lifecycle
run_case 'dcode refuses a .env with its own tracing variables or a symlink' dcode_refuses_foreign_env
run_case 'OTLP receiver decodes, filters and stores spans per agent and content mode' receiver_stores_filtered_spans
run_case 'OpenClaw disable only touches an exporter this installer enabled' openclaw_disable_needs_installer_ownership
run_case 'one harness exporter is recorded; enable for another agent is refused and disable follows the owner' only_one_harness_exporter_is_recorded
run_case 'a failed OpenClaw enable is recorded so disable can clean it up' openclaw_failed_enable_can_be_disabled
finish_tests
