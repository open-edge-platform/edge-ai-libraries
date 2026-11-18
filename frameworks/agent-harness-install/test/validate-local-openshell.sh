#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: bash test/validate-local-openshell.sh [--prepare] [--model <served-id>] [--report-dir <directory>]

Validate this checkout, including uncommitted changes. No fetch or checkout.
Default: offline tests, read-only environment checks, then live integration.
--prepare: allow normal installer prerequisite/inference/OpenShell provisioning.
           Existing inference is validated, never explicitly switched or repaired.
--model: exact already-served ID (default: Qwen3.5-9B-int8-ov).
         Fresh preparation without existing inference supports only that default.
--report-dir: new report directory (default: a temporary directory).

Requires Linux, Bash, Node.js 24, curl, GNU timeout, flock and standard utilities
before offline tests. For missing base tools run startup.sh separately.
Preparation may require sudo, downloads and substantial disk/RAM. Run reviewed
code outside demo windows. Shared services/models are retained after validation.
EOF
}

validate_local() {
  local prepare=0 model=Qwen3.5-9B-int8-ov report_dir="" containers
  while (($#)); do
    case "$1" in
      --prepare) prepare=1; shift ;;
      --model | --report-dir)
        [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || { printf 'Missing value for %s\n' "$1" >&2; return 2; }
        case "$1" in --model) model="$2" ;; --report-dir) report_dir="$2" ;; esac
        shift 2 ;;
      --help | -h) usage; return 0 ;;
      *) printf 'Unknown option: %s\n' "$1" >&2; return 2 ;;
    esac
  done
  [[ "$(uname -s)" == Linux ]] || { printf 'Linux is required.\n' >&2; return 2; }
  local tool
  for tool in node curl timeout flock tee mktemp; do
    command -v "$tool" >/dev/null || { printf 'Missing base tool: %s; run startup.sh first.\n' "$tool" >&2; return 2; }
  done
  [[ "$(node -p 'process.versions.node.split(".")[0]')" == 24 ]] \
    || { printf 'Node.js 24 is required.\n' >&2; return 2; }
  [[ -z "${HARNESS_HF_MODEL:-}" ]] \
    || { printf 'Unset HARNESS_HF_MODEL; this validator does not request model changes.\n' >&2; return 2; }
  if [[ -n "$report_dir" ]]; then
    mkdir -- "$report_dir"
    report_dir="$(cd "$report_dir" && pwd)"
  else
    report_dir="$(mktemp -d "${TMPDIR:-/tmp}/openshell-local-validation.XXXXXX")"
  fi
  printf 'Reports: %s\nCheckout: %s (working-tree files are tested)\n' "$report_dir" "$ROOT"
  cd "$ROOT"
  printf '\nStage 1: syntax and offline regression\n'
  local file
  while IFS= read -r -d '' file; do bash -n "$file"; done < <(find scripts openshell test -name '*.sh' -print0)
  bash -n install.sh
  bash -n uninstall.sh
  bash test/openshell-test.sh | tee "$report_dir/offline.tap"
  node --test --test-reporter=tap test/tap-summary-test.mjs | tee "$report_dir/reporting.tap"

  printf '\nStage 2: inspect shared environment\n'
  # Reuse installer configuration and safety checks, without invoking its main.
  . "$ROOT/scripts/install.sh"
  export HARNESS_RUNTIME=openshell HARNESS_LLM_MODEL="$model" NON_INTERACTIVE=1
  [[ "$(resolve_bind_host)" == 127.0.0.1 ]] || error "OpenShell requires loopback publication."
  [[ ! -e "$(harness_state_root)/openshell-model-pending.json" &&
     ! -L "$(harness_state_root)/openshell-model-pending.json" ]] \
    || error "A model transition is pending. Recover it explicitly before validation."
  if command -v openshell >/dev/null; then
    [[ "$(openshell --version)" == "openshell $HARNESS_OPENSHELL_VERSION" ]] \
      || error "Incompatible OpenShell version; restore the supported version explicitly."
  fi
  if ((prepare)); then
    printf '\nStage 3: opt-in prerequisite preparation\n'
    local startup_rc=0
    bash "$ROOT/startup.sh" || startup_rc=$?
    ((startup_rc == 0)) || error "Prerequisite setup failed (exit $startup_rc); fix setup and rerun validation."
  fi
  command -v docker >/dev/null || error "Docker is missing; rerun with --prepare."
  docker info >/dev/null || error "Docker is inaccessible; fix permissions/daemon (a new login may be needed) and retry."
  containers="$(docker container ls -a --format '{{.Names}}')" \
    || error "Cannot discover existing containers; refusing preparation."
  if grep -Fxq "$HARNESS_IR_CONTAINER" <<<"$containers"; then
    openshell_validate_shared_inference
  else
    ((prepare)) || error "Shared IR is missing; prepare it explicitly or rerun with --prepare."
    [[ "$model" == Qwen3.5-9B-int8-ov && -z "${HARNESS_LLM_ROUTER_ENDPOINT:-}" ]] \
      || error "Prepare custom/external inference explicitly, then rerun validation."
    # No --model: the installer's fresh-only path rejects partial deployments
    # rather than treating preparation as permission to switch or repair models.
    env -u HARNESS_LLM_MODEL bash "$ROOT/install.sh" inference --runtime openshell --non-interactive
    openshell_validate_shared_inference
  fi
  if ((prepare)); then
    with_deployment_lock ensure_openshell_cli
  else
    command -v openshell >/dev/null || error "OpenShell is missing; rerun with --prepare."
  fi
  timeout 20 openshell status -g "${HARNESS_OPENSHELL_GATEWAY:-openshell}"
  printf '\nStage 4: live integration and scoped cleanup\n'
  HARNESS_RUN_OPENSHELL_INTEGRATION=1 bash test/openshell-integration-test.sh \
    | tee "$report_dir/integration.tap"
  printf '\nStage 5: validation passed; reports retained at %s\nShared services/models retained. Review the final cleanup TAP result.\n' "$report_dir"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  validate_local "$@"
fi
