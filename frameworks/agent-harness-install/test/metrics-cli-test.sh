#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# CLI-level test for `./install.sh metrics <enable|disable|show>`: runs the real
# entry point as a subprocess (argument parsing, deployment lock, dispatch, exit
# codes) against stateful fake `docker`, `hermes` and `flock` executables.
# Nothing touches the host; it does not replace a run on a real Docker host.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf -- "$TEST_ROOT"' EXIT

FAKE="$TEST_ROOT/fake"
BIN="$TEST_ROOT/bin"
export HOME="$TEST_ROOT/home"
export HERMES_HOME="$HOME/hermes"
export HARNESS_IR_WORKSPACE_DIR="$HOME/ir"
export HARNESS_AGENT=hermes
export HARNESS_RUNTIME=host
export HARNESS_BIND_HOST=127.0.0.1
export FAKE
mkdir -p "$BIN" "$FAKE/containers" "$FAKE/plugin" "$HERMES_HOME" "$HARNESS_IR_WORKSPACE_DIR"

cat >"$BIN/flock" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

cat >"$BIN/docker" <<'EOF'
#!/usr/bin/env bash
c="$FAKE/containers"
printf 'docker %s\n' "$*" >>"$FAKE/docker.log"
[[ "${FAKE_DOCKER_DOWN:-}" != 1 ]] || { echo "Cannot connect to the Docker daemon" >&2; exit 1; }
case "$1" in
  container) ls -1 "$c" ;;
  inspect)
    [[ "$2" == -f ]] || exit 1
    name="${@: -1}"
    [[ -d "$c/$name" ]] || exit 1
    case "$3" in
      *Labels*) cat "$c/$name/label" ;;
      *PortBindings*) cat "$c/$name/ports" ;;
      *GroupAdd*) cat "$c/$name/groups" ;;
      *State.Running*) echo true ;;
    esac ;;
  run)
    name="" label="" ports=""
    shift
    while [[ $# -gt 1 ]]; do
      case "$1" in
        --name) name="$2"; shift ;;
        --label) label="${2#*=}"; shift ;;
        -p) ports+="$2 "; shift ;;
      esac
      shift
    done
    mkdir -p "$c/$name"
    printf '%s\n' "$label" >"$c/$name/label"
    ui="${ports%% *}"; rest="${ports#* }"
    printf '{"16686/tcp":[{"HostIp":"%s","HostPort":"%s"}],"4318/tcp":[{"HostIp":"%s","HostPort":"%s"}]}\n' \
      "${ui%%:*}" "$(cut -d: -f2 <<<"$ui")" "${rest%%:*}" "$(cut -d: -f2 <<<"$rest")" >"$c/$name/ports" ;;
  rm) rm -rf "$c/${@: -1}" ;;
  image) exit 0 ;;
  info) echo "[name=seccomp]" ;;
  restart | start | pull) exit 0 ;;
esac
EOF

cat >"$BIN/hermes" <<'EOF'
#!/usr/bin/env bash
p="$FAKE/plugin"
printf 'hermes %s\n' "$*" >>"$FAKE/hermes.log"
case "$1 ${2:-}" in
  'plugins install') mkdir -p "$HERMES_HOME/plugins/hermes_otel"; echo disabled >"$p/state" ;;
  'plugins enable') echo enabled >"$p/state" ;;
  'plugins disable')
    [[ "${FAKE_HERMES_DISABLE_FAILS:-}" != 1 ]] || exit 1
    echo disabled >"$p/state" ;;
  'plugins list') echo "hermes_otel  $(cat "$p/state" 2>/dev/null || echo disabled)" ;;
esac
EOF
cat >"$BIN/curl" <<'EOF'
#!/usr/bin/env bash
echo '{}'
EOF
chmod +x "$BIN/flock" "$BIN/docker" "$BIN/hermes" "$BIN/curl"
export PATH="$BIN:$PATH"

N=0
FAILED=0
LOG="$TEST_ROOT/out.log"
CASE_NAME=""

reset_world() {
  rm -rf "$HOME/.agent-harness-install" "$FAKE/containers" "$HERMES_HOME" "$HARNESS_IR_WORKSPACE_DIR" "$FAKE"/*.log "$FAKE/plugin"
  mkdir -p "$FAKE/containers/agent-harness-install-ir" "$FAKE/plugin" "$HERMES_HOME" "$HARNESS_IR_WORKSPACE_DIR"
  printf '["%s"]\n' "$(id -g)" >"$FAKE/containers/agent-harness-install-ir/groups"
  printf 'log_level: "INFO"\nrouting:\n  policy: "Balanced"\ntelemetry:\n  backend: "memory"\n  enabled: true\n' \
    >"$HARNESS_IR_WORKSPACE_DIR/config.yaml"
  : >"$FAKE/docker.log"
  : >"$FAKE/hermes.log"
}

# cli <args...> -- runs the real entry point; output in $LOG, exit code in $RC.
cli() {
  RC=0
  (cd "$SCRIPT_DIR" && bash ./install.sh --non-interactive "$@") >"$LOG" 2>&1 || RC=$?
}

check() {
  local desc="$1"; shift
  if "$@"; then return 0; fi
  FAILED=1
  printf '  FAILED: %s (%s)\n' "$desc" "$CASE_NAME"
  sed 's/^/    | /' "$LOG" | tail -n 15
  return 0
}

out_has() { grep -Fq -- "$1" "$LOG"; }
log_has() { grep -Fq -- "$2" "$FAKE/$1.log"; }
rc_is() { [[ "$RC" -eq "$1" ]]; }
rc_fails() { [[ "$RC" -ne 0 ]]; }
state_is() { [[ "$(node -e 'const s=JSON.parse(require("fs").readFileSync(process.argv[1],"utf8"));let v=s;for(const k of process.argv[2].split("."))v=v?.[k];console.log(v===undefined?"":v)' "$HOME/.agent-harness-install/metrics.json" "$1" 2>/dev/null)" == "$2" ]]; }
file_has() { grep -Fq -- "$2" "$1"; }
# Windows file systems under Git Bash ignore chmod, so mode checks are skipped there.
chmod_is_effective() { : >"$TEST_ROOT/probe" && chmod 600 "$TEST_ROOT/probe" && [[ "$(stat -c %a "$TEST_ROOT/probe")" == 600 ]]; }
no_container() { [[ ! -d "$FAKE/containers/$1" ]]; }
has_container() { [[ -d "$FAKE/containers/$1" ]]; }

run_case() {
  CASE_NAME="$1"
  N=$((N + 1))
  local before=$FAILED
  FAILED=0
  reset_world
  "$2"
  if [[ $FAILED -eq 0 ]]; then printf 'ok %d - %s\n' "$N" "$1"; FAILED=$before; else printf 'not ok %d - %s\n' "$N" "$1"; FAILED=1; fi
}

case_enable_all_then_disable() {
  cli metrics enable --target all --backend jaeger
  check 'enable exits 0' rc_is 0
  check 'router config switched to file telemetry' file_has "$HARNESS_IR_WORKSPACE_DIR/config.yaml" 'backend: "file"'
  check 'router telemetry file created' test -f "$HARNESS_IR_WORKSPACE_DIR/telemetry.jsonl"
  check 'router restarted' log_has docker 'docker restart agent-harness-install-ir'
  check 'jaeger started with the installer label' log_has docker 'io.agent-harness-install.managed-by=metrics-jaeger'
  check 'jaeger published on loopback only' log_has docker '127.0.0.1:16686:16686'
  check 'plugin installed and enabled' log_has hermes 'plugins enable hermes_otel'
  check 'plugin config written' test -f "$HERMES_HOME/hermes_otel.yaml"
  check 'router state saved' state_is router.enabled true
  check 'harness state saved' state_is harness.enabled true

  cli metrics show
  check 'show exits 0' rc_is 0
  check 'show reports the harness enabled' out_has 'Enabled for Hermes'

  cli metrics disable --target all
  check 'disable exits 0' rc_is 0
  check 'router config back to memory' file_has "$HARNESS_IR_WORKSPACE_DIR/config.yaml" 'backend: "memory"'
  if chmod_is_effective; then
    check 'telemetry file no longer world/group writable' test "$(stat -c %a "$HARNESS_IR_WORKSPACE_DIR/telemetry.jsonl")" = 600
  fi
  check 'plugin disabled' log_has hermes 'plugins disable hermes_otel'
  check 'managed config removed' test ! -e "$HERMES_HOME/hermes_otel.yaml"
  check 'jaeger removed' no_container agent-harness-install-jaeger
  check 'states cleared' state_is harness.enabled false
}

case_keep_jaeger_then_remove() {
  cli metrics enable --target harness --backend jaeger
  cli metrics disable --target harness --keep-jaeger
  check 'disable --keep-jaeger exits 0' rc_is 0
  check 'jaeger kept' has_container agent-harness-install-jaeger
  cli metrics disable --target harness
  check 'second disable exits 0' rc_is 0
  check 'jaeger removed by the later disable' no_container agent-harness-install-jaeger
}

case_foreign_jaeger_is_refused() {
  mkdir -p "$FAKE/containers/agent-harness-install-jaeger"
  : >"$FAKE/containers/agent-harness-install-jaeger/label"
  cli metrics enable --target harness --backend jaeger
  check 'enable fails' rc_fails
  check 'explains the container is not ours' out_has 'was not created by this installer'
  check 'foreign container untouched' has_container agent-harness-install-jaeger
  check 'plugin never installed' test ! -s "$FAKE/hermes.log"
  check 'no config written' test ! -e "$HERMES_HOME/hermes_otel.yaml"
}

case_target_all_failure_rolls_router_back() {
  mkdir -p "$FAKE/containers/agent-harness-install-jaeger"
  : >"$FAKE/containers/agent-harness-install-jaeger/label"
  cli metrics enable --target all --backend jaeger
  check 'enable fails before any change' rc_fails
  check 'router state untouched' state_is router.enabled ''
  check 'router config untouched' file_has "$HARNESS_IR_WORKSPACE_DIR/config.yaml" 'backend: "memory"'
}

case_docker_down_is_an_error() {
  FAKE_DOCKER_DOWN=1 cli metrics enable --target harness --backend jaeger
  check 'fails when Docker cannot be queried' rc_fails
  check 'says so' out_has 'Cannot inspect Docker containers'
  check 'jaeger not created' no_container agent-harness-install-jaeger
}

case_disable_survives_an_already_disabled_plugin() {
  cli metrics enable --target harness
  FAKE_HERMES_DISABLE_FAILS=1 cli metrics disable --target harness
  check 'failing command with a plugin that lists as enabled is an error' rc_fails
  check 'state still enabled so it can be retried' state_is harness.enabled true
  echo disabled >"$FAKE/plugin/state"
  FAKE_HERMES_DISABLE_FAILS=1 cli metrics disable --target harness
  check 'already-disabled plugin is accepted' rc_is 0
  check 'state cleared' state_is harness.enabled false
}

case_all_disable_still_reaches_router() {
  cli metrics enable --target all
  FAKE_HERMES_DISABLE_FAILS=1 cli metrics disable --target all
  check 'harness failure is reported' rc_fails
  check 'router was still disabled' state_is router.enabled false
  check 'harness stays enabled for retry' state_is harness.enabled true
}

case_rejects_bad_input() {
  cli metrics enable --target harness --backend otlp
  check 'otlp without endpoint rejected' rc_fails
  cli metrics enable --target harness --endpoint 'http://x:4318/v1/traces;touch pwned'
  check 'unsafe endpoint rejected' rc_fails
  check 'nothing executed' test ! -e "$SCRIPT_DIR/pwned"
  cli metrics bogus
  check 'unknown verb rejected' rc_fails
  HARNESS_IR_TELEMETRY_FILE_MODE=777 cli metrics enable --target router
  check 'bad file mode rejected' rc_fails
  check 'router state untouched by a rejected mode' state_is router.enabled ''
}

run_case 'enable --target all then disable, end to end' case_enable_all_then_disable
run_case '--keep-jaeger keeps the container until a later disable' case_keep_jaeger_then_remove
run_case 'a foreign Jaeger container is refused and left alone' case_foreign_jaeger_is_refused
run_case '--target all fails up front without changing the Router' case_target_all_failure_rolls_router_back
run_case 'an unreachable Docker daemon is an error' case_docker_down_is_an_error
run_case 'disable accepts a plugin that is already disabled' case_disable_survives_an_already_disabled_plugin
run_case '--target all disable still disables the Router when the harness fails' case_all_disable_still_reaches_router
run_case 'bad input is rejected without side effects' case_rejects_bad_input

printf '1..%d\n' "$N"
exit "$FAILED"
