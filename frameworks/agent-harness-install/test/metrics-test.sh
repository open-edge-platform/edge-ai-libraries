#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Unit tests for `./install.sh metrics <enable|disable|show>` (scripts/lib/metrics.sh).
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
            *) printf 'true\n' ;;
          esac
        fi ;;
      info) printf '%s\n' "${TEST_DOCKER_SECOPTS-[name=apparmor name=seccomp,profile=builtin name=cgroupns]}" ;;
      restart | rm | start | run | pull) printf 'docker %s %s\n' "$1" "${*: -1}" >>"$ACTIONS" ;;
      image) return 0 ;;
      port)
        case "$3" in
          16686/tcp) printf '127.0.0.1:%s\n' "${TEST_JAEGER_UI_PUBLISHED:-$HARNESS_JAEGER_UI_PORT}" ;;
          4318/tcp) printf '127.0.0.1:%s\n' "$HARNESS_JAEGER_OTLP_PORT" ;;
        esac ;;
    esac
  }
  hermes() {
    case "$1 ${2:-}" in
      'plugins install') mkdir -p "$HERMES_HOME/plugins/hermes_otel"; printf 'hermes install %s%s\n' "$3" "${4:+ $4 $5}" >>"$ACTIONS" ;;
      'plugins enable') printf 'hermes enable\n' >>"$ACTIONS" ;;
      'plugins disable') printf 'hermes disable\n' >>"$ACTIONS" ;;
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
  expect_failure '--content must be' metrics_parse_args enable --content all
  expect_failure 'requires --endpoint' metrics_parse_args enable --backend otlp
  expect_failure 'cannot be combined with --backend sqlite' \
    metrics_parse_args enable --endpoint http://h:4318/v1/traces
  expect_failure 'plain http\(s\) URL' \
    metrics_parse_args enable --backend otlp --endpoint 'http://user:pw@h:4318/v1/traces'
  expect_failure 'plain http\(s\) URL' \
    metrics_parse_args enable --backend otlp --endpoint 'http://h:4318/v1/traces?token=x'
  expect_failure 'only valid with .metrics enable' metrics_parse_args disable --backend jaeger
  expect_failure 'apply to the harness' metrics_parse_args enable --target router --content full
  expect_failure 'requires a value' metrics_parse_args enable --endpoint
  expect_failure 'given more than once' metrics_parse_args enable --backend sqlite --backend=jaeger
  expect_failure 'given more than once' metrics_parse_args show --target router --target all
  expect_failure 'port must be between' \
    metrics_parse_args enable --backend otlp --endpoint http://h:99999/v1/traces
  expect_failure 'port must be between' \
    metrics_parse_args enable --backend otlp --endpoint 'http://[::1]:0/v1/traces'
  metrics_parse_args enable --backend otlp --endpoint 'http://[::1]:4318/v1/traces'
  [[ "$M_ENDPOINT" == 'http://[::1]:4318/v1/traces' ]]
  metrics_parse_args enable --backend otlp --endpoint http://h:65535
  expect_failure 'plain http\(s\) URL' \
    metrics_parse_args enable --backend otlp --endpoint 'http://[::1]x:4318/v1/traces'
}

router_toggle() {
  fixture
  local cfg="$HARNESS_IR_WORKSPACE_DIR/config.yaml"
  metrics_router_apply true
  grep -Fq 'backend: "file"' "$cfg"
  grep -Fq 'file_path: "/app/telemetry.jsonl"' "$cfg"
  grep -Fq 'policy: "Balanced"' "$cfg"
  [[ -f "$HARNESS_IR_WORKSPACE_DIR/telemetry.jsonl" ]]
  [[ "$(metrics_state_get router.enabled)" == true ]]
  [[ "$(grep -c '^telemetry:' "$cfg")" == 1 ]]
  grep -Fxq "docker restart $HARNESS_IR_CONTAINER" "$ACTIONS"
  metrics_router_apply false
  grep -Fq 'backend: "memory"' "$cfg"
  ! grep -Fq 'file_path' "$cfg"
  [[ "$(metrics_state_get router.enabled)" == false ]]
  [[ -f "$HARNESS_IR_WORKSPACE_DIR/telemetry.jsonl" ]]
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
  ! grep -q restart "$ACTIONS"
}

harness_enable_disable() {
  fixture
  local cfg="$HERMES_HOME/hermes_otel.yaml"
  M_TARGET=harness M_BACKEND=otlp M_ENDPOINT=http://collector:4318/v1/traces M_CONTENT=preview
  metrics_enable_harness
  grep -Fxq 'hermes install hermes_otel' "$ACTIONS"
  grep -Fxq 'hermes enable' "$ACTIONS"
  grep -Fxq 'content_capture: "preview"' "$cfg"
  grep -Fq 'type: otlp' "$cfg"
  grep -Fq 'endpoint: "http://collector:4318/v1/traces"' "$cfg"
  [[ "$(uname -s)" != Linux || "$(stat -c '%a' "$cfg")" == 600 ]]
  [[ "$(metrics_state_get harness.backend)" == otlp ]]
  # sqlite means no exporter entry, and "off" must stay a quoted string.
  M_BACKEND=sqlite M_ENDPOINT="" M_CONTENT=off
  metrics_enable_harness
  grep -Fxq 'content_capture: "off"' "$cfg"
  ! grep -q 'backends:' "$cfg"
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
  TEST_JAEGER_UI_PUBLISHED=1 expect_failure 'does not publish port' metrics_enable_harness
  [[ ! -e "$HERMES_HOME/hermes_otel.yaml" ]]
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
  local file="$HARNESS_IR_WORKSPACE_DIR/telemetry.jsonl" want=664
  [[ "$(id -g)" != 0 ]] || want=666
  metrics_router_apply true
  [[ "$(stat -c '%a' "$file")" == "$want" ]]
  [[ "$(metrics_router_file_group)" == "$([[ $want == 664 ]] && id -g || true)" ]]
  HARNESS_IR_TELEMETRY_FILE_MODE=666 metrics_router_prepare_file
  [[ "$(stat -c '%a' "$file")" == 666 && -z "$(HARNESS_IR_TELEMETRY_FILE_MODE=666 metrics_router_file_group)" ]]
  HARNESS_IR_TELEMETRY_FILE_MODE=777 expect_failure 'must be 664 or 666' metrics_router_prepare_file
}

router_enable_rejects_a_container_without_the_group() {
  [[ "$(metrics_router_host_gid)" != 0 ]] || { echo "# skipped: root has no private group"; return 0; }
  fixture
  TEST_IR_GROUPADD='null' expect_failure 'without access to group' metrics_router_apply true
  [[ -z "$(metrics_state_get router.enabled)" && ! -e "$HARNESS_IR_WORKSPACE_DIR/telemetry.jsonl" ]]
  TEST_IR_GROUPADD='null' HARNESS_IR_TELEMETRY_FILE_MODE=666 metrics_router_apply true
  [[ "$(metrics_state_get router.enabled)" == true ]]
}

all_target_fails_before_touching_the_harness() {
  [[ "$(metrics_router_host_gid)" != 0 ]] || { echo "# skipped: root has no private group"; return 0; }
  fixture
  TEST_IR_GROUPADD='null' expect_failure 'without access to group' run_metrics_command enable --target all
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
  local file="$HARNESS_IR_WORKSPACE_DIR/telemetry.jsonl"
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
  ! metrics_clean_router
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
  HARNESS_AGENT=openclaw
  expect_failure 'only Hermes is supported' run_metrics_command enable --target harness
  # With --target all the Router is still configured and the harness skipped.
  local out
  out="$(run_metrics_command enable --target all)"
  grep -Fq 'Skipping the harness' <<<"$out"
  [[ "$(metrics_state_get router.enabled)" == true ]]
  HARNESS_AGENT=hermes HARNESS_RUNTIME=openshell
  expect_failure 'no network egress' run_metrics_command enable --target harness
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
  ! grep -q "docker rm" "$ACTIONS"
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
  expect_failure 'only valid with .metrics disable' metrics_parse_args enable --clean
  expect_failure 'only valid with .metrics disable' metrics_parse_args show --keep-jaeger
  expect_failure 'conflict' metrics_parse_args disable --clean --keep-jaeger
  expect_failure 'applies to the harness' metrics_parse_args disable --keep-jaeger --target router
  expect_failure 'Unknown option' metrics_parse_args disable --clean=1
}

router_disable_clean_is_opt_in() {
  fixture
  local file="$HARNESS_IR_WORKSPACE_DIR/telemetry.jsonl"
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
  ! metrics_clean_router
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
  ! grep -q $'\x1b' <<<"$out"
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
  ! grep -Fxq "docker rm $HARNESS_JAEGER_CONTAINER" "$ACTIONS"
  [[ "$(metrics_state_get harness.managed_jaeger)" == true && "$(metrics_state_get harness.enabled)" == false ]]
  M_KEEP_JAEGER=""
  metrics_disable_harness
  grep -Fxq "docker rm $HARNESS_JAEGER_CONTAINER" "$ACTIONS"
  [[ "$(metrics_state_get harness.managed_jaeger)" == false ]]
}

kept_jaeger_survives_a_later_enable() {
  fixture
  M_TARGET=harness M_BACKEND=jaeger M_ENDPOINT="" M_CONTENT=off
  metrics_enable_harness
  M_KEEP_JAEGER=1
  metrics_disable_harness
  # e.g. 'metrics enable --target all' later, defaulting the harness to sqlite
  M_BACKEND=sqlite M_ENDPOINT="" M_BACKEND_GIVEN="" M_CONTENT_GIVEN=""
  metrics_enable_harness
  ! grep -Fxq "docker rm $HARNESS_JAEGER_CONTAINER" "$ACTIONS"
  [[ "$(metrics_state_get harness.managed_jaeger)" == true ]]
  # Actively switching away from a Jaeger that is in use still removes it.
  M_BACKEND=jaeger M_BACKEND_GIVEN=1
  metrics_enable_harness
  M_BACKEND=sqlite
  metrics_enable_harness
  grep -Fxq "docker rm $HARNESS_JAEGER_CONTAINER" "$ACTIONS"
  [[ "$(metrics_state_get harness.managed_jaeger)" == false ]]
}

content_capture_warns_for_remote_endpoints() {
  fixture
  local out
  M_TARGET=harness M_BACKEND=otlp M_ENDPOINT=http://collector.example:4318/v1/traces M_CONTENT=full
  out="$(metrics_enable_harness 2>&1)"
  grep -Fq 'not on this machine' <<<"$out"
  M_ENDPOINT=http://localhost:4318/v1/traces
  out="$(metrics_enable_harness 2>&1)"
  ! grep -Fq 'not on this machine' <<<"$out"
  M_ENDPOINT=http://127.0.0.1.evil.example:4318/v1/traces
  out="$(metrics_enable_harness 2>&1)"
  grep -Fq 'not on this machine' <<<"$out"
  M_ENDPOINT='http://[::1]:4318/v1/traces'
  out="$(metrics_enable_harness 2>&1)"
  ! grep -Fq 'not on this machine' <<<"$out"
  M_ENDPOINT='http://[2001:db8::1]:4318/v1/traces'
  out="$(metrics_enable_harness 2>&1)"
  grep -Fq 'not on this machine' <<<"$out"
  M_ENDPOINT=http://collector.example:4318/v1/traces M_CONTENT=off
  out="$(metrics_enable_harness 2>&1)"
  ! grep -Fq 'not on this machine' <<<"$out"
}

clean_failures_are_reported() {
  fixture
  local file="$HARNESS_IR_WORKSPACE_DIR/telemetry.jsonl" out
  printf 'keep\n' >"$HOME/elsewhere"
  ln -s "$HOME/elsewhere" "$file"
  M_CLEAN=1
  out="$(metrics_disable_router 2>&1)"
  grep -Fq 'was not cleaned' <<<"$out"
  ! grep -Fq 'and collected data cleaned' <<<"$out"
  ln -s "$HOME/elsewhere" "$HERMES_HOME/hermes_otel_live.db"
  ! metrics_clean_harness_store "$HERMES_HOME"
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
  ! grep -q $'\x1b' <<<"$out"
}

dispatch() {
  fixture
  with_deployment_lock() { printf 'lock\n' >>"$ACTIONS"; "$@"; }
  run_metrics_command() { printf 'metrics %s\n' "$*" >>"$ACTIONS"; }
  (main metrics show --target router)
  (main --runtime openshell metrics enable --target router)
  cmp "$ACTIONS" <(printf 'metrics show --target router\nlock\nmetrics enable --target router\n')
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
run_case 'existing Jaeger container with other ports is rejected' jaeger_port_mismatch_is_rejected
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
run_case 'unsupported harness/runtime is reported, router still applied for --target all' unsupported_harness_is_reported
run_case 'metrics show skips the deployment lock; mutations take it, in any runtime' dispatch
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
finish_tests
