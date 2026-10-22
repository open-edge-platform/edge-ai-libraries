#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Full-flow end-to-end test for agent-harness-install: drives the REAL
# ./install.sh entry point per agent (openclaw, deepagents-code, hermes),
# exercising the actual production flow in order every real install goes
# through:
#   Node.js (nvm) -> OVMS pulled/started -> model downloaded+converted and
#   registered (default docker-pull exporter) -> Inference Router built+started
#   in front of OVMS -> agent installed -> agent onboarded (wired to the
#   Router, not OVMS) -> real chat completion through Router -> OVMS ->
#   uninstall.
#
# Run this on a disposable/reflash-able Linux host with Docker (+ ideally
# an Intel GPU) -- it installs real things on the machine (Docker, Node.js
# via nvm, the agent CLIs, OVMS + IR containers), same disposable-host
# assumption test/smoke-test.sh's own header documents.
#
# Host prerequisites (Docker, Node.js, Python/venv/PyYAML) are installed by
# ./startup.sh -- install.sh now runs it automatically as its first step
# (see docs/user-guide/known-limitations.md), so this script's own
# pre-flight call below is just to fail fast on a prerequisite problem
# before the long per-agent install loop, not because install.sh wouldn't
# otherwise handle it.
#
# Usage (from the repo root, or anywhere -- this script locates the repo
# root relative to its own path):
#   ./test/full-flow-test.sh
#
# Options (env vars):
#   TEST_AGENTS            Space-separated agent list (default: "openclaw deepagents-code hermes")
#   TEST_OVMS_EXPORTER      HARNESS_OVMS_EXPORTER to exercise (default: docker-pull,
#                           the installer's default: a raw Hugging Face model is
#                           downloaded and converted to OpenVINO IR by OVMS's own
#                           "-py" image). Set hf-snapshot to exercise that
#                           exporter instead -- it only works against a HF repo
#                           already published as a ready-to-serve OpenVINO IR +
#                           OVMS MediaPipe graph.pbtxt, which the pre-flight check
#                           below confirms (remotely, no download) before running
#                           anything, failing fast with guidance if not. You must
#                           then also set TEST_HF_MODEL to such a repo.
#   TEST_HF_MODEL           A HF model id matching TEST_OVMS_EXPORTER's expected
#                           input (default: Qwen/Qwen2.5-0.5B-Instruct, a small
#                           raw ~0.5B repo that docker-pull converts).
#   KEEP_FINAL_STATE        1 = don't uninstall after the last agent (default: 0)
#   SKIP_GPU_CHECK          Forwarded to install.sh (default: 1, since GPU passthrough
#                           itself still works regardless -- this only skips the
#                           driver/runtime *verification* step, see install.sh --help).
#                           Set to exactly "1" to skip (the default) or "0"/anything
#                           else to run the check -- "0" is specifically normalized to
#                           unset before being forwarded, since install.sh itself treats
#                           ANY non-empty value (including a literal "0") as "skip".
#   LOG_FILE                Path to write the full run's output to (default:
#                           test/logs/full-flow-test-<UTC timestamp>.log)
#   NO_LOG=1                Disable logging to a file; only print to the terminal
#
# Exit code: 0 if every check passed, 1 if any failed (including the
# TEST_HF_MODEL/TEST_OVMS_EXPORTER pre-flight compatibility check).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"

# ------------------------------------------------- full-output log file --
# Re-execs itself as a plain foreground pipeline through `tee`, mirroring
# test/smoke-test.sh's own logging wrapper and its reasoning: `exec >
# >(tee ...)` runs tee in a detached background process substitution, which
# can let this script exit (and the shell reap tee) before the last few
# lines are flushed -- a well known race. A foreground `"$0" ... | tee`
# instead means the `exit` below is only reached once the whole pipeline
# (including tee) has completed, and ${PIPESTATUS[0]} recovers the script's
# real exit code rather than tee's (which is always 0).
if [[ "${_FULL_FLOW_TEST_REEXEC:-0}" != "1" ]]; then
  _log_file="${LOG_FILE:-}"
  _no_log="${NO_LOG:-0}"
  if [[ "$_no_log" != "1" ]]; then
    [[ -n "$_log_file" ]] || _log_file="${REPO_ROOT}/test/logs/full-flow-test-$(date -u +%Y%m%dT%H%M%SZ).log"
    mkdir -p "$(dirname "$_log_file")"
    printf 'Logging full output to: %s\n' "$_log_file"
    _FULL_FLOW_TEST_REEXEC=1 FULL_FLOW_TEST_LOG_FILE="$_log_file" bash "$0" "$@" 2>&1 | tee "$_log_file"
    exit "${PIPESTATUS[0]}"
  fi
fi

[[ -f "${REPO_ROOT}/scripts/install.sh" ]] || { echo "Could not locate the repo root (expected scripts/install.sh at ${REPO_ROOT})."; exit 1; }
cd "$REPO_ROOT" || exit 1

TEST_AGENTS="${TEST_AGENTS:-openclaw deepagents-code hermes}"
TEST_HF_MODEL="${TEST_HF_MODEL:-Qwen/Qwen2.5-0.5B-Instruct}"
KEEP_FINAL_STATE="${KEEP_FINAL_STATE:-0}"
# install.sh (like startup.sh's own SKIP_* vars) treats ANY non-empty value
# as "skip", not specifically "1" -- so a caller's SKIP_GPU_CHECK=0
# (intending "please run the check") must be normalized to a genuinely
# empty/unset var here, not left as the literal non-empty string "0",
# which would still get inherited into install.sh's subprocess below and
# be treated as "skip" there regardless of the CLI flag decision made from
# it further down (see run_full_install_for_agent's gpu_check_args).
if [[ "${SKIP_GPU_CHECK:-1}" == "1" ]]; then
  export SKIP_GPU_CHECK=1
else
  unset SKIP_GPU_CHECK
fi

# --- Isolated identifiers: safe to run alongside a real/other install -----
export HARNESS_OVMS_CONTAINER="test-full-ovms"
export HARNESS_IR_CONTAINER="test-full-ir"
export HARNESS_BACKEND_NETWORK="test-full-backend"
export HARNESS_OVMS_REST_PORT="18000"
export HARNESS_IR_PORT="18010"
export HARNESS_MODELS_DIR="/tmp/test-full-models"
export HARNESS_IR_WORKSPACE_DIR="/tmp/test-full-ir-workspace"
export HARNESS_STATE_DIRNAME=".test-full-agent-harness-install"
export HARNESS_OVMS_EXPORTER="${TEST_OVMS_EXPORTER:-docker-pull}"
# A real agent CLI shim (e.g. an operator's own openclaw/dcode/hermes
# install) commonly already lives at HARNESS_SHIM_DIR's default
# ($HOME/.local/bin) -- without its own override here, this test would
# silently overwrite that real shim instead of staying isolated the same
# way every other identifier above already is.
export HARNESS_SHIM_DIR="/tmp/test-full-shim"
export NON_INTERACTIVE=1
export NO_COLOR=1

PASS=0
FAIL=0
FAILURES=()
ts() { date -u +%H:%M:%S; }
pass() { PASS=$((PASS + 1)); echo "  [$(ts)] [PASS] $1"; }
fail() { FAIL=$((FAIL + 1)); FAILURES+=("$1"); echo "  [$(ts)] [FAIL] $1"; [[ -n "${2:-}" ]] && echo "         $2"; }
section() { echo; echo "=================================================="; echo "[$(ts)] $1"; echo "=================================================="; }
model_name="${TEST_HF_MODEL##*/}"

cleanup_backend() {
  docker rm -f "$HARNESS_IR_CONTAINER" "$HARNESS_OVMS_CONTAINER" >/dev/null 2>&1 || true
}
final_cleanup() {
  [[ "$KEEP_FINAL_STATE" -eq 1 ]] && { echo; echo "KEEP_FINAL_STATE=1: leaving final state in place."; return; }
  echo; echo "=== Final cleanup ==="
  cleanup_backend
  docker network rm "$HARNESS_BACKEND_NETWORK" >/dev/null 2>&1 || true
  rm -rf -- "$HARNESS_MODELS_DIR" "$HARNESS_IR_WORKSPACE_DIR" "$HOME/${HARNESS_STATE_DIRNAME:?}" "$HARNESS_SHIM_DIR"
}
trap final_cleanup EXIT

# print_summary -- shared by both the normal end-of-run path and the
# pre-flight early-exit path below, so a fixture-compatibility failure
# reports the same PASS/FAIL tally/format a normal run would instead of a
# differently-shaped message.
print_summary() {
  echo
  echo "=================================================="
  echo "SUMMARY: $PASS passed, $FAIL failed"
  if [[ "$FAIL" -gt 0 ]]; then
    echo "Failures:"
    for f in "${FAILURES[@]}"; do echo "  - $f"; done
  fi
  [[ -n "${FULL_FLOW_TEST_LOG_FILE:-}" ]] && echo "Full log: ${FULL_FLOW_TEST_LOG_FILE}"
  echo "=================================================="
}

# ---------------------------------------------------------------------
section "0. Pre-flight"
for f in scripts/lib/inference-router.sh scripts/lib/openvino.sh scripts/install.sh uninstall.sh; do
  if [[ -f "$f" ]]; then
    if bash -n "$f" 2>/tmp/synerr; then pass "bash -n $f"; else fail "bash -n $f" "$(cat /tmp/synerr)"; fi
  else
    fail "bash -n $f" "file not found -- is this checkout complete?"
  fi
done

# install.sh now runs ./startup.sh automatically as its first step (see
# scripts/install.sh's prepare_installer_host) -- called explicitly here too
# so a prerequisite problem is reported now, not buried inside the first
# agent's (long) ./install.sh run below.
if bash "${REPO_ROOT}/startup.sh" --non-interactive >/tmp/test-full-startup.log 2>&1; then
  pass "./startup.sh installs/verifies Docker, Node.js, and Python"
else
  fail "./startup.sh installs/verifies Docker, Node.js, and Python" "$(cat /tmp/test-full-startup.log)"
  echo "Cannot continue."
  print_summary
  exit 1
fi
ls /dev/dri/renderD* >/dev/null 2>&1 \
  && pass "Intel GPU render node(s) present (will be passed through to OVMS/IR)" \
  || echo "  [INFO] No /dev/dri render node found -- containers will run CPU-only"

# hf-snapshot only supports a HF repo already published as a ready-to-serve
# OpenVINO IR + OVMS MediaPipe graph.pbtxt (see export_model_via_hf_snapshot
# in scripts/lib/openvino.sh); a repo missing graph.pbtxt fails install.sh
# at the export step for every single agent, which would otherwise surface
# here as a confusing cascade of unrelated-looking OVMS/IR/agent failures
# across the whole TEST_AGENTS loop. Checked remotely (no download) so this
# fails fast with one clear, actionable message instead.
if [[ "$HARNESS_OVMS_EXPORTER" == "hf-snapshot" ]]; then
  hf_tree_url="https://huggingface.co/api/models/${TEST_HF_MODEL}/tree/${HARNESS_HF_MODEL_REVISION:-main}"
  if ! hf_tree="$(curl -sf "$hf_tree_url" 2>/tmp/hf_api_err)"; then
    fail "pre-flight: TEST_HF_MODEL (${TEST_HF_MODEL}) is reachable on the Hugging Face API" \
      "$(cat /tmp/hf_api_err 2>/dev/null) -- check network access and that the repo id/revision are correct."
    print_summary
    exit 1
  fi
  if echo "$hf_tree" | grep -q '"path":"graph.pbtxt"'; then
    pass "pre-flight: TEST_HF_MODEL (${TEST_HF_MODEL}) has a graph.pbtxt (hf-snapshot-compatible)"
  else
    fail "pre-flight: TEST_HF_MODEL (${TEST_HF_MODEL}) has a graph.pbtxt (hf-snapshot-compatible)" \
      "This repo is missing an OVMS MediaPipe graph.pbtxt -- hf-snapshot only supports
repos already published as ready-to-serve OVMS servables, not plain OpenVINO
IR exports. No verified Intel/OpenVINO-owned public example of such a repo
is known at the time of writing (only unverified third-party community
uploads do, which this test deliberately won't default to). Set
TEST_HF_MODEL to a repo you've verified yourself, or drop
TEST_OVMS_EXPORTER to use the default docker-pull exporter with a *raw*
(non-OpenVINO) TEST_HF_MODEL instead."
    print_summary
    exit 1
  fi
fi

# Mirrors the installer's own "open a new terminal" guidance (same fix as
# test/smoke-test.sh's phase_05) so this script's own later verify_agent()
# checks below -- running in *this* process, not install.sh's per-agent
# subprocess -- can resolve node/openclaw/dcode/hermes the same way a real
# user's next shell would. install.sh's own PATH updates (shim.sh's export,
# nvm's `nvm use`) only ever apply within its own subprocess, never
# retroactively to this one -- and this test overrides HARNESS_SHIM_DIR
# away from its real default ($HOME/.local/bin), so without this, every
# "CLI resolves on PATH" check below would false-negative regardless of
# whether the install actually succeeded. dcode/hermes's own upstream
# installers always install to $HOME/.local/bin regardless of
# HARNESS_SHIM_DIR (same reasoning as agent_cli_is_trusted_path in
# agents.sh), so that needs to be on PATH here too, not just the shim dir.
export NVM_DIR="$HOME/.nvm"
# shellcheck disable=SC1091
[[ -s "$NVM_DIR/nvm.sh" ]] && . "$NVM_DIR/nvm.sh"
export PATH="${HARNESS_SHIM_DIR}:$HOME/.local/bin:$PATH"

# ---------------------------------------------------------------------

run_full_install_for_agent() {
  local agent="$1"
  section "Agent: ${agent} -- full ./install.sh run"
  # SKIP_GPU_CHECK is normalized above to either "1" (exported) or fully
  # unset -- checked with the ${:-} safe form since set -u is active and a
  # caller's "run the check" case leaves it genuinely unset, not empty.
  # An unconditional literal --skip-gpu-check here would always force it on
  # regardless, silently ignoring that (this is exactly the GPU-
  # verification step, not GPU passthrough itself, which install.sh's
  # export_model_via_docker_pull applies automatically based on real
  # hardware detection either way).
  local -a gpu_check_args=()
  [[ "${SKIP_GPU_CHECK:-}" == "1" ]] && gpu_check_args=(--skip-gpu-check)
  if env HARNESS_AGENT="$agent" bash "${REPO_ROOT}/install.sh" \
      --harness "$agent" --model "$TEST_HF_MODEL" \
      --non-interactive "${gpu_check_args[@]}" \
      2>&1 | tee "/tmp/test-full-install-${agent}.log"; then
    pass "./install.sh --harness ${agent} --model ${TEST_HF_MODEL} exited 0"
  else
    fail "./install.sh --harness ${agent} --model ${TEST_HF_MODEL} exited 0" \
      "see /tmp/test-full-install-${agent}.log"
    return 1
  fi
}

verify_backend() {
  local agent="$1"
  # --- OVMS ---
  if docker inspect -f '{{.State.Running}}' "$HARNESS_OVMS_CONTAINER" 2>/dev/null | grep -q true; then
    pass "[$agent] OVMS container is running"
  else
    fail "[$agent] OVMS container is running"
  fi
  if curl -sf "http://127.0.0.1:${HARNESS_OVMS_REST_PORT}/v2/models/${model_name}/ready" >/dev/null 2>&1; then
    pass "[$agent] OVMS reports the model ready"
  else
    fail "[$agent] OVMS reports the model ready"
  fi
  if grep -q "\"name\": \"${model_name}\"" "${HARNESS_MODELS_DIR}/config.json" 2>/dev/null; then
    pass "[$agent] model registered in OVMS config.json"
  else
    fail "[$agent] model registered in OVMS config.json"
  fi

  # --- Inference Router ---
  if docker inspect -f '{{.State.Running}}' "$HARNESS_IR_CONTAINER" 2>/dev/null | grep -q true; then
    pass "[$agent] Inference Router container is running"
  else
    fail "[$agent] Inference Router container is running"
    echo "  --- docker logs ${HARNESS_IR_CONTAINER} (last 40) ---"
    docker logs "$HARNESS_IR_CONTAINER" 2>&1 | tail -40
  fi
  if curl -sf "http://127.0.0.1:${HARNESS_IR_PORT}/health" >/dev/null 2>&1; then
    pass "[$agent] IR /health responds"
  else
    fail "[$agent] IR /health responds"
  fi

  # --- Backend network (the actual fix: IR must reach OVMS by container
  # name on HARNESS_BACKEND_NETWORK, not via the host-facing/loopback
  # address -- see ensure_backend_network/ovms_internal_endpoint in
  # scripts/lib/openvino.sh) ---
  if docker network inspect "$HARNESS_BACKEND_NETWORK" >/dev/null 2>&1; then
    pass "[$agent] backend network '${HARNESS_BACKEND_NETWORK}' exists"
  else
    fail "[$agent] backend network '${HARNESS_BACKEND_NETWORK}' exists"
  fi
  if docker inspect -f '{{json .NetworkSettings.Networks}}' "$HARNESS_OVMS_CONTAINER" 2>/dev/null | grep -q "$HARNESS_BACKEND_NETWORK"; then
    pass "[$agent] OVMS container is joined to the backend network"
  else
    fail "[$agent] OVMS container is joined to the backend network"
  fi
  if docker inspect -f '{{json .NetworkSettings.Networks}}' "$HARNESS_IR_CONTAINER" 2>/dev/null | grep -q "$HARNESS_BACKEND_NETWORK"; then
    pass "[$agent] IR container is joined to the backend network"
  else
    fail "[$agent] IR container is joined to the backend network"
  fi

  local config_file="${HARNESS_IR_WORKSPACE_DIR}/config.yaml"
  local perms; perms="$(stat -c '%a' "$config_file" 2>/dev/null || echo '??')"
  [[ "$perms" == "644" ]] \
    && pass "[$agent] IR config.yaml is mode 644 (readable by IR's container uid)" \
    || fail "[$agent] IR config.yaml is mode 644 (readable by IR's container uid)" "got: $perms"
  if python3 -c "
import yaml
d = yaml.safe_load(open('${config_file}'))
assert d['providers'][0]['model'] == '${model_name}', d
assert d['providers'][0]['settings']['endpoint'] == 'http://${HARNESS_OVMS_CONTAINER}:8000/v3', d
" 2>/tmp/yerr; then
    pass "[$agent] IR config.yaml's provider points at OVMS by container name (not loopback) with the right model name"
  else
    fail "[$agent] IR config.yaml's provider points at OVMS by container name (not loopback) with the right model name" "$(cat /tmp/yerr)"
  fi

  # --- End-to-end chat completion THROUGH IR -> OVMS (agent-agnostic proof) ---
  local response http_code
  # -sf together silences curl's OWN error diagnostics too (-s mutes them,
  # not just the progress meter -- -S is needed to get them back) AND, via
  # -f, discards the response body entirely on a non-2xx status -- between
  # the two, a real failure here previously showed completely empty detail
  # (neither /tmp/curlerr nor /tmp/jsonerr had anything), making it
  # impossible to tell a connection failure from a non-2xx response from an
  # empty-but-200 body. -o+-w captures the body and status separately
  # instead, with -sS to still get real curl-level errors (DNS/connection
  # failures etc.) without the progress meter.
  http_code="$(curl -sS -o /tmp/chat_body -w '%{http_code}' -X POST \
    "http://127.0.0.1:${HARNESS_IR_PORT}/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d "{\"model\": \"${model_name}\", \"messages\": [{\"role\": \"user\", \"content\": \"Say hello in one word.\"}], \"max_tokens\": 10}" \
    2>/tmp/curlerr)"
  response="$(cat /tmp/chat_body 2>/dev/null)"
  # OVMS/IR responds as an SSE event-stream (content-type text/event-stream,
  # a series of "data: {...}" chunks + a trailing "data: [DONE]") regardless
  # of whether the request set "stream": true -- confirmed from OpenClaw's
  # own onboarding smoke test hitting this same endpoint/model moments
  # earlier. A plain json.load() of the raw SSE text always fails even on a
  # real success (it isn't a single JSON document), so parse either shape:
  # SSE chunks if any "data:" lines are present, otherwise the whole body
  # as one JSON object.
  if [[ "$http_code" == 2* && -n "$response" ]] && echo "$response" | python3 -c "
import json, sys
text = sys.stdin.read()
chunks = [l[5:].strip() for l in text.splitlines() if l.startswith('data:')]
chunks = [c for c in chunks if c and c != '[DONE]']
if chunks:
    # Tolerate one malformed chunk rather than letting json.loads raise on
    # it short-circuit the whole check before a later, valid chunk is ever
    # examined -- any() over a generator doesn't catch exceptions, it only
    # stops early on a *truthy* result.
    found = False
    for c in chunks:
        try:
            if 'choices' in json.loads(c):
                found = True
                break
        except ValueError:
            continue
    assert found, 'no valid SSE chunk contained choices'
else:
    d = json.loads(text)
    assert 'choices' in d, d
" 2>/tmp/jsonerr; then
    pass "[$agent] real chat completion through IR -> OVMS succeeded"
    echo "    response: $(echo "$response" | head -c 200)"
  else
    fail "[$agent] real chat completion through IR -> OVMS succeeded" \
      "http_code=${http_code}, body: $(echo "$response" | head -c 500)
$(cat /tmp/curlerr /tmp/jsonerr 2>/dev/null)"
    # A 502 here means IR itself responded but reported OVMS (its
    # "upstream provider") failed the actual inference call -- IR's own
    # error body has no detail beyond that, so the real cause only shows
    # up in one or both containers' own logs (same diagnostic already done
    # above for a flat-out-not-running IR container).
    echo "  --- docker logs ${HARNESS_IR_CONTAINER} (last 40) ---"
    docker logs "$HARNESS_IR_CONTAINER" 2>&1 | tail -40
    echo "  --- docker logs ${HARNESS_OVMS_CONTAINER} (last 40) ---"
    docker logs "$HARNESS_OVMS_CONTAINER" 2>&1 | tail -40
  fi

  # --- status reflects both OVMS and IR ---
  local status_out
  status_out="$(bash "${REPO_ROOT}/install.sh" status 2>&1)"
  echo "$status_out" | grep -q "OpenVINO Model Server running" \
    && pass "[$agent] status reports OVMS running" \
    || fail "[$agent] status reports OVMS running" "$status_out"
  echo "$status_out" | grep -q "Inference Router running" \
    && pass "[$agent] status reports Inference Router running" \
    || fail "[$agent] status reports Inference Router running" "$status_out"
}

verify_agent() {
  local agent="$1"
  case "$agent" in
    openclaw)
      command -v openclaw >/dev/null 2>&1 \
        && pass "[$agent] openclaw CLI resolves on PATH" \
        || fail "[$agent] openclaw CLI resolves on PATH"
      # openclaw's own onboarding already ran a real chat completion against
      # the endpoint during install.sh above (configure_openclaw_provider +
      # "openclaw infer model run") -- the install.sh exit-0 check already
      # covers this; its own warn() on a failed smoke test does not fail
      # the overall install (see agents.sh), so cross-check the log too.
      if grep -q "Smoke-testing OpenClaw" "/tmp/test-full-install-${agent}.log" 2>/dev/null \
         && ! grep -q "Smoke test failed" "/tmp/test-full-install-${agent}.log" 2>/dev/null; then
        pass "[$agent] openclaw's own onboarding smoke test succeeded (per install log)"
      else
        fail "[$agent] openclaw's own onboarding smoke test succeeded (per install log)"
      fi
      ;;
    deepagents-code)
      command -v dcode >/dev/null 2>&1 \
        && pass "[$agent] dcode CLI resolves on PATH" \
        || fail "[$agent] dcode CLI resolves on PATH"
      if grep -q "base_url = \"http://127.0.0.1:${HARNESS_IR_PORT}/v1\"" "$HOME/.deepagents/config.toml" 2>/dev/null; then
        pass "[$agent] dcode's config.toml is wired to IR's endpoint (not OVMS's)"
      else
        fail "[$agent] dcode's config.toml is wired to IR's endpoint (not OVMS's)" \
          "$(cat "$HOME/.deepagents/config.toml" 2>/dev/null)"
      fi
      if grep -q "Smoke-testing dcode" "/tmp/test-full-install-${agent}.log" 2>/dev/null \
         && ! grep -q "Smoke test failed" "/tmp/test-full-install-${agent}.log" 2>/dev/null; then
        pass "[$agent] dcode's own onboarding smoke test succeeded (per install log)"
      else
        fail "[$agent] dcode's own onboarding smoke test succeeded (per install log)"
      fi
      ;;
    hermes)
      command -v hermes >/dev/null 2>&1 \
        && pass "[$agent] hermes CLI resolves on PATH" \
        || fail "[$agent] hermes CLI resolves on PATH"
      # Hermes has no built-in auto-config/smoke-test in onboarding (that
      # auto-config path was reverted) -- confirm the installer at least
      # printed IR's endpoint (not OVMS's) as the one to wire manually.
      if grep -q "http://127.0.0.1:${HARNESS_IR_PORT}/v1" "/tmp/test-full-install-${agent}.log" 2>/dev/null; then
        pass "[$agent] onboarding printed IR's endpoint (not OVMS's) for manual Hermes config"
      else
        fail "[$agent] onboarding printed IR's endpoint (not OVMS's) for manual Hermes config"
      fi
      ;;
  esac
}

uninstall_agent() {
  local agent="$1"
  # Deliberately no --delete-models here -- the downloaded model and built
  # IR image should persist across agent iterations (same idempotent-reuse
  # behavior a real repeated install would get), so only the backend
  # containers + this agent's package are torn down each time; final_cleanup
  # removes the models dir/image once, at the very end.
  if bash "${REPO_ROOT}/uninstall.sh" --yes --harness "$agent" >/tmp/test-full-uninstall.log 2>&1; then
    pass "[$agent] ./uninstall.sh --harness ${agent} --yes exited 0"
  else
    fail "[$agent] ./uninstall.sh --harness ${agent} --yes exited 0" "$(cat /tmp/test-full-uninstall.log)"
  fi
  if ! docker inspect "$HARNESS_OVMS_CONTAINER" >/dev/null 2>&1 \
    && ! docker inspect "$HARNESS_IR_CONTAINER" >/dev/null 2>&1; then
    pass "[$agent] both OVMS and IR containers removed by uninstall"
  else
    fail "[$agent] both OVMS and IR containers removed by uninstall"
  fi
}

# ---------------------------------------------------------------------
read -ra agent_array <<<"$TEST_AGENTS"
last_index=$((${#agent_array[@]} - 1))
for i in "${!agent_array[@]}"; do
  agent="${agent_array[$i]}"
  if run_full_install_for_agent "$agent"; then
    verify_backend "$agent"
    verify_agent "$agent"
  fi
  if [[ "$i" -eq "$last_index" && "$KEEP_FINAL_STATE" == "1" ]]; then
    echo "  [INFO] KEEP_FINAL_STATE=1 on the last agent -- skipping uninstall."
  else
    uninstall_agent "$agent"
  fi
done

# ---------------------------------------------------------------------
print_summary
[[ "$FAIL" -eq 0 ]]
