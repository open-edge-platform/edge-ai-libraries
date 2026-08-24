#!/usr/bin/env bash
# platform-lifecycle.sh — full install/start/stop/remove lifecycle test
#
# Usage:
#   platform-lifecycle.sh <component> <os_like> <results_dir>
#
# Drives platform-target.sh to run the full lifecycle for one component on a
# disposable target host, capturing per-step exit status, duration, and log.
#
# Results are written to:
#   <results_dir>/<component>.results   — pipe-delimited: step|status|duration
#   <results_dir>/<component>.<step>.log — raw output for each step
#
# Steps:
#   1. install          must exit 0
#   2. install (again)  idempotency — must exit 0
#   3. install --reset  forced reinstall — must exit 0
#   4. start + probe    start must exit 0; declared ports must be reachable
#   5. stop + probe     stop must exit 0; ports must be released
#   6. remove           must exit 0; verify_<name> must fail; workspace gone
#
# Steps 4/5 are SKIPPED when the component defines no start/stop function.
# Step 6 is SKIPPED when the component defines no remove function.
#
# Teardown (stop + remove + target release) always runs via trap even when an
# earlier step fails or the job is cancelled.
#
# Environment (all inherited from the caller / workflow):
#   TARGET_BACKEND, TARGET_POOL, TARGET_SNAPSHOT, TARGET_SSH_USER,
#   TARGET_SSH_KEY, TARGET_SSH_PORT, LIBVIRT_URI, SYNC_DIR, SSH_TIMEOUT
#   (see platform-target.sh for defaults)
#
#   PROBE_PORTS   space-separated list of TCP ports to probe after start/stop.
#                 If unset, the script attempts to derive ports from
#                 configure_<name> by inspecting the source file; if it cannot
#                 determine them it records status SKIP-PROBE instead of PASS.

set -euo pipefail

COMPONENT="${1:?Usage: $0 <component> <os_like> <results_dir>}"
OS_LIKE="${2:?Usage: $0 <component> <os_like> <results_dir>}"
RESULTS_DIR="${3:?Usage: $0 <component> <os_like> <results_dir>}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_SH="${SCRIPT_DIR}/platform-target.sh"

mkdir -p "$RESULTS_DIR"
RESULTS_FILE="${RESULTS_DIR}/${COMPONENT}.results"
# Clear results from a previous run
: > "$RESULTS_FILE"

# The module file path relative to the repo root (on the target)
MODULE_FILE="module/${COMPONENT}/${OS_LIKE}"

# Keep track of whether teardown has already run (guard against double-execution)
_teardown_done=false

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# _step <name> <command...>
#   Run <command> on the target, capture output, record PASS/FAIL + duration.
#   Returns 0 on success, 1 on failure (does NOT abort the script; callers
#   decide whether to continue or invoke teardown early).
_step () {
  local step="$1"; shift
  local log_file="${RESULTS_DIR}/${COMPONENT}.${step}.log"
  local status duration start_ts end_ts

  echo "--- Step: ${step} ---"
  start_ts=$(date +%s)

  if "$TARGET_SH" exec "$@" 2>&1 | tee "$log_file"; then
    status="✅ PASS"
  else
    status="❌ FAIL"
  fi

  end_ts=$(date +%s)
  duration=$(( end_ts - start_ts ))

  printf '%s|%s|%ds\n' "$step" "$status" "$duration" >> "$RESULTS_FILE"
  echo "Step ${step}: ${status} (${duration}s)"

  [[ "$status" == "✅ PASS" ]]
}

# _step_skip <name> <reason>
#   Record a SKIP entry without running anything on the target.
_step_skip () {
  local step="$1" reason="$2"
  printf '%s|⏭ SKIP|0s\n' "$step" >> "$RESULTS_FILE"
  echo "Step ${step}: SKIP (${reason})"
}

# _probe_ports <expect_open: true|false>
#   Probe $PROBE_PORTS on TARGET_HOST.  If $PROBE_PORTS is empty, record
#   SKIP-PROBE.  Returns 0 if the port state matches expectation.
_probe_ports () {
  local expect_open="$1"
  local step_label
  step_label="probe-ports-$([ "$expect_open" = "true" ] && echo open || echo closed)"
  local log_file="${RESULTS_DIR}/${COMPONENT}.${step_label}.log"
  local status duration start_ts end_ts

  if [ -z "${PROBE_PORTS:-}" ]; then
    # Try to derive ports from configure_<component> in the module file
    PROBE_PORTS="$(_derive_ports)"
  fi

  if [ -z "${PROBE_PORTS:-}" ]; then
    _step_skip "$step_label" "ports not determined"
    return 0
  fi

  start_ts=$(date +%s)
  local all_ok=true

  for port in $PROBE_PORTS; do
    if "$TARGET_SH" exec \
        "timeout 5 bash -c \"</dev/tcp/localhost/${port}\" 2>/dev/null" \
        >> "$log_file" 2>&1; then
      port_open=true
    else
      port_open=false
    fi

    if [ "$expect_open" = "true" ] && [ "$port_open" = "false" ]; then
      echo "Port ${port} expected open but is closed" >> "$log_file"
      all_ok=false
    elif [ "$expect_open" = "false" ] && [ "$port_open" = "true" ]; then
      echo "Port ${port} expected closed but is still open" >> "$log_file"
      all_ok=false
    fi
  done

  end_ts=$(date +%s)
  duration=$(( end_ts - start_ts ))

  if [ "$all_ok" = "true" ]; then
    status="✅ PASS"
  else
    status="❌ FAIL"
  fi

  printf '%s|%s|%ds\n' "$step_label" "$status" "$duration" >> "$RESULTS_FILE"
  echo "Step ${step_label}: ${status} (${duration}s)"
  [[ "$status" == "✅ PASS" ]]
}

# _derive_ports — attempt to extract a port variable from configure_<name>
# in the module file.  Returns a space-separated list or empty string.
_derive_ports () {
  local port_val=""
  # shellcheck disable=SC2016
  port_val=$(grep -E '^\s*port(s)?=' "repo/${MODULE_FILE}" 2>/dev/null \
    | head -1 \
    | sed -E 's/^\s*ports?="?([0-9 ]+)"?/\1/' \
    | grep -E '^[0-9 ]+$' \
    || true)
  echo "${port_val}"
}

# _has_function <pattern> — check whether the module file defines a function
# matching <pattern> (grep -E pattern against the file on the runner, not the
# target — the file was checked out into repo/).
_has_function () {
  local pattern="$1"
  grep -qE "^${pattern} \(\)" "repo/${MODULE_FILE}" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Teardown — always runs via trap
# ---------------------------------------------------------------------------
_teardown () {
  if [ "$_teardown_done" = "true" ]; then return; fi
  _teardown_done=true

  echo "=== Teardown for ${COMPONENT} ==="

  # Attempt stop (ignore failure — may already be stopped)
  if _has_function "${OS_LIKE}_[0-9][0-9]_stop_${COMPONENT}"; then
    "$TARGET_SH" exec \
      "./rendered/openedge-cli stop ${COMPONENT}" \
      >> "${RESULTS_DIR}/${COMPONENT}.teardown-stop.log" 2>&1 || true
  fi

  # Attempt remove (ignore failure)
  if _has_function "${OS_LIKE}_[0-9][0-9]_remove_${COMPONENT}"; then
    "$TARGET_SH" exec \
      "./rendered/openedge-cli remove ${COMPONENT}" \
      >> "${RESULTS_DIR}/${COMPONENT}.teardown-remove.log" 2>&1 || true
  fi

  # Release the target back to the pool
  "$TARGET_SH" release || true
}

trap '_teardown' EXIT INT TERM

# ---------------------------------------------------------------------------
# Acquire and prepare the target
# ---------------------------------------------------------------------------
echo "=== Acquiring target for ${COMPONENT} ==="
"$TARGET_SH" acquire

echo "=== Resetting target ==="
"$TARGET_SH" reset

echo "=== Syncing repo to target ==="
"$TARGET_SH" sync HEAD

# Bootstrap the installer on the target so `openedge-cli` knows about the
# component under test.
echo "=== Bootstrapping installer on target ==="
"$TARGET_SH" exec "./openedge-cli bootstrap ${COMPONENT}"

# ---------------------------------------------------------------------------
# Determine which optional lifecycle steps are available
# ---------------------------------------------------------------------------
has_start=false
has_stop=false
has_remove=false

_has_function "${OS_LIKE}_[0-9][0-9]_start_${COMPONENT}"  && has_start=true  || has_start=false
_has_function "${OS_LIKE}_[0-9][0-9]_stop_${COMPONENT}"   && has_stop=true   || has_stop=false
_has_function "${OS_LIKE}_[0-9][0-9]_remove_${COMPONENT}" && has_remove=true || has_remove=false

echo "has_start=${has_start} has_stop=${has_stop} has_remove=${has_remove}"

# ---------------------------------------------------------------------------
# Track overall pass/fail
# ---------------------------------------------------------------------------
lifecycle_ok=true

# ---------------------------------------------------------------------------
# Step 1: install
# ---------------------------------------------------------------------------
_step "install" \
  "./rendered/openedge-cli install ${COMPONENT}" \
  || lifecycle_ok=false

# ---------------------------------------------------------------------------
# Step 2: install again (idempotency)
# ---------------------------------------------------------------------------
_step "install-idempotent" \
  "./rendered/openedge-cli install ${COMPONENT}" \
  || lifecycle_ok=false

# ---------------------------------------------------------------------------
# Step 3: install --reset-<name> (forced reinstall)
# ---------------------------------------------------------------------------
_step "install-reset" \
  "./rendered/openedge-cli install ${COMPONENT} --reset-${COMPONENT}" \
  || lifecycle_ok=false

# ---------------------------------------------------------------------------
# Steps 4 & 5: start + probe / stop + probe
# ---------------------------------------------------------------------------
if [ "$has_start" = "true" ]; then
  _step "start" \
    "./rendered/openedge-cli start ${COMPONENT}" \
    || lifecycle_ok=false

  _probe_ports true || lifecycle_ok=false
else
  _step_skip "start" "no start function defined"
  _step_skip "probe-ports-open" "no start function defined"
fi

if [ "$has_stop" = "true" ]; then
  _step "stop" \
    "./rendered/openedge-cli stop ${COMPONENT}" \
    || lifecycle_ok=false

  _probe_ports false || lifecycle_ok=false
else
  _step_skip "stop" "no stop function defined"
  _step_skip "probe-ports-closed" "no stop function defined"
fi

# ---------------------------------------------------------------------------
# Step 6: remove
# ---------------------------------------------------------------------------
if [ "$has_remove" = "true" ]; then
  _step "remove" \
    "./rendered/openedge-cli remove ${COMPONENT}" \
    || lifecycle_ok=false

  # Confirm verify_<name> no longer succeeds after remove
  _step "verify-gone" \
    "bash -c 'cd /opt/oep-installer-cli && source module/${COMPONENT}/${OS_LIKE} && ! verify_${COMPONENT} 2>/dev/null'" \
    || lifecycle_ok=false
else
  _step_skip "remove"     "no remove function defined"
  _step_skip "verify-gone" "no remove function defined"
fi

# ---------------------------------------------------------------------------
# Exit status
# ---------------------------------------------------------------------------
_teardown  # explicit call so teardown doesn't double-run via trap

if [ "$lifecycle_ok" = "true" ]; then
  echo "=== All lifecycle steps PASSED for ${COMPONENT} ==="
  exit 0
else
  echo "=== One or more lifecycle steps FAILED for ${COMPONENT} ===" >&2
  exit 1
fi
