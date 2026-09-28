# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# Onboarding flow — session resume classification via an onboard-session.json
# state machine (resume / fresh-recover / failed / complete / corrupt),
# wired to the Docker-based sandbox manager.

onboard_session_file() {
  local state_dir
  state_dir="$(ensure_state_dir)"
  printf '%s/onboard-session.json' "$state_dir"
}

save_onboard_session() {
  local status="$1" sandbox="$2" file entry
  file="$(onboard_session_file)"
  entry="$(node -e '
    process.stdout.write(JSON.stringify({
      status: process.argv[1], sandboxName: process.argv[2],
      updatedAt: new Date().toISOString(),
    }, null, 2));
  ' "$status" "$sandbox")"
  atomic_write_file "$file" "$entry"
}

# Prints one of: complete | fresh-recover | failed | corrupt | skip
classify_onboard_session() {
  local file status
  file="$(onboard_session_file)"
  [[ -f "$file" ]] || { printf 'skip'; return; }
  status="$(read_json_field "$file" status)"
  case "$status" in
    complete) printf 'complete' ;;
    in_progress) printf 'fresh-recover' ;;
    failed) printf 'failed' ;;
    *) printf 'corrupt' ;;
  esac
}

# run_onboard [--fresh] [--resume] — creates (or resumes) the default sandbox
# from PLATFORM_SANDBOX_IMAGE.
run_onboard() {
  local fresh="" resume="" arg
  for arg in "$@"; do
    case "$arg" in
      --fresh) fresh=1 ;;
      --resume) resume=1 ;;
    esac
  done

  require_third_party_notice_acceptance

  local sandbox_name="${PLATFORM_SANDBOX_NAME:-my-project}"
  local image="${PLATFORM_SANDBOX_IMAGE:-}"
  [[ -n "$image" ]] || error "Set PLATFORM_SANDBOX_IMAGE to the Docker image onboarding
should run (your project's built image). Onboarding did not run."

  local session_state
  session_state="$(classify_onboard_session)"

  if [[ -n "$fresh" ]]; then
    info "Starting a fresh onboarding session (--fresh)."
    destroy_sandbox "$sandbox_name" --force 2>/dev/null || true
  elif [[ "$session_state" == "complete" && -z "$resume" ]]; then
    info "Onboarding already completed for '${sandbox_name}'; recovering it."
    recover_sandbox "$sandbox_name" || true
    save_onboard_session complete "$sandbox_name"
    ensure_cli_shim "${PROJECT_CLI_BIN:-myagent}" || true
    return 0
  elif [[ "$session_state" == "failed" && -z "$resume" ]]; then
    if [[ "${NON_INTERACTIVE:-}" == "1" ]]; then
      error "Previous onboarding session for '${sandbox_name}' failed. Re-run with
--fresh to discard it, or --resume to retry."
    fi
    local answer
    printf "  Previous onboarding session failed. Resume, or start fresh? [R/f]: "
    IFS= read -r answer || answer=""
    case "$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')" in
      f | fresh) destroy_sandbox "$sandbox_name" --force 2>/dev/null || true ;;
    esac
  fi

  save_onboard_session in_progress "$sandbox_name"
  if sandbox_exists "$sandbox_name"; then
    recover_sandbox "$sandbox_name" \
      || { save_onboard_session failed "$sandbox_name"; error "Onboarding failed while recovering '${sandbox_name}'."; }
  else
    create_sandbox "$sandbox_name" "$image" \
      || { save_onboard_session failed "$sandbox_name"; error "Onboarding failed while creating '${sandbox_name}'."; }
  fi
  save_onboard_session complete "$sandbox_name"
  ensure_cli_shim "${PROJECT_CLI_BIN:-myagent}" || true
}
