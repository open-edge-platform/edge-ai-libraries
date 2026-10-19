#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
#
# agent-harness-install -- end-to-end smoke test suite.
#
# Targets: Ubuntu, CPU-only host (no Intel GPU required -- the installer's
# own CPU fallback path is exercised). Installs real things on this machine
# (Docker, Node.js via nvm, OpenClaw/dcode/Hermes, an OpenVINO Model Server
# container) -- run this on a disposable or reflash-able Ubuntu box, not a
# box you can't afford to modify.
#
# Usage:
#   ./test/smoke-test.sh [options]
#
# Options:
#   --list                  List test phases and exit
#   --only ID[,ID...]       Run only these phases (see --list for IDs)
#   --skip ID[,ID...]       Skip these phases
#   --agents "a b c"        Space-separated agent list to install/onboard/
#                           uninstall (default: "openclaw deepagents-code hermes")
#   --hf-model <id>         Hugging Face model the installer exports+serves via
#                           OVMS (the installer requires a model; default:
#                           Qwen/Qwen2.5-0.5B-Instruct -- downloads several
#                           hundred MB-GB)
#   --allow-clone-test      Also test the live git-clone standalone bootstrap
#                           path (does a real shallow git fetch of this repo)
#   --no-cleanup            Skip the final uninstall/cleanup phase (leaves
#                           everything installed for manual inspection)
#   --log-file <path>       Write the full run's output to this file (default:
#                           test/logs/smoke-test-<UTC timestamp>.log). Logging
#                           is on by default -- disables ANSI colors for the
#                           duration of the run so the log file stays clean
#                           plain text (easy to paste/share without escape
#                           code garbage).
#   --no-log                Disable logging to a file; only print to the
#                           terminal (colors re-enabled if it's a TTY).
#   -h, --help              Show this help
#
# Environment overrides (same effect as the matching flag):
#   SMOKE_AGENTS, SMOKE_HF_MODEL, SMOKE_CLEANUP (0/1),
#   SMOKE_TEST_BOOTSTRAP_CLONE (0/1)
#
# Exit code: 0 if every check passed (or was skipped), 1 if any check failed.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ------------------------------------------------- full-output log file --
# Captures everything this script prints (both streams) to a plain-text log
# file, so a run's full output can be shared/attached instead of copy-pasted
# from a terminal. Re-execs itself as a plain foreground pipeline through
# `tee` rather than `exec > >(tee ...)`: the latter runs tee in a detached
# background process substitution, which can let this script exit (and the
# shell reap it) before tee finishes flushing the last few lines -- a well
# known race. Piping a foreground `"$0" ... | tee` instead means `exit`
# below is only reached once the whole pipeline (including tee) has
# completed, and ${PIPESTATUS[0]} recovers the *script's* real exit code
# rather than tee's (which is always 0).
if [[ "${_SMOKE_TEST_REEXEC:-0}" != "1" ]]; then
  _orig_args=("$@")
  _log_file=""
  _no_log=0
  _skip_wrap=0
  _i=0
  while [[ $_i -lt ${#_orig_args[@]} ]]; do
    case "${_orig_args[$_i]}" in
      --no-log) _no_log=1 ;;
      --log-file) _i=$((_i + 1)); _log_file="${_orig_args[$_i]:-}" ;;
      --list | -h | --help) _skip_wrap=1 ;;
    esac
    _i=$((_i + 1))
  done
  if [[ "$_no_log" != "1" && "$_skip_wrap" != "1" ]]; then
    [[ -n "$_log_file" ]] || _log_file="${REPO_ROOT}/test/logs/smoke-test-$(date -u +%Y%m%dT%H%M%SZ).log"
    mkdir -p "$(dirname "$_log_file")"
    printf 'Logging full output to: %s\n' "$_log_file"
    _SMOKE_TEST_REEXEC=1 _SMOKE_TEST_LOG_FILE="$_log_file" bash "$0" "${_orig_args[@]}" 2>&1 | tee "$_log_file"
    exit "${PIPESTATUS[0]}"
  fi
fi

cd "$REPO_ROOT" || exit 1

# ---------------------------------------------------------------- options --
SMOKE_AGENTS="${SMOKE_AGENTS:-openclaw deepagents-code hermes}"
SMOKE_HF_MODEL="${SMOKE_HF_MODEL:-Qwen/Qwen2.5-0.5B-Instruct}"
SMOKE_CLEANUP="${SMOKE_CLEANUP:-1}"
SMOKE_TEST_BOOTSTRAP_CLONE="${SMOKE_TEST_BOOTSTRAP_CLONE:-0}"
ONLY_IDS=""
SKIP_IDS=""
LIST_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --list) LIST_ONLY=1 ;;
    --only) ONLY_IDS="${2:?--only requires a value}"; shift ;;
    --skip) SKIP_IDS="${2:?--skip requires a value}"; shift ;;
    --agents) SMOKE_AGENTS="${2:?--agents requires a value}"; shift ;;
    --hf-model) SMOKE_HF_MODEL="${2:?--hf-model requires a value}"; shift ;;
    --allow-clone-test) SMOKE_TEST_BOOTSTRAP_CLONE=1 ;;
    --no-cleanup) SMOKE_CLEANUP=0 ;;
    # Already fully handled by the re-exec-through-tee wrapper above; just
    # consumed here (not an "Unknown option" error) when this is the inner,
    # already-wrapped invocation re-parsing the same original arguments.
    --log-file) shift ;;
    --no-log) ;;
    -h | --help) sed -n '/^# agent-harness-install/,/^# Exit code:/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

# The first --agents entry is installed in phase 05; later phases reuse it.
read -r SMOKE_PRIMARY_AGENT _ <<<"$SMOKE_AGENTS"
case "$SMOKE_PRIMARY_AGENT" in
  openclaw) SMOKE_PRIMARY_CLI=openclaw; SMOKE_PRIMARY_LABEL=OpenClaw ;;
  deepagents-code) SMOKE_PRIMARY_CLI=dcode; SMOKE_PRIMARY_LABEL=dcode ;;
  hermes) SMOKE_PRIMARY_CLI=hermes; SMOKE_PRIMARY_LABEL=Hermes ;;
  *) echo "--agents must start with openclaw, deepagents-code or hermes (got '${SMOKE_PRIMARY_AGENT}')" >&2; exit 2 ;;
esac

# -------------------------------------------------------------- reporting --
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
declare -a FAILED_CHECKS=()
CURRENT_PHASE=""

c_bold=$'\033[1m'; c_green=$'\033[1;32m'; c_red=$'\033[1;31m'
c_yellow=$'\033[1;33m'; c_cyan=$'\033[1;36m'; c_reset=$'\033[0m'
[[ -t 1 ]] || { c_bold=''; c_green=''; c_red=''; c_yellow=''; c_cyan=''; c_reset=''; }

phase_banner() {
  CURRENT_PHASE="$1"
  printf '\n%s=== %s ===%s\n' "$c_cyan" "$1" "$c_reset"
}
pass() { printf '  %sPASS%s  %s\n' "$c_green" "$c_reset" "$1"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail() {
  printf '  %sFAIL%s  %s\n' "$c_red" "$c_reset" "$1"
  [[ -n "${2:-}" ]] && printf '%s\n' "$2" | sed 's/^/        /'
  FAIL_COUNT=$((FAIL_COUNT + 1))
  FAILED_CHECKS+=("[$CURRENT_PHASE] $1")
}
skip() { printf '  %sSKIP%s  %s (%s)\n' "$c_yellow" "$c_reset" "$1" "${2:-}"; SKIP_COUNT=$((SKIP_COUNT + 1)); }
note() { printf '  %s-%s     %s\n' "$c_bold" "$c_reset" "$1"; }

# check DESC -- CMD [ARGS...]   (expects exit 0)
check() {
  local desc="$1"; shift
  local out
  if out="$("$@" 2>&1)"; then pass "$desc"; else fail "$desc" "$out"; fi
}
# check_fail DESC -- CMD [ARGS...]   (expects nonzero exit)
check_fail() {
  local desc="$1"; shift
  local out rc=0
  out="$("$@" 2>&1)" || rc=$?
  if [[ $rc -ne 0 ]]; then pass "$desc"; else fail "$desc" "expected failure, got success. output:
$out"; fi
}
# check_with_retry DESC RETRIES -- CMD [ARGS...]   (expects exit 0, retrying
# on failure -- only for genuinely network-dependent checks, e.g. a remote
# registry API through a corporate proxy, where a transient blip isn't a
# real bug; a persistent failure still reports FAIL after RETRIES attempts)
check_with_retry() {
  local desc="$1" retries="$2"; shift 2
  local out attempt=1
  while :; do
    out="$("$@" 2>&1)" && { pass "$desc"; return; }
    [[ $attempt -lt $retries ]] || break
    attempt=$((attempt + 1))
    sleep 2
  done
  fail "$desc" "$out"
}
# check_output_contains DESC PATTERN -- CMD [ARGS...]   (expects exit 0 AND pattern in output)
check_output_contains() {
  local desc="$1" pattern="$2"; shift 2
  local out rc=0
  out="$("$@" 2>&1)" || rc=$?
  if [[ $rc -eq 0 ]] && grep -qF -- "$pattern" <<<"$out"; then
    pass "$desc"
  else
    fail "$desc" "rc=$rc, expected to contain '$pattern'. output:
$out"
  fi
}
# check_fail_output_contains DESC PATTERN -- CMD [ARGS...]  (expects nonzero exit AND pattern)
check_fail_output_contains() {
  local desc="$1" pattern="$2"; shift 2
  local out rc=0
  out="$("$@" 2>&1)" || rc=$?
  if [[ $rc -ne 0 ]] && grep -qF -- "$pattern" <<<"$out"; then
    pass "$desc"
  else
    fail "$desc" "rc=$rc, expected failure containing '$pattern'. output:
$out"
  fi
}

agent_in_list() { [[ " $SMOKE_AGENTS " == *" $1 "* ]]; }

# ------------------------------------------------- isolated lib unit-test --
# Sources every scripts/lib/*.sh file (same order as scripts/install.sh) in
# a disposable bash -c subshell, then evaluates $1. Isolated because several
# lib functions call error() -> exit 1 on failure; running them in a nested
# subshell means that exit only ends the subshell, never this test runner.
LIB_ORDER="colors verify state sudo shim gpu-intel docker-setup nodejs python-setup openvino inference-router agents harness-mcp"
lib_eval() {
  local snippet="$1"
  bash -c '
    set -uo pipefail
    cd "'"$REPO_ROOT"'" || exit 99
    for f in '"$LIB_ORDER"'; do . "scripts/lib/${f}.sh"; done
    '"$snippet"'
  '
}

# ---------------------------------------------------------------- phases --
phase_00_prereqs() {
  phase_banner "00-prereqs: tool prerequisites"
  local tool
  # sudo/sha256sum are base-OS tools this suite assumes are already present
  # (not something ./startup.sh installs) -- checked up front since nothing
  # below can even run without them.
  for tool in sudo sha256sum; do
    check "required tool present: $tool" bash -c "command -v $tool"
  done

  # Every third-party agent installer in this project (OpenClaw, dcode,
  # Hermes) and scripts/lib/verify.sh's own fetch_and_verify do an HTTPS
  # download. A stale/incomplete CA trust store (common on minimal/fresh
  # cloud images) makes those fail with "SSL certificate problem: unable to
  # get local issuer certificate" -- a host prerequisite gap, not a product
  # bug -- so refresh it proactively rather than letting it surface later as
  # a confusing mid-install failure.
  check "ca-certificates is installed and up to date" \
    bash -c 'sudo apt-get update -qq && sudo apt-get install -y -qq --reinstall ca-certificates && sudo update-ca-certificates >/dev/null'

  if ! command -v shellcheck >/dev/null 2>&1; then
    note "shellcheck not found; attempting apt install (informational phase only)"
    sudo apt-get update -qq >/dev/null 2>&1 || true
    sudo apt-get install -y -qq shellcheck >/dev/null 2>&1 || true
  fi

  # install.sh now runs ./startup.sh automatically as its first step (see
  # scripts/install.sh's prepare_installer_host) -- called explicitly here
  # too so a prerequisite problem is reported in this early phase, not
  # buried inside phase_05's first real ./install.sh run. Also the thing
  # that actually installs curl/git on a fresh host (see below) -- checked
  # for *before* this, curl/git would always spuriously fail here on a
  # truly fresh machine even though this same phase goes on to fix it.
  check "./startup.sh installs/verifies Docker, Node.js, and Python" \
    env NON_INTERACTIVE=1 bash "$REPO_ROOT/startup.sh" --non-interactive

  for tool in curl git; do
    check "required tool present: $tool" bash -c "command -v $tool"
  done
}


phase_01_static() {
  phase_banner "01-static: syntax + shellcheck"
  local f
  while IFS= read -r -d '' f; do
    check "bash -n: ${f#"$REPO_ROOT"/}" bash -n "$f"
  done < <(find "$REPO_ROOT" -name '*.sh' -not -path '*/node_modules/*' -print0)

  if command -v shellcheck >/dev/null 2>&1; then
    local sc_out rc=0
    sc_out="$(find "$REPO_ROOT" -name '*.sh' -not -path '*/node_modules/*' -print0 \
      | xargs -0 shellcheck -x -s bash -S error 2>&1)" || rc=$?
    if [[ $rc -eq 0 ]]; then
      pass "shellcheck: no error-level findings across all *.sh files"
    else
      fail "shellcheck: error-level findings present" "$sc_out"
    fi
  else
    skip "shellcheck static analysis" "shellcheck not installed and apt install failed"
  fi
}

phase_02_selfcheck() {
  phase_banner "02-selfcheck: regression guards for known-fixed bugs"
  check_fail "uninstall.sh no longer sources removed scripts/lib/notice.sh" \
    bash -c "grep -q 'lib notice' '$REPO_ROOT/uninstall.sh'"
  check "agents.sh defines resolve_installed_agent (stale-default-agent fix)" \
    bash -c "grep -q 'resolve_installed_agent()' '$REPO_ROOT/scripts/lib/agents.sh'"
  check "openvino.sh defines ovms_is_managed (OVMS-managed-state fix)" \
    bash -c "grep -q 'ovms_is_managed()' '$REPO_ROOT/scripts/lib/openvino.sh'"
  check "install.sh validates --harness/--model have a value before use" \
    bash -c "grep -q -- '--harness requires a value' '$REPO_ROOT/scripts/install.sh'"
  check_fail "openvino.sh no longer pins the stale HARNESS_OVMS_IMAGE with no matching -py tag" \
    bash -c "grep -q '2026\\.4\\.0-gpu' '$REPO_ROOT/scripts/lib/openvino.sh'"
  # Regression guard for the fix's own consistency invariant: openvino.sh's
  # comments document that HARNESS_OVMS_EXPORT_MODEL_REF (the export-model-py
  # fallback exporter's pin) must track HARNESS_OVMS_EXPORT_IMAGE's version --
  # catches a future version bump to one without updating the other. (The
  # serving image, HARNESS_OVMS_IMAGE, is pinned independently of both.)
  check "HARNESS_OVMS_EXPORT_MODEL_REF stays in sync with HARNESS_OVMS_EXPORT_IMAGE's pinned version" \
    lib_eval '
      [[ "$HARNESS_OVMS_EXPORT_MODEL_REF" == "$_OVMS_EXPORT_MODEL_PINNED_REF" ]] || exit 1
      image_version="${HARNESS_OVMS_EXPORT_IMAGE#*:}"; image_version="${image_version%-py}"
      export_version="${HARNESS_OVMS_EXPORT_MODEL_REF#v}"
      [[ "$image_version" == "$export_version" ]]'
  # export_model_via_docker_pull (the default exporter) runs the same
  # optimum-cli/httpx conversion stack its two sibling exporters already
  # guard with assert_proxy_scheme_supported -- catches a regression where
  # that check gets dropped again (it was missing until this fix).
  check "export_model_via_docker_pull validates the proxy scheme before pulling/converting" \
    bash -c "awk '/^export_model_via_docker_pull\\(\\)/,/^\\}/' '$REPO_ROOT/scripts/lib/openvino.sh' | grep -q 'assert_proxy_scheme_supported'"
  # harness_llm_endpoint's resolve_advertised_host call must be a standalone
  # assignment (not embedded as a printf argument) so a failure inside it
  # (e.g. an advertised-host state-file tamper check) aborts via set -e
  # instead of silently producing a malformed empty-host endpoint that then
  # gets persisted into the agent's own config file. This logic now lives
  # in inference_router_endpoint (inference-router.sh), which
  # harness_llm_endpoint delegates to, not in harness_llm_endpoint itself.
  check "inference_router_endpoint propagates resolve_advertised_host failures (not embedded in printf)" \
    bash -c "awk '/^inference_router_endpoint\\(\\)/,/^\\}/' '$REPO_ROOT/scripts/lib/inference-router.sh' | grep -q 'host=\"\$(resolve_advertised_host)\" || return 1'"
  # wait_for_ovms_model_ready returns 1 on a plain readiness-poll timeout
  # (its own warn() is the complete, non-fatal signal) -- a bare call with
  # no `|| true` was silently killing the *entire* installer under set -e
  # partway through step 2, with no [ERROR] at all, whenever a model took
  # longer than 60s to report ready.
  check "ensure_inference_backend tolerates a wait_for_ovms_model_ready timeout" \
    bash -c "grep -qF 'wait_for_ovms_model_ready \"\$(model_dir_name \"\$HARNESS_HF_MODEL\")\" || true' '$REPO_ROOT/scripts/lib/openvino.sh'"
  # install.sh's own HARNESS_LLM_ENDPOINT resolution must not combine
  # `export VAR=\"\$(...)\"` into one statement -- export is a builtin
  # command, so (like printf/ok above) a failing command substitution
  # embedded in its argument is not checked by set -e; only a bare
  # `VAR=\$(cmd)` assignment's own failure is.
  check "install.sh's HARNESS_LLM_ENDPOINT export is split from its assignment" \
    bash -c "grep -q 'HARNESS_LLM_ENDPOINT=\"\${HARNESS_LLM_ENDPOINT:-\$(harness_llm_endpoint)}\"' '$REPO_ROOT/scripts/install.sh' && grep -q '^  export HARNESS_LLM_ENDPOINT\$' '$REPO_ROOT/scripts/install.sh'"
  # print_status's OVMS-running branch must check harness_llm_endpoint's
  # exit status (via `if endpoint=\$(...); then`) rather than embedding the
  # call directly in ok's argument list, so a resolve_advertised_host
  # failure degrades to a clear warning instead of a silent blank endpoint.
  check "print_status detects a harness_llm_endpoint failure instead of showing a blank endpoint" \
    bash -c "grep -q 'if endpoint=\"\$(harness_llm_endpoint)\"; then' '$REPO_ROOT/scripts/install.sh'"
  # export_model_via_docker_pull's "already exported" fast path must
  # re-register the model (idempotent), not just skip straight to return --
  # otherwise a model directory that exists on disk but lost its
  # config.json entry (reset/edited config.json, a crash between pull and
  # registration on an earlier run, etc.) stays permanently unregistered
  # and OVMS 404s on it forever, with the installer reporting success.
  check "export_model_via_docker_pull's already-exported fast path re-registers the model" \
    bash -c "awk '/^export_model_via_docker_pull\\(\\)/,/^command_exists docker/' '$REPO_ROOT/scripts/lib/openvino.sh' | grep -q '_add_model_config_entry_locked'"
  # mktemp creates its file mode 0600 by default -- the published OVMS
  # image's server runs as a fixed non-root uid (ovms, 5000), not the host
  # user, so a config.json replaced without an explicit chmod becomes
  # unreadable by the running container and OVMS crash-loops on every
  # restart after the first real model registration ("Configuration file
  # is invalid" -- confirmed against a real server log).
  check "_add_model_config_entry_locked keeps config.json readable by OVMS's container uid" \
    bash -c "awk '/^_add_model_config_entry_locked\\(\\)/,/^}/' '$REPO_ROOT/scripts/lib/openvino.sh' | grep -q 'chmod 644 \"\$tmp\"'"
  check "_remove_model_from_ovms_config_locked keeps config.json readable by OVMS's container uid" \
    bash -c "awk '/^_remove_model_from_ovms_config_locked\\(\\)/,/^}/' '$REPO_ROOT/scripts/lib/openvino.sh' | grep -q 'chmod 644 \"\$tmp\"'"
  # run_agent_onboard's model_hint fallback must not be the bare literal
  # "default" anymore -- that never matches a real registered model name
  # (exports register under the HF model's own basename), so a standalone
  # "./install.sh onboard" run (no --model/HARNESS_LLM_MODEL) against an
  # already-exported model always 404'd even though the server was healthy.
  check "run_agent_onboard auto-discovers the sole registered model instead of a bare 'default'" \
    bash -c "grep -q 'ovms_sole_registered_model_name' '$REPO_ROOT/scripts/lib/agents.sh'"
  # dcode's own internal LangGraph dev-server health check over-eagerly
  # respects HTTP_PROXY/HTTPS_PROXY for what's purely local loopback
  # traffic -- behind a corporate proxy, that gets routed through the
  # proxy (which 403s it), and dcode times out after 60s. Neither that
  # health check nor the actual OVMS call afterward need external network
  # access, so the onboarding smoke test must strip these vars for just
  # this invocation -- confirmed empirically (403/60s-timeout with them
  # set, clean success in ~1-2s without).
  check "run_agent_onboard strips proxy vars for dcode's own onboarding smoke test" \
    bash -c "awk '/^run_agent_onboard\\(\\)/,/^}/' '$REPO_ROOT/scripts/lib/agents.sh' | grep -q 'env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy'"
  # --device alone doesn't grant a non-root container GPU access -- OVMS's
  # own docs (accelerators.md) document --group-add=<render-gid> as a
  # required *additional* flag. Without it, GPU acceleration would silently
  # fail (permission denied opening the render node) on any real GPU host,
  # even though --device was correctly attached and target_device=GPU was
  # selected -- confirmed as a real gap, not caught by any CPU-only test.
  check "docker-setup.sh defines intel_gpu_docker_group_add_args" \
    bash -c "grep -q 'intel_gpu_docker_group_add_args()' '$REPO_ROOT/scripts/lib/docker-setup.sh'"
  check "ensure_openvino_model_server passes --group-add alongside --device" \
    bash -c "awk '/^ensure_openvino_model_server\\(\\)/,/^}/' '$REPO_ROOT/scripts/lib/openvino.sh' | grep -q 'group_add_args=\"\$(intel_gpu_docker_group_add_args)\"'"
  check "export_model_via_docker_pull passes --device/--group-add when targeting GPU (was missing --device entirely)" \
    bash -c "awk '/^export_model_via_docker_pull\\(\\)/,/^}/' '$REPO_ROOT/scripts/lib/openvino.sh' | grep -q 'gpu_args=\"\$(intel_gpu_docker_device_args)\"'"
}

phase_03_libunit() {
  phase_banner "03-libunit: pure library-function checks (isolated, no side effects)"

  check "version_gte: 24.16.0 >= 24.16.0" lib_eval 'version_gte 24.16.0 24.16.0'
  check_fail "version_gte: 24.15.9 >= 24.16.0 is false" lib_eval 'version_gte 24.15.9 24.16.0'
  check "node_version_in_unsupported_gap: 25.0.0 is in the gap" lib_eval 'node_version_in_unsupported_gap 25.0.0'
  check_fail "node_version_in_unsupported_gap: 26.1.0 is not in the gap" lib_eval 'node_version_in_unsupported_gap 26.1.0'

  check_output_contains "canonical_agent_name: OpenClaw -> openclaw" "openclaw" lib_eval 'canonical_agent_name OpenClaw'
  check_output_contains "canonical_agent_name: deep-agents -> deepagents-code" "deepagents-code" lib_eval 'canonical_agent_name deep-agents'
  check_output_contains "canonical_agent_name: dcode -> deepagents-code (alias fix)" "deepagents-code" lib_eval 'canonical_agent_name dcode'
  check_output_contains "canonical_agent_name: Hermes -> hermes" "hermes" lib_eval 'canonical_agent_name Hermes'
  check_output_contains "canonical_agent_name: unknown input is lowercased, not raw-passthrough" "bogus-agent" lib_eval 'canonical_agent_name Bogus-Agent'

  check_output_contains "agent_cli_bin: openclaw -> openclaw" "openclaw" lib_eval 'agent_cli_bin openclaw'
  check_output_contains "agent_cli_bin: deepagents-code -> dcode" "dcode" lib_eval 'agent_cli_bin deepagents-code'
  check_output_contains "agent_cli_bin: hermes -> hermes" "hermes" lib_eval 'agent_cli_bin hermes'
  check_fail "agent_cli_bin: unknown agent returns nonzero (regression: was silent empty string)" \
    lib_eval 'agent_cli_bin bogus-agent'

  check "validate_model_name: accepts qwen2.5-7b" lib_eval 'validate_model_name qwen2.5-7b'
  check_fail "validate_model_name: rejects a dot-prefixed name" lib_eval 'validate_model_name .hidden'
  check_fail "validate_model_name: rejects path traversal" lib_eval 'validate_model_name ../etc'

  check "validate_skill_name: accepts my-skill" lib_eval 'validate_skill_name my-skill'
  check_fail "validate_skill_name: rejects .." lib_eval 'validate_skill_name ..'
  check_fail "validate_skill_name: rejects a path separator" lib_eval 'validate_skill_name a/b'

  check "validate_hf_model_id: accepts org/name" lib_eval 'validate_hf_model_id Qwen/Qwen2.5-0.5B-Instruct'
  check "validate_hf_model_id: accepts a bare name" lib_eval 'validate_hf_model_id my-model'
  check_fail "validate_hf_model_id: rejects a trailing slash" lib_eval 'validate_hf_model_id org/'
  check_fail "validate_hf_model_id: rejects traversal" lib_eval 'validate_hf_model_id ../../x'
  check_fail "validate_hf_model_id: rejects empty" lib_eval 'validate_hf_model_id ""'
  check_fail "validate_hf_model_id: rejects a leading dot" lib_eval 'validate_hf_model_id org/.hidden'

  # Per-hub --model validation (the Model Download hubs).
  check "validate_model_for_hub: openvino accepts org/name" lib_eval 'validate_model_for_hub openvino Qwen/Qwen2.5-0.5B-Instruct'
  check_fail "validate_model_for_hub: openvino rejects a trailing slash" lib_eval 'validate_model_for_hub openvino org/'
  check "validate_model_for_hub: ollama accepts name:tag" lib_eval 'validate_model_for_hub ollama llama3.2:3b'
  check "validate_model_for_hub: ollama accepts a namespaced name" lib_eval 'validate_model_for_hub ollama library/llama3.2'
  check "validate_model_for_hub: ollama accepts a Hugging Face GGUF reference with an upper-case tag" \
    lib_eval 'validate_model_for_hub ollama hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_K_M'
  check_fail "validate_model_for_hub: ollama rejects a second colon" lib_eval 'validate_model_for_hub ollama a:b:c'
  check_fail "validate_model_for_hub: ollama rejects more than three path parts" lib_eval 'validate_model_for_hub ollama a/b/c/d'
  check_fail "validate_model_for_hub: ollama rejects spaces" lib_eval 'validate_model_for_hub ollama "llama 3"'
  check_fail "validate_model_for_hub: ollama rejects traversal" lib_eval 'validate_model_for_hub ollama ../x'
  check_fail "validate_model_for_hub: remote-url needs a url in --model-config" lib_eval 'validate_model_for_hub remote-url my-model'
  check "validate_model_for_hub: remote-url accepts a name once a url is configured" \
    lib_eval 'HARNESS_MODEL_CONFIG_JSON="{\"url\":\"https://github.com/o/r/raw/main/{name}.tar\"}"; validate_model_for_hub remote-url my-model'
  check_fail "validate_model_for_hub: remote-url rejects a slash in the name" \
    lib_eval 'HARNESS_MODEL_CONFIG_JSON="{\"url\":\"u\"}"; validate_model_for_hub remote-url a/b'
  check "validate_model_for_hub: ultralytics accepts a comma-separated list" lib_eval 'validate_model_for_hub ultralytics yolov8n,yolov8s'
  check_fail "validate_model_for_hub: ultralytics rejects shell metacharacters" lib_eval 'validate_model_for_hub ultralytics "yolo;rm"'
  check_fail "validate_model_for_hub: geti needs GETI_* in the environment" \
    lib_eval 'unset GETI_HOST GETI_TOKEN GETI_WORKSPACE_ID; validate_model_for_hub geti "My Project"'
  check "validate_model_for_hub: geti accepts a project name with spaces once configured" \
    lib_eval 'GETI_HOST=h GETI_TOKEN=t GETI_WORKSPACE_ID=w; validate_model_for_hub geti "My Project"'
  check_fail "validate_model_for_hub: hls needs --model-type" lib_eval 'HARNESS_MODEL_TYPE=; validate_model_for_hub hls hls-3d-pose'
  check "validate_model_for_hub: hls accepts a valid type" lib_eval 'HARNESS_MODEL_TYPE=3d-pose; validate_model_for_hub hls hls-3d-pose'
  check_fail "validate_model_for_hub: unknown hub is rejected" lib_eval 'validate_model_for_hub bogus x'

  check_output_contains "model_dir_name: strips the org prefix" "Qwen2.5-0.5B-Instruct" lib_eval 'model_dir_name Qwen/Qwen2.5-0.5B-Instruct'
  check_output_contains "model_dir_name: makes an Ollama tag filesystem-safe" "llama3.2-3b" lib_eval 'model_dir_name llama3.2:3b'

  check "model_hub_unserved_reason: openvino may be served" lib_eval 'model_hub_unserved_reason openvino'
  check "model_hub_unserved_reason: remote-url may be served (if it has a graph.pbtxt)" lib_eval 'model_hub_unserved_reason remote-url'
  check_fail "model_hub_unserved_reason: ollama is not served (yet)" lib_eval 'model_hub_unserved_reason ollama'
  check_output_contains "model_hub_unserved_reason: ollama explains why" "not loadable by OVMS" lib_eval 'model_hub_unserved_reason ollama || true'
  check_fail "model_hub_unserved_reason: ultralytics is not served" lib_eval 'model_hub_unserved_reason ultralytics'

  # --model-hub alone selects the Model Download exporter.
  check_output_contains "apply_model_source_defaults: default hub keeps the docker-pull exporter" "docker-pull" \
    lib_eval 'apply_model_source_defaults; printf "%s" "$HARNESS_OVMS_EXPORTER"'
  check_output_contains "apply_model_source_defaults: explicit openvino hub keeps docker-pull" "docker-pull" \
    lib_eval 'HARNESS_MODEL_HUB=openvino HARNESS_MODEL_HUB_WAS_SET=1; apply_model_source_defaults; printf "%s" "$HARNESS_OVMS_EXPORTER"'
  check_output_contains "apply_model_source_defaults: --model-hub ollama selects model-download" "model-download" \
    lib_eval 'HARNESS_MODEL_HUB=ollama HARNESS_MODEL_HUB_WAS_SET=1; apply_model_source_defaults; printf "%s" "$HARNESS_OVMS_EXPORTER"'
  check_fail "apply_model_source_defaults: a conflicting explicit exporter is rejected" \
    lib_eval 'HARNESS_MODEL_HUB=ollama HARNESS_MODEL_HUB_WAS_SET=1 HARNESS_OVMS_EXPORTER=docker-pull HARNESS_OVMS_EXPORTER_WAS_SET=1; apply_model_source_defaults'
  check_fail "apply_model_source_defaults: an unknown hub is rejected" lib_eval 'HARNESS_MODEL_HUB=bogus; apply_model_source_defaults'
  check_fail "apply_model_source_defaults: an invalid precision is rejected" lib_eval 'HARNESS_MODEL_PRECISION=int3; apply_model_source_defaults'
  check_fail "apply_model_source_defaults: an invalid --model for the hub is rejected before any install work" \
    lib_eval 'HARNESS_HF_MODEL="org/"; apply_model_source_defaults'
  check "apply_model_source_defaults: --model is not validated when routing to an external endpoint" \
    lib_eval 'HARNESS_LLM_ROUTER_ENDPOINT=http://x/v1 HARNESS_HF_MODEL="any name"; apply_model_source_defaults'
  check_output_contains "apply_model_source_defaults: warns about a model option the exporter ignores" "is ignored by" \
    lib_eval 'HARNESS_HF_MODEL=org/m HARNESS_MODEL_OPTS_GIVEN=" device"; apply_model_source_defaults 2>&1'

  # Model Download's docker client config: proxy settings are injected into
  # a private DOCKER_CONFIG copy so get_model.sh's container can reach the
  # network behind a proxy.
  check_output_contains "model_download_docker_config: prints nothing when no proxy is set" "[none]" \
    lib_eval 'unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy; export HOME=$(mktemp -d); out=$(model_download_docker_config); echo "[${out:-none}]"'
  check_output_contains "model_download_docker_config: writes the proxy into a private config.json" "http://p:3128" \
    lib_eval 'unset http_proxy https_proxy; export HOME=$(mktemp -d); HTTP_PROXY=http://p:3128; d=$(model_download_docker_config); cat "$d/config.json"'
  check_output_contains "model_download_docker_config: keeps existing Docker client settings (e.g. credsStore)" "desktop" \
    lib_eval 'unset http_proxy https_proxy; export HOME=$(mktemp -d); mkdir -p "$HOME/.docker"; printf "%s" "{\"credsStore\":\"desktop\"}" > "$HOME/.docker/config.json"; HTTPS_PROXY=http://p:3128; d=$(model_download_docker_config); cat "$d/config.json"'
  check_output_contains "model_download_docker_config: config.json is owner-only" "600" \
    lib_eval 'unset http_proxy https_proxy; export HOME=$(mktemp -d); HTTP_PROXY=http://p:3128; d=$(model_download_docker_config); stat -c %a "$d/config.json"'
  check_output_contains "model_download_docker_config: links an existing contexts dir so a non-default context keeps working" "contexts" \
    lib_eval 'unset http_proxy https_proxy; export HOME=$(mktemp -d); mkdir -p "$HOME/.docker/contexts"; HTTP_PROXY=http://p:3128; d=$(model_download_docker_config); ls "$d"'

  check "ovms_model_registered: finds a registered model" \
    lib_eval 'HARNESS_MODELS_DIR=$(mktemp -d); printf "%s" "{\"model_config_list\":[{\"config\":{\"name\":\"a\",\"base_path\":\"a\"}}]}" > "$HARNESS_MODELS_DIR/config.json"; ovms_model_registered a'
  check_fail "ovms_model_registered: does not match a different name" \
    lib_eval 'HARNESS_MODELS_DIR=$(mktemp -d); printf "%s" "{\"model_config_list\":[{\"config\":{\"name\":\"a\",\"base_path\":\"a\"}}]}" > "$HARNESS_MODELS_DIR/config.json"; ovms_model_registered b'
  check_fail "ovms_model_registered: false when there is no config.json" lib_eval 'HARNESS_MODELS_DIR=$(mktemp -d); ovms_model_registered a'

  # The model name onboarding wires an agent to.
  local hint_cfg='HARNESS_MODELS_DIR=$(mktemp -d); printf "%s" "{\"model_config_list\":[{\"config\":{\"name\":\"a\",\"base_path\":\"a\"}}]}" > "$HARNESS_MODELS_DIR/config.json"; '
  check_output_contains "resolve_onboarding_model_hint: an external router keeps the model name exactly as given (minus org/)" "llama3.2:3b" \
    lib_eval 'HARNESS_LLM_ROUTER_ENDPOINT=http://x/v1 HARNESS_HF_MODEL=library/llama3.2:3b; resolve_onboarding_model_hint'
  check_output_contains "resolve_onboarding_model_hint: a model OVMS serves is used" "a" \
    lib_eval "${hint_cfg}"'HARNESS_HF_MODEL=org/a; resolve_onboarding_model_hint'
  check_output_contains "resolve_onboarding_model_hint: an unserved download falls back to the one registered model" "a" \
    lib_eval "${hint_cfg}"'HARNESS_HF_MODEL=ollama-x; resolve_onboarding_model_hint'
  check_output_contains "resolve_onboarding_model_hint: nothing registered falls back to default" "default" \
    lib_eval 'HARNESS_MODELS_DIR=$(mktemp -d); HARNESS_HF_MODEL=org/zz; resolve_onboarding_model_hint'

  # What a finished Model Download run means for OVMS (_finish_model_download):
  # served iff the download contains a graph.pbtxt and the hub can produce one.
  local fin_prefix='export HOME=$(mktemp -d); HARNESS_MODELS_DIR=$(mktemp -d); '
  check_output_contains "_finish_model_download: an Ollama download is tracked, not registered, and explains why" "not loadable by OVMS" \
    lib_eval "${fin_prefix}"'mkdir -p "$HARNESS_MODELS_DIR/o/ollama/llama3"; _finish_model_download ollama llama3.2:3b llama3.2-3b "$HARNESS_MODELS_DIR/o/ollama/llama3" 2>&1; echo "registered=$HARNESS_LAST_MODEL_REGISTERED"'
  check_output_contains "_finish_model_download: an Ollama download leaves HARNESS_LAST_MODEL_REGISTERED=0" "registered=0" \
    lib_eval "${fin_prefix}"'mkdir -p "$HARNESS_MODELS_DIR/o/ollama/llama3"; _finish_model_download ollama llama3.2:3b llama3.2-3b "$HARNESS_MODELS_DIR/o/ollama/llama3" >/dev/null 2>&1; echo "registered=$HARNESS_LAST_MODEL_REGISTERED"'
  check_output_contains "_finish_model_download: an Ollama download is listed as tracked in unregistered-downloads.json" "llama3.2-3b" \
    lib_eval "${fin_prefix}"'mkdir -p "$HARNESS_MODELS_DIR/o/ollama/llama3"; _finish_model_download ollama llama3.2:3b llama3.2-3b "$HARNESS_MODELS_DIR/o/ollama/llama3" >/dev/null 2>&1; cat "$HARNESS_MODELS_DIR/unregistered-downloads.json"'
  check_output_contains "_finish_model_download: a vision hub is never served, even if a graph.pbtxt is present" "registered=0" \
    lib_eval "${fin_prefix}"'mkdir -p "$HARNESS_MODELS_DIR/y"; touch "$HARNESS_MODELS_DIR/y/graph.pbtxt"; _finish_model_download ultralytics yolov8n yolov8n "$HARNESS_MODELS_DIR/y" >/dev/null 2>&1; echo "registered=$HARNESS_LAST_MODEL_REGISTERED"'
  check_output_contains "_finish_model_download: a remote-url tarball with a graph.pbtxt is registered" "registered=1" \
    lib_eval "${fin_prefix}"'mkdir -p "$HARNESS_MODELS_DIR/r/remote-url/m/sub"; touch "$HARNESS_MODELS_DIR/r/remote-url/m/sub/graph.pbtxt"; _finish_model_download remote-url m m "$HARNESS_MODELS_DIR/r/remote-url/m" >/dev/null 2>&1; echo "registered=$HARNESS_LAST_MODEL_REGISTERED"'
  check_output_contains "_finish_model_download: the registered base_path points at the directory holding graph.pbtxt" "r/remote-url/m/sub" \
    lib_eval "${fin_prefix}"'mkdir -p "$HARNESS_MODELS_DIR/r/remote-url/m/sub"; touch "$HARNESS_MODELS_DIR/r/remote-url/m/sub/graph.pbtxt"; _finish_model_download remote-url m m "$HARNESS_MODELS_DIR/r/remote-url/m" >/dev/null 2>&1; cat "$HARNESS_MODELS_DIR/config.json"'
  check_output_contains "_finish_model_download: a remote-url tarball without a graph.pbtxt is tracked" "registered=0" \
    lib_eval "${fin_prefix}"'mkdir -p "$HARNESS_MODELS_DIR/r/remote-url/m"; touch "$HARNESS_MODELS_DIR/r/remote-url/m/model.xml"; _finish_model_download remote-url m m "$HARNESS_MODELS_DIR/r/remote-url/m" >/dev/null 2>&1; echo "registered=$HARNESS_LAST_MODEL_REGISTERED"'
  check_output_contains "_finish_model_download: a pre-converted Hugging Face repo with a graph.pbtxt is registered" "registered=1" \
    lib_eval "${fin_prefix}"'mkdir -p "$HARNESS_MODELS_DIR/h/huggingface/p"; touch "$HARNESS_MODELS_DIR/h/huggingface/p/graph.pbtxt"; _finish_model_download huggingface org/p p "$HARNESS_MODELS_DIR/h/huggingface/p" >/dev/null 2>&1; echo "registered=$HARNESS_LAST_MODEL_REGISTERED"'
  check_output_contains "_finish_model_download: the openvino hub registers the graph under <output>/<model id>/" "registered=1" \
    lib_eval "${fin_prefix}"'mkdir -p "$HARNESS_MODELS_DIR/m/org/model"; touch "$HARNESS_MODELS_DIR/m/org/model/graph.pbtxt"; _finish_model_download openvino org/model model "$HARNESS_MODELS_DIR/m" >/dev/null 2>&1; echo "registered=$HARNESS_LAST_MODEL_REGISTERED"'
  check_output_contains "_finish_model_download: the openvino hub without a graph.pbtxt warns and registers nothing" "registered=0" \
    lib_eval "${fin_prefix}"'mkdir -p "$HARNESS_MODELS_DIR/m"; _finish_model_download openvino org/model model "$HARNESS_MODELS_DIR/m" >/dev/null 2>&1; echo "registered=$HARNESS_LAST_MODEL_REGISTERED"'

  check "safe_agent_data_dir: accepts a dir under \$HOME" lib_eval 'safe_agent_data_dir "$HOME/.hermes"'
  check_fail "safe_agent_data_dir: rejects /" lib_eval 'safe_agent_data_dir /'
  check_fail "safe_agent_data_dir: rejects \$HOME" lib_eval 'safe_agent_data_dir "$HOME"'
  check_fail "safe_agent_data_dir: rejects a parent of \$HOME" lib_eval 'safe_agent_data_dir "$(dirname "$HOME")"'
  check_fail "safe_agent_data_dir: rejects a relative path" lib_eval 'safe_agent_data_dir .hermes'

  check_output_contains "resolve_installed_agent: defaults to openclaw with no marker/env" \
    "openclaw" lib_eval 'export HOME=$(mktemp -d); unset HARNESS_AGENT; resolve_installed_agent'
  check_output_contains "resolve_installed_agent: HARNESS_AGENT wins over a persisted marker" \
    "hermes" lib_eval '
      export HOME=$(mktemp -d)
      mkdir -p "$HOME/.agent-harness-install"; printf openclaw > "$HOME/.agent-harness-install/installed-agent"
      export HARNESS_AGENT=hermes
      resolve_installed_agent'
  check_output_contains "resolve_installed_agent: falls back to the persisted marker, not a hardcoded default (regression)" \
    "hermes" lib_eval '
      export HOME=$(mktemp -d)
      mkdir -p "$HOME/.agent-harness-install"; printf hermes > "$HOME/.agent-harness-install/installed-agent"
      unset HARNESS_AGENT
      resolve_installed_agent'

  check_output_contains "ovms_is_managed: marker=1 -> managed" "managed" \
    lib_eval 'export HOME=$(mktemp -d); record_ovms_managed 1; ovms_is_managed && echo managed || echo not-managed'
  check_output_contains "ovms_is_managed: marker=0 -> not managed" "not-managed" \
    lib_eval 'export HOME=$(mktemp -d); record_ovms_managed 0; ovms_is_managed && echo managed || echo not-managed'
  # No unset here: openvino.sh already defaults HARNESS_LLM_ROUTER_ENDPOINT to
  # "" at source time, same as every real call site (uninstall.sh always
  # sources openvino.sh first) -- unsetting it afterward would only be an
  # artifact of this test, not a state ovms_is_managed is ever called in for real.
  check_output_contains "ovms_is_managed: no marker, no router endpoint -> managed (legacy fallback)" "managed" \
    lib_eval 'export HOME=$(mktemp -d); ovms_is_managed && echo managed || echo not-managed'
  check_output_contains "ovms_is_managed: no marker, router endpoint set -> not managed (legacy fallback)" "not-managed" \
    lib_eval 'export HOME=$(mktemp -d); export HARNESS_LLM_ROUTER_ENDPOINT=http://example:1/v1; ovms_is_managed && echo managed || echo not-managed'
  check_output_contains "ovms_is_managed: persisted marker overrides the CURRENT env var (regression: uninstall bug)" \
    "managed" lib_eval '
      export HOME=$(mktemp -d)
      record_ovms_managed 1
      export HARNESS_LLM_ROUTER_ENDPOINT=http://example:1/v1
      ovms_is_managed && echo managed || echo not-managed'

  # ovms_internal_endpoint: IR must address OVMS by container name + its
  # internal port (8000), never the host-published/loopback address --
  # see ensure_backend_network (regression: IR couldn't reach OVMS at all
  # when this used ovms_endpoint's host-facing URL instead).
  check_output_contains "ovms_internal_endpoint: container-name URL, not loopback" \
    "http://agent-harness-install-ovms:8000/v3" lib_eval 'ovms_internal_endpoint'
  check_output_contains "harness_llm_endpoint: delegates to inference_router_endpoint (no duplicated URL logic)" \
    "/v1" lib_eval 'export HOME=$(mktemp -d); harness_llm_endpoint'
  check_output_contains "HARNESS_MODEL_HUB defaults to openvino (Hugging Face + conversion)" \
    "openvino" lib_eval 'printf "%s" "$HARNESS_MODEL_HUB"'
  check_output_contains "HARNESS_MODEL_TYPE has no blanket default (hub-specific, not always llm)" \
    "empty-ok" lib_eval '[[ -z "$HARNESS_MODEL_TYPE" ]] && echo empty-ok || echo "got: $HARNESS_MODEL_TYPE"'
}

phase_04_bootstrap() {
  phase_banner "04-bootstrap: standalone install.sh regression checks"
  check "install.sh --help delegates cleanly from a source checkout" bash "$REPO_ROOT/install.sh" --help

  local tmp
  tmp="$(mktemp -d)"
  cp "$REPO_ROOT/install.sh" "$tmp/install.sh"
  chmod +x "$tmp/install.sh"

  check_fail_output_contains "standalone fetch with no HARNESS_INSTALL_REPO errors clearly" "HARNESS_INSTALL_REPO" \
    env -u HARNESS_INSTALL_REPO -u HARNESS_INSTALL_REF bash "$tmp/install.sh" --help
  check_fail_output_contains "standalone fetch with REPO but no REF errors clearly" "HARNESS_INSTALL_REF is required" \
    env -u HARNESS_INSTALL_REF HARNESS_INSTALL_REPO="https://example.invalid/x.git" bash "$tmp/install.sh" --help
  check_fail_output_contains "standalone fetch rejects a plaintext http:// repo URL" "https://" \
    env HARNESS_INSTALL_REPO="http://example.invalid/x.git" HARNESS_INSTALL_REF=main bash "$tmp/install.sh" --help

  if [[ "$SMOKE_TEST_BOOTSTRAP_CLONE" == "1" ]]; then
    local origin_url head_sha
    origin_url="$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null || true)"
    head_sha="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || true)"
    if [[ -n "$origin_url" && -n "$head_sha" ]]; then
      check_output_contains "standalone fetch clones a real pinned ref and delegates" "agent-harness-install" \
        env HARNESS_INSTALL_REPO="$origin_url" HARNESS_INSTALL_REF="$head_sha" bash "$tmp/install.sh" --help
    else
      skip "live git-clone bootstrap test" "could not resolve this repo's origin/HEAD"
    fi
  else
    skip "live git-clone bootstrap test" "pass --allow-clone-test to enable (does a real git fetch)"
  fi
  rm -rf "$tmp"
}

phase_05_install_primary() {
  phase_banner "05-install: first agent (${SMOKE_PRIMARY_AGENT}), CPU-only, exports the smoke model"
  check "./install.sh status is read-only and does not crash before anything is installed" \
    env NON_INTERACTIVE=1 bash "$REPO_ROOT/install.sh" status

  check "full install: --harness ${SMOKE_PRIMARY_AGENT} --non-interactive --skip-gpu-check --model ${SMOKE_HF_MODEL}" \
    env NON_INTERACTIVE=1 bash "$REPO_ROOT/install.sh" --harness "$SMOKE_PRIMARY_AGENT" --non-interactive --skip-gpu-check --model "$SMOKE_HF_MODEL"

  # Mirrors the installer's own "open a new terminal" guidance so later
  # phases (separate processes) can resolve node/openclaw/dcode/hermes the
  # same way a real user's next shell would.
  export NVM_DIR="$HOME/.nvm"
  # shellcheck disable=SC1091
  [[ -s "$NVM_DIR/nvm.sh" ]] && . "$NVM_DIR/nvm.sh"
  export PATH="$HOME/.local/bin:$PATH"

  check "docker info succeeds (via ./startup.sh in phase 00)" docker info
  check "node --version resolves (via ./startup.sh in phase 00)" bash -c 'command -v node'
  check "${SMOKE_PRIMARY_CLI} CLI resolves on PATH after install" bash -c "command -v ${SMOKE_PRIMARY_CLI}"
  check_output_contains "installed-agent marker == ${SMOKE_PRIMARY_AGENT}" "$SMOKE_PRIMARY_AGENT" cat "$HOME/.agent-harness-install/installed-agent"
  check_output_contains "ovms-managed marker == 1 (no external router configured)" "1" cat "$HOME/.agent-harness-install/ovms-managed"
  if [[ "$SMOKE_PRIMARY_AGENT" == "openclaw" ]]; then
    check_output_contains "OpenClaw's 'ovms' provider was registered (onboarding fix)" "ovms" \
      bash -c "openclaw config get models.providers --json | grep -o ovms"
  fi
}

phase_06_status() {
  phase_banner "06-status: combined health view"
  check "./install.sh status succeeds post-install" bash "$REPO_ROOT/install.sh" status
  check_output_contains "status mentions ${SMOKE_PRIMARY_LABEL} as installed" "$SMOKE_PRIMARY_LABEL" bash "$REPO_ROOT/install.sh" status
}

phase_07_optparsing() {
  phase_banner "07-optparsing: unbound-variable regression checks"
  check_fail_output_contains "install.sh --harness with no value errors (not 'unbound variable')" "requires a value" \
    bash "$REPO_ROOT/install.sh" --harness
  check_fail_output_contains "install.sh --model with no value errors (not 'unbound variable')" "requires a value" \
    bash "$REPO_ROOT/install.sh" --model
  check_fail_output_contains "uninstall.sh --harness with no value errors (not 'unbound variable')" "requires a value" \
    bash "$REPO_ROOT/uninstall.sh" --harness
  # The --model-* options are validated before startup.sh installs anything,
  # so these fail fast without touching the host.
  local opt
  for opt in --model-hub --model-config --model-revision --model-type --model-precision --model-device; do
    check_fail_output_contains "install.sh $opt with no value errors (not 'unbound variable')" "requires a value" \
      bash "$REPO_ROOT/install.sh" "$opt"
  done
  check_fail_output_contains "install.sh rejects an unknown --model-hub" "Unknown model hub" \
    bash "$REPO_ROOT/install.sh" --model-hub bogus
  check_fail_output_contains "install.sh without --model fails fast when it cannot prompt (no default model)" "No model selected" \
    env NON_INTERACTIVE=1 HARNESS_MODELS_DIR=/nonexistent-smoke-models-dir bash "$REPO_ROOT/install.sh"
  check_fail_output_contains "install.sh rejects an invalid --model-precision" "Invalid model precision" \
    bash "$REPO_ROOT/install.sh" --model-precision int3
  check_fail_output_contains "install.sh rejects a malformed Hugging Face --model before installing anything" "Invalid --model" \
    bash "$REPO_ROOT/install.sh" --model "org/"
  check_fail_output_contains "install.sh rejects remote-url without --model-config" "--model-config" \
    bash "$REPO_ROOT/install.sh" --model-hub remote-url --model my-model
  check_fail_output_contains "install.sh rejects a conflicting HARNESS_OVMS_EXPORTER for a non-default hub" "needs the model-download exporter" \
    env HARNESS_OVMS_EXPORTER=docker-pull bash "$REPO_ROOT/install.sh" --model-hub ollama --model llama3.2
  check_fail_output_contains "install.sh rejects geti without GETI_* in the environment" "GETI_HOST" \
    env -u GETI_HOST -u GETI_TOKEN -u GETI_WORKSPACE_ID bash "$REPO_ROOT/install.sh" --model-hub geti --model "My Project"
}

phase_08_agent_resolution() {
  phase_banner "08-agent-resolution: stale-default + silent-no-op regression checks (live)"
  local marker="$HOME/.agent-harness-install/installed-agent"
  local saved; saved="$(cat "$marker" 2>/dev/null || true)"

  check_output_contains "onboard (HARNESS_AGENT unset) operates on the persisted agent, not a hardcoded default" \
    "$SMOKE_PRIMARY_LABEL" env -u HARNESS_AGENT bash "$REPO_ROOT/install.sh" onboard

  printf 'totally-bogus' >"$marker"
  check_fail_output_contains "onboard errors loudly on an unrecognized persisted agent (regression: was a silent no-op)" \
    "Unknown agent" env -u HARNESS_AGENT bash "$REPO_ROOT/install.sh" onboard
  check "status degrades gracefully (does not crash) on the same unrecognized marker" \
    bash "$REPO_ROOT/install.sh" status

  printf '%s' "$saved" >"$marker"
}

phase_09_other_agents() {
  phase_banner "09-install: remaining agents"
  if agent_in_list deepagents-code && [[ "$SMOKE_PRIMARY_AGENT" != "deepagents-code" ]]; then
    check "full install: --harness deepagents-code (dcode, pinned verified installer)" \
      env NON_INTERACTIVE=1 \
      bash "$REPO_ROOT/install.sh" --harness deepagents-code --non-interactive --skip-gpu-check
    export PATH="$HOME/.local/bin:$PATH"
    check "dcode CLI resolves on PATH after install" bash -c 'command -v dcode'
    check_output_contains "installed-agent marker == deepagents-code" "deepagents-code" cat "$HOME/.agent-harness-install/installed-agent"
    check "dcode's config.toml carries the managed-provider markers (onboarding wiring)" \
      bash -c "grep -q 'BEGIN agent-harness-install managed provider' '${DEEPAGENTS_HOME:-$HOME/.deepagents}/config.toml'"
    check_output_contains "onboard (HARNESS_AGENT unset) now resolves to dcode (persisted marker updated)" \
      "dcode" env -u HARNESS_AGENT bash "$REPO_ROOT/install.sh" onboard
  else
    skip "deepagents-code install" "not in --agents list, or already installed as the primary agent"
  fi

  if agent_in_list hermes && [[ "$SMOKE_PRIMARY_AGENT" != "hermes" ]]; then
    check "full install: --harness hermes (pinned verified installer)" \
      env NON_INTERACTIVE=1 \
      bash "$REPO_ROOT/install.sh" --harness hermes --non-interactive --skip-gpu-check
    export PATH="$HOME/.local/bin:$PATH"
    check "hermes CLI resolves on PATH after install" bash -c 'command -v hermes'
    check_output_contains "installed-agent marker == hermes" "hermes" cat "$HOME/.agent-harness-install/installed-agent"
    check_output_contains "onboard (HARNESS_AGENT unset) now resolves to hermes (persisted marker updated)" \
      "Hermes" env -u HARNESS_AGENT bash "$REPO_ROOT/install.sh" onboard
  else
    skip "hermes install" "not in --agents list, or already installed as the primary agent"
  fi
}

phase_10_mcp() {
  phase_banner "10-mcp: MCP endpoint registration"
  if agent_in_list hermes && command -v hermes >/dev/null 2>&1; then
    check "mcp register (hermes)" bash "$REPO_ROOT/install.sh" mcp register smoke-test-mcp https://example.invalid/mcp hermes
    check_output_contains "hermes config.yaml carries the registered route" "smoke-test-mcp" \
      cat "${HERMES_CONFIG:-$HOME/.hermes/config.yaml}"
    check "hermes config.yaml is mode 0600" bash -c "[[ \$(stat -c '%a' '${HERMES_CONFIG:-$HOME/.hermes/config.yaml}') == 600 ]]"
  else
    skip "mcp register (hermes)" "hermes not installed in this run"
  fi

  if agent_in_list openclaw && command -v openclaw >/dev/null 2>&1; then
    check "mcp register (openclaw)" bash "$REPO_ROOT/install.sh" mcp register smoke-test-mcp https://example.invalid/mcp openclaw
  else
    skip "mcp register (openclaw)" "openclaw not installed in this run"
  fi

  check_output_contains "mcp register for an unimplemented agent warns instead of crashing" "isn't implemented" \
    bash "$REPO_ROOT/install.sh" mcp register smoke-test-mcp https://example.invalid/mcp some-other-agent
}

phase_11_skills() {
  phase_banner "11-skills: Hermes skill management"
  if ! agent_in_list hermes; then
    skip "hermes skills" "hermes not in --agents list"
    return
  fi
  local skill_dir; skill_dir="$(mktemp -d)/smoke-skill"
  mkdir -p "$skill_dir"
  printf '# Smoke Test Skill\n' >"$skill_dir/SKILL.md"

  check "skill install" bash "$REPO_ROOT/install.sh" skill install "$skill_dir"
  check_output_contains "skill list shows the installed skill" "smoke-skill" bash "$REPO_ROOT/install.sh" skill list
  check "skill remove" bash "$REPO_ROOT/install.sh" skill remove smoke-skill
  local out; out="$(bash "$REPO_ROOT/install.sh" skill list 2>&1)"
  if ! grep -qF "smoke-skill" <<<"$out"; then pass "skill list no longer shows the removed skill"; else fail "skill list no longer shows the removed skill" "$out"; fi

  check_fail "skill install rejects path traversal in the derived name" \
    bash -c "mkdir -p /tmp/smoke-skill-parent/.. 2>/dev/null; bash '$REPO_ROOT/install.sh' skill install /tmp/.."
}

phase_12_inference() {
  phase_banner "12-inference: OVMS exporter image resolution + model export + external endpoint via the Router"

  # Fast, always-on regression test for the stale "-py" tag bug: confirms
  # the registry actually has the export image the default docker-pull
  # exporter would use (HARNESS_OVMS_EXPORT_IMAGE) via the manifest API
  # only (no image layers downloaded) -- catches an unpublished tag without
  # waiting for a full slow model conversion.
  local ovms_image pull_image
  ovms_image="$(lib_eval 'printf "%s" "$HARNESS_OVMS_IMAGE"')"
  pull_image="$(lib_eval 'printf "%s" "$HARNESS_OVMS_EXPORT_IMAGE"')"
  check_with_retry "OVMS serving image tag resolves on the registry (${ovms_image})" 3 \
    docker buildx imagetools inspect "$ovms_image"
  check_with_retry "OVMS docker-pull exporter's derived image tag resolves on the registry (${pull_image})" 3 \
    docker buildx imagetools inspect "$pull_image"

  if [[ -n "$SMOKE_HF_MODEL" ]]; then
    check "install --model exports and registers a real model (slow)" \
      env NON_INTERACTIVE=1 bash "$REPO_ROOT/install.sh" --harness "$SMOKE_PRIMARY_AGENT" --non-interactive --skip-gpu-check --model "$SMOKE_HF_MODEL"
    local model_name="${SMOKE_HF_MODEL##*/}"
    check_output_contains "models list shows the exported model" "$model_name" bash "$REPO_ROOT/install.sh" models list
    check_output_contains "OVMS readiness endpoint responds for the exported model" "" \
      curl -sf "http://127.0.0.1:8000/v2/models/${model_name}/ready"
    check "models remove cleans it up" bash "$REPO_ROOT/install.sh" models remove "$model_name"

    # --model-hub alone selects the Model Download exporter (no
    # HARNESS_OVMS_EXPORTER needed), and downloads OVMS can't serve (no
    # graph.pbtxt) are tracked instead of registered -- see
    # export_model_via_model_download/list_exported_models/
    # remove_exported_model in scripts/lib/openvino.sh.
    local hub_model="hf-internal-testing/tiny-random-gpt2" hub_model_name="tiny-random-gpt2"
    check "install --model-hub huggingface (raw download, no OVMS registration)" \
      env NON_INTERACTIVE=1 \
      bash "$REPO_ROOT/install.sh" --harness "$SMOKE_PRIMARY_AGENT" --non-interactive --skip-gpu-check \
        --model "$hub_model" --model-hub huggingface
    check_output_contains "models list shows the hub download, labeled not served by OVMS" \
      "not served by OVMS" bash "$REPO_ROOT/install.sh" models list
    check_output_contains "models list labels it with its hub" \
      "hub: huggingface" bash "$REPO_ROOT/install.sh" models list
    check "models remove also cleans up an untracked (non-config.json) hub download" \
      bash "$REPO_ROOT/install.sh" models remove "$hub_model_name"

    # A non-LLM-servable hub: Ollama is downloaded and tracked, not served,
    # and the install still succeeds with the Router on what OVMS serves.
    check "install --model-hub ollama (downloaded and tracked, not served by OVMS)" \
      env NON_INTERACTIVE=1 \
      bash "$REPO_ROOT/install.sh" --harness "$SMOKE_PRIMARY_AGENT" --non-interactive --skip-gpu-check \
        --model-hub ollama --model smollm:135m
    check_output_contains "models list shows the Ollama download with its hub, labeled not served" \
      "hub: ollama" bash "$REPO_ROOT/install.sh" models list
    check "models remove cleans up the Ollama download" \
      bash "$REPO_ROOT/install.sh" models remove smollm-135m
  else
    skip "real HF model export + chat-completion test" "pass --hf-model <id> to enable (slow, downloads a model)"
  fi

  check "external endpoint: OVMS is skipped, the Router is started in front of it, status reports 'routed externally'" \
    bash -c "cd '$REPO_ROOT' && HARNESS_LLM_ROUTER_ENDPOINT=http://127.0.0.1:1/fake NON_INTERACTIVE=1 bash install.sh --harness ${SMOKE_PRIMARY_AGENT} --non-interactive --skip-gpu-check --model fake-model >/tmp/smoke-router.log 2>&1 && HARNESS_LLM_ROUTER_ENDPOINT=http://127.0.0.1:1/fake bash install.sh status | grep -q 'routed externally'"
  check_output_contains "external endpoint: the Router's provider points at it" 'name: "external"' \
    lib_eval 'cat "$(inference_router_workspace_dir)/config.yaml"'
  check_output_contains "ovms-managed marker flips to 0 when routed externally" "0" cat "$HOME/.agent-harness-install/ovms-managed"

  # Restore local-OVMS management for the uninstall phase below.
  lib_eval 'record_ovms_managed 1' >/dev/null 2>&1 || true
}

phase_13_uninstall() {
  phase_banner "13-uninstall: per-agent removal + final cleanup"
  if [[ "$SMOKE_CLEANUP" != "1" ]]; then
    skip "uninstall / cleanup" "--no-cleanup was passed"
    return
  fi

  local agent
  for agent in $SMOKE_AGENTS; do
    check "uninstall --harness $agent --yes" bash "$REPO_ROOT/uninstall.sh" --yes --harness "$agent"
  done

  if agent_in_list openclaw; then
    check_fail "openclaw npm package actually removed" bash -c 'npm ls -g openclaw 2>&1 | grep -q openclaw'
  fi
  if agent_in_list deepagents-code; then
    check_fail "dcode binary no longer resolves" bash -c 'command -v dcode'
  fi
  if agent_in_list hermes; then
    check_fail "hermes binary no longer resolves" bash -c 'command -v hermes'
  fi

  check "state directory is gone (or contains only a kept models dir)" \
    bash -c '[[ ! -d "$HOME/.agent-harness-install" ]] || [[ -z "$(ls -A "$HOME/.agent-harness-install" 2>/dev/null | grep -v "^models$")" ]]'
}

phase_99_summary() {
  printf '\n%s%s=== Summary ===%s\n' "$c_bold" "$c_cyan" "$c_reset"
  printf '  %sPASS%s: %d   %sFAIL%s: %d   %sSKIP%s: %d\n' \
    "$c_green" "$c_reset" "$PASS_COUNT" "$c_red" "$c_reset" "$FAIL_COUNT" "$c_yellow" "$c_reset" "$SKIP_COUNT"
  if [[ "$FAIL_COUNT" -gt 0 ]]; then
    printf '\n  Failed checks:\n'
    local f
    for f in "${FAILED_CHECKS[@]}"; do printf '    - %s\n' "$f"; done
  fi
  if [[ -n "${_SMOKE_TEST_LOG_FILE:-}" ]]; then
    printf '\n  Full log: %s\n' "$_SMOKE_TEST_LOG_FILE"
  fi
}

# ----------------------------------------------------------------- driver --
declare -A PHASE_FN=(
  [00-prereqs]=phase_00_prereqs
  [01-static]=phase_01_static
  [02-selfcheck]=phase_02_selfcheck
  [03-libunit]=phase_03_libunit
  [04-bootstrap]=phase_04_bootstrap
  [05-install-primary]=phase_05_install_primary
  [06-status]=phase_06_status
  [07-optparsing]=phase_07_optparsing
  [08-agent-resolution]=phase_08_agent_resolution
  [09-other-agents]=phase_09_other_agents
  [10-mcp]=phase_10_mcp
  [11-skills]=phase_11_skills
  [12-inference]=phase_12_inference
  [13-uninstall]=phase_13_uninstall
)
PHASE_ORDER=(00-prereqs 01-static 02-selfcheck 03-libunit 04-bootstrap 05-install-primary \
  06-status 07-optparsing 08-agent-resolution 09-other-agents 10-mcp 11-skills \
  12-inference 13-uninstall)

if [[ "$LIST_ONLY" == "1" ]]; then
  printf '%s\n' "${PHASE_ORDER[@]}"
  exit 0
fi

should_run() {
  local id="$1"
  if [[ -n "$ONLY_IDS" ]]; then
    [[ ",${ONLY_IDS}," == *",${id},"* ]] || return 1
  fi
  if [[ -n "$SKIP_IDS" ]]; then
    [[ ",${SKIP_IDS}," == *",${id},"* ]] && return 1
  fi
  return 0
}

for id in "${PHASE_ORDER[@]}"; do
  if should_run "$id"; then
    "${PHASE_FN[$id]}"
  fi
done
phase_99_summary

[[ "$FAIL_COUNT" -eq 0 ]]
