#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Opt-in tests for a prepared runner; never provision or uninstall shared inference.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${HARNESS_RUN_OPENSHELL_INTEGRATION:-}" != 1 ]]; then
  printf 'Set HARNESS_RUN_OPENSHELL_INTEGRATION=1 on a prepared Linux runner.\n' >&2
  exit 2
fi
: "${HARNESS_LLM_MODEL:?Set HARNESS_LLM_MODEL to an exact model ID already served by IR}"
for command in node docker openshell curl timeout; do
  command -v "$command" >/dev/null || { printf 'Missing prerequisite: %s\n' "$command" >&2; exit 2; }
done
[[ "$(uname -s)" == Linux ]] || { printf 'Linux is required.\n' >&2; exit 2; }
[[ "$(openshell --version)" == 'openshell 0.1.5' ]] || { printf 'OpenShell 0.1.5 is required.\n' >&2; exit 2; }

export HARNESS_STATE_DIRNAME=".agent-harness-ci-$(node -e 'console.log(require("node:crypto").randomBytes(8).toString("hex"))')"
export HARNESS_BIND_HOST=127.0.0.1
export HARNESS_ADVERTISED_HOST=127.0.0.1
export NO_COLOR=1
for lib in colors verify state sudo shim gpu-intel docker-setup nodejs openvino inference-router agents openshell; do
  # shellcheck disable=SC1090
  . "$SCRIPT_DIR/scripts/lib/$lib.sh"
done
. "$SCRIPT_DIR/test/openshell-test-lib.sh"
TEST_ROOT="$(mktemp -d)"
export HARNESS_OPENSHELL_GATEWAY="${HARNESS_OPENSHELL_GATEWAY:-openshell}"
printf 'TAP version 13\n'
printf '# Isolated ownership records: %s/%s\n' "$HOME" "$HARNESS_STATE_DIRNAME"

cleanup_resources() {
  local agent result=0
  for agent in openclaw deepagents-code hermes; do
    if [[ -f "$HOME/$HARNESS_STATE_DIRNAME/openshell/$agent/profile.json" ]]; then
      timeout 180 bash "$SCRIPT_DIR/uninstall.sh" --runtime openshell --sandbox-only --harness "$agent" --yes < /dev/null \
        || result=1
    fi
  done
  rm -f -- "$HOME/$HARNESS_STATE_DIRNAME/host-only-marker" || result=1
  return "$result"
}
on_exit() {
  local rc=$? cleanup_rc
  trap - EXIT
  set +e
  cleanup_resources >"$TEST_LOG" 2>&1
  cleanup_rc=$?
  TEST_COUNT=$((TEST_COUNT + 1))
  if [[ "$cleanup_rc" == 0 ]]; then
    printf 'ok %s - final owned-resource cleanup\n' "$TEST_COUNT"
  else
    TEST_FAILURES=$((TEST_FAILURES + 1))
    printf 'not ok %s - final owned-resource cleanup\n' "$TEST_COUNT"
    sed 's/^/# /' "$TEST_LOG"
  fi
  finish_tests || rc=1
  rm -f -- "$TEST_LOG"
  rm -rf -- "$TEST_ROOT"
  exit "$rc"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

gate() {
  run_case "$@"
  # Live cases have dependencies; stop at the first failure and let EXIT clean up.
  [[ "$TEST_FAILURES" == 0 ]] || exit 1
}
profile_name() {
  node -e 'console.log(JSON.parse(require("node:fs").readFileSync(process.argv[1])).name)' \
    "$HOME/$HARNESS_STATE_DIRNAME/openshell/$1/profile.json"
}
exec_in() {
  local agent="$1"
  shift
  timeout 180 openshell sandbox exec --name "$(profile_name "$agent")" \
    --no-tty --no-login-shell -g "$HARNESS_OPENSHELL_GATEWAY" -- "$@" < /dev/null
}
wait_phase() {
  local name="$1" expected="$2" attempt phase
  for attempt in {1..90}; do
    phase="$(timeout 15 openshell sandbox get "$name" -g "$HARNESS_OPENSHELL_GATEWAY" -o json < /dev/null \
      | node -e 'let d="";process.stdin.on("data",x=>d+=x).on("end",()=>console.log(JSON.parse(d).phase))')"
    [[ "$phase" != "$expected" ]] || return 0
    sleep 2
  done
  printf 'Sandbox %s did not reach %s; last phase: %s\n' "$name" "$expected" "$phase" >&2
  return 1
}
snapshot_inference() {
  local container
  for container in "$HARNESS_IR_CONTAINER" "$HARNESS_OVMS_CONTAINER"; do
    if docker container inspect "$container" >/dev/null 2>&1; then
      docker inspect "$container" --format '{{.Id}} {{.State.StartedAt}} {{json .HostConfig.PortBindings}}'
    elif [[ "$container" == "$HARNESS_IR_CONTAINER" ]]; then
      printf 'Shared IR container is missing.\n' >&2
      return 1
    fi
  done
}
preflight() {
  HARNESS_AGENT=openclaw
  docker info >/dev/null
  timeout 20 openshell status -g "$HARNESS_OPENSHELL_GATEWAY" < /dev/null
  openshell_validate_shared_inference
  [[ "$HARNESS_IR_PORT" != "$HARNESS_OVMS_REST_PORT" ]]
  ensure_state_dir >/dev/null
  atomic_write_file "$HOME/$HARNESS_STATE_DIRNAME/host-only-marker" 'host-only-test-fixture'
  snapshot_inference >"$TEST_ROOT/inference-before"
}
install_agent() {
  local agent="$1"
  timeout 1800 bash "$SCRIPT_DIR/install.sh" --runtime openshell --harness "$agent" \
    --non-interactive < /dev/null
  wait_phase "$(profile_name "$agent")" Ready
  if [[ "$agent" == deepagents-code ]]; then
    grep -Fq '/home/node/.local/share/uv/python/cpython-*/bin/python*' \
      "$HOME/$HARNESS_STATE_DIRNAME/openshell/$agent/provider.json"
  fi
}
status_agent() {
  timeout 30 bash "$SCRIPT_DIR/install.sh" status --runtime openshell --harness "$1" < /dev/null
}
idempotent_install() {
  local before
  before="$(profile_name "$1")"
  install_agent "$1"
  [[ "$(profile_name "$1")" == "$before" ]]
}
model_change_rejected() {
  expect_failure 'refusing to change it implicitly|does not serve model|Shared inference is unavailable' \
    env HARNESS_LLM_MODEL=agent-harness-ci-unserved-model \
    timeout 60 bash "$SCRIPT_DIR/install.sh" --runtime openshell --harness "$1" \
      --non-interactive
}
filesystem_boundaries() {
  local agent="$1" home_config
  case "$agent" in
    openclaw) home_config="$HOME/.openclaw" ;;
    deepagents-code) home_config="$HOME/.deepagents" ;;
    hermes) home_config="$HOME/.hermes" ;;
  esac
  exec_in "$agent" /usr/local/bin/node -e '
    const fs = require("node:fs");
    if (process.getuid() === 0) throw Error("Sandbox runs as root");
    for (const path of [...process.argv.slice(1), "/var/run/docker.sock"])
      if (fs.existsSync(path)) throw Error(`Unexpected host resource: ${path}`);
    const file = "/sandbox/harness-ci-exact-copy";
    const token = require("node:crypto").randomBytes(32).toString("hex");
    fs.writeFileSync(file, token);
    if (fs.readFileSync(file, "utf8") !== token) throw Error("Workspace content mismatch");
  ' "$home_config" "$HOME/$HARNESS_STATE_DIRNAME/host-only-marker"
}
sandbox_boundaries() {
  local agent="$1" result rc
  filesystem_boundaries "$agent"
  # Confirm allowed connectivity first, so a broken exec/network cannot pass the denial case.
  exec_in "$agent" /usr/bin/curl --fail --silent --show-error --max-time 15 \
    "http://host.openshell.internal:${HARNESS_IR_PORT}/v1/models"
  set +e
  result="$(exec_in "$agent" /usr/bin/curl --fail --silent --show-error --max-time 10 \
    "http://host.openshell.internal:${HARNESS_OVMS_REST_PORT}/v1/models" 2>&1)"
  rc=$?
  set -e
  [[ "$rc" == 7 ]] || { printf 'Expected denied connection (curl 7), got %s:\n%s\n' "$rc" "$result" >&2; return 1; }
}
dynamic_policy_change() {
  local agent="$1" name rule response rc
  name="$(profile_name "$agent")"
  rule="agent_harness_ci_policy_validation"
  # OpenShell 0.1.5 requires endpoint and deny changes in separate updates.
  timeout 45 openshell policy update "$name" --rule-name "$rule" --binary /usr/bin/curl \
    --add-endpoint "host.openshell.internal:${HARNESS_IR_PORT}:read-write:rest:enforce" \
    -g "$HARNESS_OPENSHELL_GATEWAY" --wait
  timeout 45 openshell policy update "$name" --rule-name "$rule" --binary /usr/bin/curl \
    --add-deny "host.openshell.internal:${HARNESS_IR_PORT}:GET:/v1/models" \
    -g "$HARNESS_OPENSHELL_GATEWAY" --wait
  timeout 30 openshell policy get "$name" --full --output json \
    -g "$HARNESS_OPENSHELL_GATEWAY" | node -e '
      let d=""; process.stdin.on("data",x=>d+=x).on("end",()=>{
        const p=JSON.parse(d).policy, rule=p.network_policies.agent_harness_ci_policy_validation;
        if (!rule || !rule.endpoints.some(e=>e.deny_rules?.some(r=>r.method==="GET"&&r.path==="/v1/models")))
          process.exitCode=1;
      });'
  filesystem_boundaries "$agent"
  set +e
  response="$(exec_in "$agent" /usr/bin/curl --silent --show-error --max-time 15 \
    -w '\n%{http_code}' "http://host.openshell.internal:${HARNESS_IR_PORT}/v1/models" 2>&1)"
  rc=$?
  set -e
  [[ "$rc" == 0 && "$response" == *policy_denied* && "$response" == *403* ]] \
    || { printf 'Expected OpenShell policy_denied (HTTP 403); got curl %s:\n%s\n' "$rc" "$response" >&2; return 1; }
  timeout 45 openshell policy update "$name" --remove-rule "$rule" \
    -g "$HARNESS_OPENSHELL_GATEWAY" --wait
  timeout 30 openshell policy get "$name" --full --output json \
    -g "$HARNESS_OPENSHELL_GATEWAY" | node -e '
      let d=""; process.stdin.on("data",x=>d+=x).on("end",()=>{
        const p=JSON.parse(d).policy;
        if (p.network_policies.agent_harness_ci_policy_validation) process.exitCode=1;
      });'
  filesystem_boundaries "$agent"
  exec_in "$agent" /usr/bin/curl --fail --silent --show-error --max-time 15 \
    "http://host.openshell.internal:${HARNESS_IR_PORT}/v1/models"
}
persistence_hash() {
  local agent="$1"
  exec_in "$agent" /usr/local/bin/node -e '
    const fs=require("node:fs"),crypto=require("node:crypto");
    const config=process.env.HARNESS_AGENT === "hermes" ? "/home/node/.hermes/config.yaml"
      : process.env.HARNESS_AGENT === "deepagents-code" ? `${process.env.HOME}/.deepagents/config.toml`
      : `${process.env.HOME}/.openclaw/openclaw.json`;
    console.log(crypto.createHash("sha256").update(fs.readFileSync(config))
      .update(fs.readFileSync("/sandbox/harness-ci-exact-copy")).digest("hex"));
  '
}
wait_stable_persistence_hash() {
  local agent="$1" previous="" current stable=0 attempt
  for attempt in {1..60}; do
    current="$(persistence_hash "$agent")" || return 1
    if [[ "$current" == "$previous" ]]; then
      stable=$((stable + 1))
      if [[ "$stable" -ge 3 ]]; then
        printf '%s\n' "$current"
        return 0
      fi
    else
      stable=0
    fi
    previous="$current"
    sleep 1
  done
  printf 'Sandbox %s persistence data did not stabilize within 60 seconds.\n' "$agent" >&2
  return 1
}
restart_persistence() {
  local agent="$1" name before after
  name="$(profile_name "$agent")"
  before="$(wait_stable_persistence_hash "$agent")"
  timeout 120 openshell sandbox stop "$name" -g "$HARNESS_OPENSHELL_GATEWAY" < /dev/null
  wait_phase "$name" Stopped
  timeout 120 openshell sandbox start "$name" -g "$HARNESS_OPENSHELL_GATEWAY" < /dev/null
  wait_phase "$name" Ready
  after="$(wait_stable_persistence_hash "$agent")"
  [[ "$before" == "$after" ]]
  # Re-run each native agent's inference smoke check after restart, not just curl.
  timeout 240 bash "$SCRIPT_DIR/install.sh" onboard --runtime openshell --harness "$agent" < /dev/null
}
remove_agent() {
  local agent="$1" name
  name="$(profile_name "$agent")"
  timeout 180 bash "$SCRIPT_DIR/uninstall.sh" --runtime openshell --sandbox-only --harness "$agent" --yes < /dev/null
  [[ ! -f "$HOME/$HARNESS_STATE_DIRNAME/openshell/$agent/profile.json" ]]
  [[ -f "$HOME/$HARNESS_STATE_DIRNAME/openshell/$agent/removed-profile.json" ]]
  for kind in sandbox provider; do
    timeout 30 openshell "$kind" list -g "$HARNESS_OPENSHELL_GATEWAY" -o json < /dev/null \
      | node -e '
        let d=""; process.stdin.on("data",x=>d+=x).on("end",()=>{
          const data=JSON.parse(d);
          const entries=data[process.argv[1] === "sandbox" ? "sandboxes" : "providers"];
          if (data.next_page_token || !Array.isArray(entries) || entries.some(x=>x.name === process.argv[2]))
            process.exitCode=1;
        });' "$kind" "$name"
  done
}
inference_unchanged() {
  snapshot_inference >"$TEST_ROOT/inference-after"
  cmp "$TEST_ROOT/inference-before" "$TEST_ROOT/inference-after"
  HARNESS_AGENT=openclaw
  openshell_validate_shared_inference
}
local_model_defaults() {
  timeout 120 docker run --rm --pull never --network none --entrypoint /usr/local/bin/node \
    -e HARNESS_TEST_REQUIRE_HERMES=1 -e HARNESS_TEST_MODEL_CONFIG=/opt/harness/model-config.mjs \
    -v "$SCRIPT_DIR/test/model-defaults-test.mjs:/opt/test/model-defaults-test.mjs:ro" \
    agent-harness-hermes-openshell:local --test /opt/test/model-defaults-test.mjs
}
dcode_pty() {
  exec_in deepagents-code /usr/bin/python3 -c \
    'import os, pty; master, slave = pty.openpty(); os.close(master); os.close(slave); print("Deep Agents Code PTY allocation passed")'
}
hermes_pty() {
  exec_in hermes /usr/local/bin/node -e '
    const {execFileSync}=require("node:child_process");
    const runtime=JSON.parse(execFileSync("/home/node/.local/bin/hermes",
      ["--print-runtime-command"],{encoding:"utf8"}));
    execFileSync(runtime[0],["-I","-c",
      "import os, pty; master, slave = pty.openpty(); os.close(master); os.close(slave); print(\"Hermes PTY allocation passed\")"],
      {stdio:"inherit"});
  '
}

gate 'prepared gateway and loopback inference are healthy' preflight
for agent in openclaw deepagents-code hermes; do
  gate "$agent installation and native inference" install_agent "$agent"
  gate "$agent status dispatch" status_agent "$agent"
  gate "$agent repeated install preserves identity" idempotent_install "$agent"
  gate "$agent implicit model change rejected" model_change_rejected "$agent"
  gate "$agent static installer policy filesystem and network boundaries" sandbox_boundaries "$agent"
  if [[ "$agent" == openclaw ]]; then
    gate 'OpenClaw dynamic network policy preserves filesystem access' dynamic_policy_change "$agent"
  fi
  gate "$agent stop/start retains config, workspace and inference" restart_persistence "$agent"
done
gate 'built image applies Qwen defaults and Hermes request overrides offline' local_model_defaults
gate 'Deep Agents Code can allocate sandbox-local PTYs' dcode_pty
gate 'Hermes browser terminal can allocate sandbox-local PTYs' hermes_pty
gate 'complete uninstall requires explicit consent' expect_failure 'confirmation requires a TTY|Uninstall cancelled' \
  timeout 30 bash "$SCRIPT_DIR/uninstall.sh" --runtime host < /dev/null
for agent in openclaw deepagents-code hermes; do
  gate "$agent owned uninstall removes sandbox and provider" remove_agent "$agent"
done
gate 'Hermes can be freshly provisioned after removal' install_agent hermes
gate 'fresh Hermes installation can be removed' remove_agent hermes
gate 'shared inference containers, bindings and model remain unchanged' inference_unchanged
