#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
#
# Intel Agentic Harness -- end-to-end smoke test suite.
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
#   --hf-model <id>         Also export+serve a real Hugging Face model via
#                           OVMS and smoke-test chat completions (slow,
#                           downloads several hundred MB-GB; default: skipped)
#   --sandbox-image <ref>   Image for sandbox tests (default: nginx:alpine)
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
#   SMOKE_AGENTS, SMOKE_HF_MODEL, SMOKE_SANDBOX_IMAGE, SMOKE_CLEANUP (0/1),
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
SMOKE_HF_MODEL="${SMOKE_HF_MODEL:-}"
SMOKE_SANDBOX_IMAGE="${SMOKE_SANDBOX_IMAGE:-docker.io/library/nginx:alpine}"
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
    --sandbox-image) SMOKE_SANDBOX_IMAGE="${2:?--sandbox-image requires a value}"; shift ;;
    --allow-clone-test) SMOKE_TEST_BOOTSTRAP_CLONE=1 ;;
    --no-cleanup) SMOKE_CLEANUP=0 ;;
    # Already fully handled by the re-exec-through-tee wrapper above; just
    # consumed here (not an "Unknown option" error) when this is the inner,
    # already-wrapped invocation re-parsing the same original arguments.
    --log-file) shift ;;
    --no-log) ;;
    -h | --help) sed -n '/^# Intel Agentic Harness/,/^# Exit code:/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

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

# smoke_port_free PORT -- mirrors scripts/lib/sandbox.sh's own
# port_is_available() logic. Only phase_12 (direct-port mode) actually binds
# a host port, so only it needs this; gateway mode never publishes a host
# port at all. nginx:alpine (the default lifecycle-test image) is a fixed
# port-80 listener the installer's sandbox CLI has no way to remap (it
# always sets host_port=container_port=HARNESS_DEFAULT_SANDBOX_PORT, which
# the harness itself requires to be >= 1024) -- so a separate, dedicated
# hashicorp/http-echo sandbox (default port 5678, listen text supplied via
# its ECHO_TEXT env var, which the CLI's [env-pairs] argument already
# supports) is used for actual HTTP-reachability checks instead.
smoke_port_free() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ! ss -H -t -l -n "sport = :${port}" 2>/dev/null | grep -q .
  elif command -v lsof >/dev/null 2>&1; then
    ! lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t >/dev/null 2>&1
  else
    return 0
  fi
}

# ------------------------------------------------- isolated lib unit-test --
# Sources every scripts/lib/*.sh file (same order as scripts/install.sh) in
# a disposable bash -c subshell, then evaluates $1. Isolated because several
# lib functions call error() -> exit 1 on failure; running them in a nested
# subshell means that exit only ends the subshell, never this test runner.
LIB_ORDER="colors verify state sudo shim gpu-intel docker-setup nodejs gateway sandbox express openvino agents harness-mcp"
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
  for tool in curl git sudo sha256sum; do
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
  if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import yaml' >/dev/null 2>&1; then
    note "python3/PyYAML needed for Hermes MCP registration; attempting install"
    sudo apt-get update -qq >/dev/null 2>&1 || true
    sudo apt-get install -y -qq python3 python3-pip >/dev/null 2>&1 || true
    pip3 install --user --quiet pyyaml >/dev/null 2>&1 || true
  fi
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
  check "gateway.sh pins an immutable image digest (not just a floating tag)" \
    bash -c "grep -q 'HARNESS_GATEWAY_IMAGE=.*@sha256:' '$REPO_ROOT/scripts/lib/gateway.sh'"
  check "openvino.sh defines ovms_is_managed (OVMS-managed-state fix)" \
    bash -c "grep -q 'ovms_is_managed()' '$REPO_ROOT/scripts/lib/openvino.sh'"
  check "install.sh validates --agent/--hf-model have a value before use" \
    bash -c "grep -q -- '--agent requires a value' '$REPO_ROOT/scripts/install.sh'"
  check_fail "openvino.sh no longer pins the stale HARNESS_OVMS_IMAGE with no matching -py tag" \
    bash -c "grep -q '2026\\.4\\.0-gpu' '$REPO_ROOT/scripts/lib/openvino.sh'"
  # Regression guard for the fix's own consistency invariant: openvino.sh's
  # comments document that HARNESS_OVMS_EXPORT_MODEL_REF (the export-model-py
  # fallback exporter's pin) must track HARNESS_OVMS_IMAGE's version --
  # catches a future version bump to one without updating the other.
  check "HARNESS_OVMS_EXPORT_MODEL_REF stays in sync with HARNESS_OVMS_IMAGE's pinned version" \
    lib_eval '
      [[ "$HARNESS_OVMS_EXPORT_MODEL_REF" == "$_OVMS_EXPORT_MODEL_PINNED_REF" ]] || exit 1
      image_version="${HARNESS_OVMS_IMAGE#*:}"; image_version="${image_version%-gpu}"
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
  # gets persisted into the agent's own config file.
  check "harness_llm_endpoint propagates resolve_advertised_host failures (not embedded in printf)" \
    bash -c "awk '/^harness_llm_endpoint\\(\\)/,/^\\}/' '$REPO_ROOT/scripts/lib/openvino.sh' | grep -q 'host=\"\$(resolve_advertised_host)\" || return 1'"
  # wait_for_ovms_model_ready returns 1 on a plain readiness-poll timeout
  # (its own warn() is the complete, non-fatal signal) -- a bare call with
  # no `|| true` was silently killing the *entire* installer under set -e
  # partway through step 2, with no [ERROR] at all, whenever a model took
  # longer than 60s to report ready.
  check "ensure_inference_backend tolerates a wait_for_ovms_model_ready timeout" \
    bash -c "grep -q 'wait_for_ovms_model_ready \"\${HARNESS_HF_MODEL##\\*/}\" || true' '$REPO_ROOT/scripts/lib/openvino.sh'"
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
  # "./install.sh onboard" run (no --hf-model/HARNESS_LLM_MODEL) against an
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
  check "create_sandbox passes --group-add alongside --device" \
    bash -c "awk '/^create_sandbox\\(\\)/,/^}/' '$REPO_ROOT/scripts/lib/sandbox.sh' | grep -q 'group_add_args=\"\$(intel_gpu_docker_group_add_args)\"'"
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

  check "validate_sandbox_name: accepts my-app" lib_eval 'validate_sandbox_name my-app'
  check_fail "validate_sandbox_name: rejects My_App (uppercase/underscore)" lib_eval 'validate_sandbox_name My_App'
  check_fail "validate_sandbox_name: rejects consecutive hyphens" lib_eval 'validate_sandbox_name ab--cd'
  check_fail "validate_sandbox_name: rejects leading digit" lib_eval 'validate_sandbox_name 1abc'

  check "validate_image_reference: accepts nginx:alpine" lib_eval 'validate_image_reference nginx:alpine'
  check "validate_image_reference: accepts a digest-pinned reference" \
    lib_eval 'validate_image_reference "alpine@sha256:0000000000000000000000000000000000000000000000000000000000000000"'
  check_fail "validate_image_reference: rejects a reference containing spaces" \
    lib_eval 'validate_image_reference "bad image ref"'

  check "validate_model_name: accepts qwen2.5-7b" lib_eval 'validate_model_name qwen2.5-7b'
  check_fail "validate_model_name: rejects a dot-prefixed name" lib_eval 'validate_model_name .hidden'
  check_fail "validate_model_name: rejects path traversal" lib_eval 'validate_model_name ../etc'

  check "validate_skill_name: accepts my-skill" lib_eval 'validate_skill_name my-skill'
  check_fail "validate_skill_name: rejects .." lib_eval 'validate_skill_name ..'
  check_fail "validate_skill_name: rejects a path separator" lib_eval 'validate_skill_name a/b'

  check_output_contains "detect_intel_harness_profile: cpu-only on this declared no-GPU host" \
    "cpu-only" lib_eval 'detect_intel_harness_profile'

  check_output_contains "resolve_installed_agent: defaults to openclaw with no marker/env" \
    "openclaw" lib_eval 'export HOME=$(mktemp -d); unset HARNESS_AGENT; resolve_installed_agent'
  check_output_contains "resolve_installed_agent: HARNESS_AGENT wins over a persisted marker" \
    "hermes" lib_eval '
      export HOME=$(mktemp -d)
      mkdir -p "$HOME/.intel-agent"; printf openclaw > "$HOME/.intel-agent/installed-agent"
      export HARNESS_AGENT=hermes
      resolve_installed_agent'
  check_output_contains "resolve_installed_agent: falls back to the persisted marker, not a hardcoded default (regression)" \
    "hermes" lib_eval '
      export HOME=$(mktemp -d)
      mkdir -p "$HOME/.intel-agent"; printf hermes > "$HOME/.intel-agent/installed-agent"
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
      check_output_contains "standalone fetch clones a real pinned ref and delegates" "Intel Agentic Harness" \
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
  phase_banner "05-install: first agent (openclaw), CPU-only, no model export"
  check "./install.sh status is read-only and does not crash before anything is installed" \
    env NON_INTERACTIVE=1 bash "$REPO_ROOT/install.sh" status

  check "full install: --agent openclaw --non-interactive --skip-gpu-check" \
    env NON_INTERACTIVE=1 bash "$REPO_ROOT/install.sh" --agent openclaw --non-interactive --skip-gpu-check

  # Mirrors the installer's own "open a new terminal" guidance so later
  # phases (separate processes) can resolve node/openclaw/dcode/hermes the
  # same way a real user's next shell would.
  export NVM_DIR="$HOME/.nvm"
  # shellcheck disable=SC1091
  [[ -s "$NVM_DIR/nvm.sh" ]] && . "$NVM_DIR/nvm.sh"
  export PATH="$HOME/.local/bin:$PATH"

  check "docker info succeeds after install" docker info
  check "node --version resolves after install" bash -c 'command -v node'
  check "openclaw CLI resolves on PATH after install" bash -c 'command -v openclaw'
  check_output_contains "installed-agent marker == openclaw" "openclaw" cat "$HOME/.intel-agent/installed-agent"
  check_output_contains "ovms-managed marker == 1 (no external router configured)" "1" cat "$HOME/.intel-agent/ovms-managed"
  check_output_contains "OpenClaw's 'ovms' provider was registered (onboarding fix)" "ovms" \
    bash -c "openclaw config get models.providers --json | grep -o ovms"
}

phase_06_status() {
  phase_banner "06-status: combined health view"
  check "./install.sh status succeeds post-install" bash "$REPO_ROOT/install.sh" status
  check_output_contains "status mentions OpenClaw as installed" "OpenClaw" bash "$REPO_ROOT/install.sh" status
}

phase_07_optparsing() {
  phase_banner "07-optparsing: unbound-variable regression checks"
  check_fail_output_contains "install.sh --agent with no value errors (not 'unbound variable')" "requires a value" \
    bash "$REPO_ROOT/install.sh" --agent
  check_fail_output_contains "install.sh --hf-model with no value errors (not 'unbound variable')" "requires a value" \
    bash "$REPO_ROOT/install.sh" --hf-model
  check_fail_output_contains "uninstall.sh --agent with no value errors (not 'unbound variable')" "requires a value" \
    bash "$REPO_ROOT/uninstall.sh" --agent
}

phase_08_agent_resolution() {
  phase_banner "08-agent-resolution: stale-default + silent-no-op regression checks (live)"
  local marker="$HOME/.intel-agent/installed-agent"
  local saved; saved="$(cat "$marker" 2>/dev/null || true)"

  check_output_contains "onboard (HARNESS_AGENT unset) operates on the persisted agent, not a hardcoded default" \
    "OpenClaw" env -u HARNESS_AGENT bash "$REPO_ROOT/install.sh" onboard

  printf 'totally-bogus' >"$marker"
  check_fail_output_contains "onboard errors loudly on an unrecognized persisted agent (regression: was a silent no-op)" \
    "Unknown agent" env -u HARNESS_AGENT bash "$REPO_ROOT/install.sh" onboard
  check "status degrades gracefully (does not crash) on the same unrecognized marker" \
    bash "$REPO_ROOT/install.sh" status

  printf '%s' "$saved" >"$marker"
}

phase_09_other_agents() {
  phase_banner "09-install: remaining agents"
  if agent_in_list deepagents-code; then
    check "full install: --agent deepagents-code (dcode, unverified installer accepted for this test)" \
      env NON_INTERACTIVE=1 HARNESS_ALLOW_UNVERIFIED_DCODE_INSTALL=1 \
      bash "$REPO_ROOT/install.sh" --agent deepagents-code --non-interactive --skip-gpu-check
    export PATH="$HOME/.local/bin:$PATH"
    check "dcode CLI resolves on PATH after install" bash -c 'command -v dcode'
    check_output_contains "installed-agent marker == deepagents-code" "deepagents-code" cat "$HOME/.intel-agent/installed-agent"
    check "dcode's config.toml carries the managed-provider markers (onboarding wiring)" \
      bash -c "grep -q 'BEGIN intel-agent-harness managed provider' '${DEEPAGENTS_HOME:-$HOME/.deepagents}/config.toml'"
    check_output_contains "onboard (HARNESS_AGENT unset) now resolves to dcode (persisted marker updated)" \
      "dcode" env -u HARNESS_AGENT bash "$REPO_ROOT/install.sh" onboard
  else
    skip "deepagents-code install" "not in --agents list"
  fi

  if agent_in_list hermes; then
    check "full install: --agent hermes (unverified installer accepted for this test)" \
      env NON_INTERACTIVE=1 HERMES_ALLOW_UNVERIFIED_INSTALL=1 \
      bash "$REPO_ROOT/install.sh" --agent hermes --non-interactive --skip-gpu-check
    export PATH="$HOME/.local/bin:$PATH"
    check "hermes CLI resolves on PATH after install" bash -c 'command -v hermes'
    check_output_contains "installed-agent marker == hermes" "hermes" cat "$HOME/.intel-agent/installed-agent"
    check_output_contains "onboard (HARNESS_AGENT unset) now resolves to hermes (persisted marker updated)" \
      "Hermes" env -u HARNESS_AGENT bash "$REPO_ROOT/install.sh" onboard
  else
    skip "hermes install" "not in --agents list"
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

phase_12_sandbox() {
  phase_banner "12-sandbox: Docker-based sandbox manager (direct port mode)"
  local name=smoke-nginx container=iplat-smoke-nginx

  check "sandbox create" bash "$REPO_ROOT/install.sh" sandbox create "$name" "$SMOKE_SANDBOX_IMAGE"
  check "container is running" bash -c "docker inspect -f '{{.State.Running}}' $container | grep -q true"
  check_output_contains "sandbox list shows it as running" "status=running" bash "$REPO_ROOT/install.sh" sandbox list
  check_fail "creating a duplicate-named sandbox is rejected" bash "$REPO_ROOT/install.sh" sandbox create "$name" "$SMOKE_SANDBOX_IMAGE"
  check_fail "creating a sandbox with an invalid name is rejected" bash "$REPO_ROOT/install.sh" sandbox create "Bad_Name" "$SMOKE_SANDBOX_IMAGE"
  check_fail "creating a sandbox with an invalid image reference is rejected" bash "$REPO_ROOT/install.sh" sandbox create smoke-bad "bad image ref"
  check "container responds to a shell probe (what 'connect' itself checks)" \
    bash -c "docker exec $container sh -c 'exit 0'"

  check "sandbox stop" bash "$REPO_ROOT/install.sh" sandbox stop "$name"
  check_output_contains "sandbox list reflects stopped status (not stale 'running')" "status=stopped" bash "$REPO_ROOT/install.sh" sandbox list
  check "sandbox start" bash "$REPO_ROOT/install.sh" sandbox start "$name"
  check_output_contains "sandbox list reflects running status again" "status=running" bash "$REPO_ROOT/install.sh" sandbox list

  local backup_count_before backup_count_after
  backup_count_before="$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -c "^${container}:backup-" || true)"
  check "sandbox backup" bash "$REPO_ROOT/install.sh" sandbox backup "$name"
  backup_count_after="$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -c "^${container}:backup-" || true)"
  if [[ "$backup_count_after" -gt "$backup_count_before" ]]; then pass "a new backup image was created"; else fail "a new backup image was created" "before=$backup_count_before after=$backup_count_after"; fi

  docker rm -f "$container" >/dev/null 2>&1
  check "sandbox recover rebuilds a lost container from its backup image" bash "$REPO_ROOT/install.sh" sandbox recover "$name"
  check "recovered container is running" bash -c "docker inspect -f '{{.State.Running}}' $container | grep -q true"

  check "sandbox destroy --force" bash "$REPO_ROOT/install.sh" sandbox destroy "$name" --force
  check_fail "destroyed container no longer exists" bash -c "docker inspect $container"
  local out; out="$(bash "$REPO_ROOT/install.sh" sandbox list 2>&1)"
  if ! grep -qF "$name" <<<"$out"; then pass "sandbox list no longer shows the destroyed sandbox"; else fail "sandbox list no longer shows the destroyed sandbox" "$out"; fi

  # Separate, dedicated sandbox for actual HTTP-reachability: the sandbox
  # CLI has no port_spec passthrough, forcing host_port=container_port=
  # HARNESS_DEFAULT_SANDBOX_PORT (which must be >= 1024, so a fixed
  # port-80 listener like nginx can never be matched). hashicorp/http-echo
  # defaults to port 5678 and takes its response text from an ECHO_TEXT env
  # var, which the CLI's [env-pairs] argument already supports -- a
  # combination that actually works within the existing CLI surface.
  local echo_name=smoke-echo echo_container=iplat-smoke-echo
  if smoke_port_free 5678; then
    check "sandbox create (http-echo, for HTTP-reachability testing)" \
      env HARNESS_DEFAULT_SANDBOX_PORT=5678 \
      bash "$REPO_ROOT/install.sh" sandbox create "$echo_name" hashicorp/http-echo "ECHO_TEXT=smoke-test-ok"
    sleep 1
    check_output_contains "sandbox is reachable on its published host port" "smoke-test-ok" \
      curl -sf "http://127.0.0.1:5678/"
    check "cleanup: destroy http-echo sandbox" bash "$REPO_ROOT/install.sh" sandbox destroy "$echo_name" --force
  else
    skip "sandbox HTTP reachability (direct port mode)" "host port 5678 already in use"
  fi
}

phase_13_gateway() {
  phase_banner "13-gateway: shared reverse-proxy mode"
  # Uses hashicorp/http-echo (see phase_12's comment) rather than the
  # general-purpose $SMOKE_SANDBOX_IMAGE: this phase's whole point is
  # validating the gateway actually proxies real HTTP traffic end-to-end,
  # which needs an image whose internal port (>= 1024, since gateway mode
  # bottoms out at the same HARNESS_DEFAULT_SANDBOX_PORT requirement) is
  # both known and reachable through the CLI's existing [env-pairs] support.
  local name=smoke-gw container=iplat-smoke-gw

  check "sandbox create (gateway mode)" \
    env HARNESS_GATEWAY_ENABLED=1 HARNESS_DEFAULT_SANDBOX_PORT=5678 \
    bash "$REPO_ROOT/install.sh" sandbox create "$name" hashicorp/http-echo "ECHO_TEXT=smoke-gateway-ok"
  check "gateway container is running" bash -c "docker inspect -f '{{.State.Running}}' intel-agent-gateway | grep -q true"
  check "sandbox has no published host port (only reachable via the gateway)" \
    bash -c "[[ -z \"\$(docker port $container 2>/dev/null)\" ]]"
  check_output_contains "sandbox list shows the gateway route for it" "gateway->" env HARNESS_GATEWAY_ENABLED=1 bash "$REPO_ROOT/install.sh" sandbox list

  local gw_port; gw_port="$(cat "$HOME/.intel-agent/gateway/port" 2>/dev/null || echo 8888)"
  sleep 1
  check_output_contains "gateway proxies to the sandbox (real response content reachable through it)" "smoke-gateway-ok" \
    curl -sf "http://127.0.0.1:${gw_port}/${name}/"

  check "sandbox destroy removes its gateway route too" env HARNESS_GATEWAY_ENABLED=1 bash "$REPO_ROOT/install.sh" sandbox destroy "$name" --force
}

phase_14_inference() {
  phase_banner "14-inference: OVMS exporter image resolution + model export + external-router bypass"

  # Fast, always-on regression test for the stale "-py" tag bug: derives the
  # exact pull_image the default docker-pull exporter would use (same -gpu
  # -> -py swap as export_model_via_docker_pull in scripts/lib/openvino.sh),
  # then confirms the registry actually has that tag via the manifest API
  # only (no image layers downloaded) -- catches the exact failure mode
  # from the 2026.4.0 pin without waiting for a full slow model conversion.
  local ovms_image pull_image
  ovms_image="$(lib_eval 'printf "%s" "$HARNESS_OVMS_IMAGE"')"
  case "$ovms_image" in
    *-gpu) pull_image="${ovms_image%-gpu}-py" ;;
    *) pull_image="${ovms_image}-py" ;;
  esac
  check "OVMS serving image tag resolves on the registry (${ovms_image})" \
    docker buildx imagetools inspect "$ovms_image"
  check "OVMS docker-pull exporter's derived image tag resolves on the registry (${pull_image})" \
    docker buildx imagetools inspect "$pull_image"

  if [[ -n "$SMOKE_HF_MODEL" ]]; then
    check "install --hf-model exports and registers a real model (slow)" \
      env NON_INTERACTIVE=1 bash "$REPO_ROOT/install.sh" --agent openclaw --non-interactive --skip-gpu-check --hf-model "$SMOKE_HF_MODEL"
    local model_name="${SMOKE_HF_MODEL##*/}"
    check_output_contains "models list shows the exported model" "$model_name" bash "$REPO_ROOT/install.sh" models list
    check_output_contains "OVMS readiness endpoint responds for the exported model" "" \
      curl -sf "http://127.0.0.1:8000/v2/models/${model_name}/ready"
    check "models remove cleans it up" bash "$REPO_ROOT/install.sh" models remove "$model_name"
  else
    skip "real HF model export + chat-completion test" "pass --hf-model <id> to enable (slow, downloads a model)"
  fi

  check "external router bypass: OVMS is skipped, status reports 'Routed externally'" \
    bash -c "cd '$REPO_ROOT' && HARNESS_LLM_ROUTER_ENDPOINT=http://127.0.0.1:1/fake NON_INTERACTIVE=1 bash install.sh --agent openclaw --non-interactive --skip-gpu-check >/tmp/smoke-router.log 2>&1; HARNESS_LLM_ROUTER_ENDPOINT=http://127.0.0.1:1/fake bash install.sh status | grep -q 'Routed externally'"
  check_output_contains "ovms-managed marker flips to 0 when routed externally" "0" cat "$HOME/.intel-agent/ovms-managed"

  # Restore local-OVMS management for the uninstall phase below.
  env NON_INTERACTIVE=1 bash "$REPO_ROOT/install.sh" --agent openclaw --non-interactive --skip-gpu-check >/dev/null 2>&1 || true
}

phase_15_uninstall() {
  phase_banner "15-uninstall: per-agent removal + final cleanup"
  if [[ "$SMOKE_CLEANUP" != "1" ]]; then
    skip "uninstall / cleanup" "--no-cleanup was passed"
    return
  fi

  local agent
  for agent in $SMOKE_AGENTS; do
    check "uninstall --agent $agent --yes" bash "$REPO_ROOT/uninstall.sh" --yes --agent "$agent"
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
    bash -c '[[ ! -d "$HOME/.intel-agent" ]] || [[ -z "$(ls -A "$HOME/.intel-agent" 2>/dev/null | grep -v "^models$")" ]]'
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
  [12-sandbox]=phase_12_sandbox
  [13-gateway]=phase_13_gateway
  [14-inference]=phase_14_inference
  [15-uninstall]=phase_15_uninstall
)
PHASE_ORDER=(00-prereqs 01-static 02-selfcheck 03-libunit 04-bootstrap 05-install-primary \
  06-status 07-optparsing 08-agent-resolution 09-other-agents 10-mcp 11-skills \
  12-sandbox 13-gateway 14-inference 15-uninstall)

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
