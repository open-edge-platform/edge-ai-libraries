#!/usr/bin/env bash
# platform-target.sh — target lifecycle driver for platform validation
#
# Abstracts target host acquisition and reset behind a small interface so labs
# can plug in their own mechanism by setting TARGET_BACKEND.
#
# Interface (subcommands):
#   acquire          — pick a free target from the pool; exports TARGET_HOST
#   reset            — restore the target to a known-clean state
#   sync  <ref>      — copy the repo content at <ref> to the target
#   exec  <cmd...>   — run a command on the target, streaming stdout/stderr
#   release          — return the target to the pool
#
# Configuration (environment variables / repo vars / secrets):
#   TARGET_BACKEND    backend to use: "libvirt" (default) or "ssh"
#   TARGET_POOL       name / CSV list of available target hostnames or VM names
#                     default: oep-targets
#   TARGET_SNAPSHOT   libvirt snapshot name to revert to
#                     default: clean-baseline
#   TARGET_SSH_USER   SSH login user on the target
#                     default: oep
#   TARGET_SSH_KEY    path to (or content of) the private key for SSH
#                     default: ~/.ssh/id_rsa
#   TARGET_SSH_PORT   SSH port on the target
#                     default: 22
#   LIBVIRT_URI       libvirt connection URI
#                     default: qemu:///system
#   SYNC_DIR          path on the target where the repo is synced
#                     default: /opt/oep-installer-cli
#   SSH_TIMEOUT       seconds to wait for SSH to become available after reset
#                     default: 120
#
# Nothing lab-specific is hardcoded; all values come from the environment.
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration defaults
# ---------------------------------------------------------------------------
TARGET_BACKEND="${TARGET_BACKEND:-libvirt}"
TARGET_POOL="${TARGET_POOL:-oep-targets}"
TARGET_SNAPSHOT="${TARGET_SNAPSHOT:-clean-baseline}"
TARGET_SSH_USER="${TARGET_SSH_USER:-oep}"
TARGET_SSH_KEY="${TARGET_SSH_KEY:-${HOME}/.ssh/id_rsa}"
TARGET_SSH_PORT="${TARGET_SSH_PORT:-22}"
LIBVIRT_URI="${LIBVIRT_URI:-qemu:///system}"
SYNC_DIR="${SYNC_DIR:-/opt/oep-installer-cli}"
SSH_TIMEOUT="${SSH_TIMEOUT:-120}"

# Lock file directory for pool management
LOCK_DIR="${TMPDIR:-/tmp}/oep-target-locks"

# ---------------------------------------------------------------------------
# Shared SSH helper
# ---------------------------------------------------------------------------
OEP_TEMP_KEY=""

# _setup_key — populate SSH_KEY_ARGS array and OEP_TEMP_KEY
_setup_key () {
  SSH_KEY_ARGS=()
  if [[ "${TARGET_SSH_KEY}" == "-----BEGIN"* ]]; then
    OEP_TEMP_KEY="$(mktemp /tmp/oep-ssh-key.XXXXXX)"
    chmod 600 "${OEP_TEMP_KEY}"
    printf '%s\n' "${TARGET_SSH_KEY}" > "${OEP_TEMP_KEY}"
    SSH_KEY_ARGS=(-i "${OEP_TEMP_KEY}")
  elif [ -n "${TARGET_SSH_KEY}" ]; then
    SSH_KEY_ARGS=(-i "${TARGET_SSH_KEY}")
  fi
}

_ssh () {
  ssh \
    "${SSH_KEY_ARGS[@]}" \
    -p "${TARGET_SSH_PORT}" \
    -o StrictHostKeyChecking=no \
    -o BatchMode=yes \
    -o ConnectTimeout=10 \
    "${TARGET_SSH_USER}@${TARGET_HOST}" \
    "$@"
}

_cleanup_key () {
  if [ -n "${OEP_TEMP_KEY:-}" ] && [ -f "${OEP_TEMP_KEY}" ]; then
    rm -f "${OEP_TEMP_KEY}"
  fi
}
trap _cleanup_key EXIT

# Initialise key args immediately
# shellcheck disable=SC2034
SSH_KEY_ARGS=()
_setup_key

# ---------------------------------------------------------------------------
# Wait for SSH to become available
# ---------------------------------------------------------------------------
_wait_for_ssh () {
  local deadline=$(( $(date +%s) + SSH_TIMEOUT ))
  echo "Waiting up to ${SSH_TIMEOUT}s for SSH on ${TARGET_HOST}..."
  while true; do
    if _ssh true 2>/dev/null; then
      echo "SSH is ready on ${TARGET_HOST}"
      return 0
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
      echo "ERROR: SSH did not become available on ${TARGET_HOST} within ${SSH_TIMEOUT}s" >&2
      return 1
    fi
    sleep 5
  done
}

# ---------------------------------------------------------------------------
# Pool management — acquire / release via lock files
# ---------------------------------------------------------------------------
_acquire_from_pool () {
  mkdir -p "$LOCK_DIR"
  IFS=',' read -ra pool_hosts <<< "$TARGET_POOL"
  for host in "${pool_hosts[@]}"; do
    host="${host// /}"  # trim spaces
    local lockfile="${LOCK_DIR}/${host}.lock"
    # Use mkdir as an atomic lock
    if mkdir "${lockfile}" 2>/dev/null; then
      echo "$host"
      return 0
    fi
  done
  echo "ERROR: No free target available in pool: ${TARGET_POOL}" >&2
  return 1
}

_release_from_pool () {
  local host="$1"
  local lockfile="${LOCK_DIR}/${host}.lock"
  rm -rf "${lockfile}" 2>/dev/null || true
}

# ===========================================================================
# Shared sync and exec helpers (backend-agnostic)
# ===========================================================================

# _sync <ref> — copy the current working directory to SYNC_DIR on the target.
# ref is passed for informational purposes; actual content is whatever is in
# the working directory (already checked out by the workflow).
_sync () {
  local ref="${1:?sync requires a ref argument}"
  echo "Syncing repo (ref=${ref}) to ${TARGET_HOST}:${SYNC_DIR} ..."
  _ssh "mkdir -p '${SYNC_DIR}'"
  rsync -az --delete \
    -e "ssh ${SSH_KEY_ARGS[*]} -p ${TARGET_SSH_PORT} -o StrictHostKeyChecking=no -o BatchMode=yes" \
    ./ \
    "${TARGET_SSH_USER}@${TARGET_HOST}:${SYNC_DIR}/"
  echo "Sync complete"
}

# _exec <cmd...> — run a command on the target from within SYNC_DIR.
_exec () {
  echo "Running on ${TARGET_HOST}: $*"
  _ssh "cd '${SYNC_DIR}' && $*"
}

# ===========================================================================
# libvirt / KVM snapshot-revert backend
# ===========================================================================
libvirt_acquire () {
  local host
  host="$(_acquire_from_pool)"
  export TARGET_HOST="$host"
  echo "Acquired target VM: ${TARGET_HOST}"
}

libvirt_reset () {
  echo "Reverting ${TARGET_HOST} to snapshot '${TARGET_SNAPSHOT}' via libvirt..."
  virsh --connect "${LIBVIRT_URI}" snapshot-revert "${TARGET_HOST}" "${TARGET_SNAPSHOT}"
  # Start the domain in case the snapshot left it off
  virsh --connect "${LIBVIRT_URI}" start "${TARGET_HOST}" 2>/dev/null || true
  _wait_for_ssh
  echo "Reset complete for ${TARGET_HOST}"
}

libvirt_sync () {
  _sync "$@"
}

libvirt_exec () {
  _exec "$@"
}

libvirt_release () {
  echo "Releasing target VM: ${TARGET_HOST}"
  _release_from_pool "${TARGET_HOST}"
}

# ===========================================================================
# ssh (stub) backend — for bare-metal / PXE labs
#
# This backend assumes the host is already clean (externally re-imaged or
# configured).  It skips snapshot revert and simply waits for SSH.
# Set TARGET_POOL to the hostname(s) of your pre-cleaned bare-metal targets.
# ===========================================================================
ssh_acquire () {
  local host
  host="$(_acquire_from_pool)"
  export TARGET_HOST="$host"
  echo "Acquired bare-metal target: ${TARGET_HOST}"
}

ssh_reset () {
  # The host is assumed to have been re-imaged externally (PXE, BMC, etc.).
  # We simply wait for SSH to confirm it is reachable.
  echo "Waiting for bare-metal target ${TARGET_HOST} (assuming external reimaging has started)..."
  _wait_for_ssh
  echo "Reset complete for ${TARGET_HOST}"
}

ssh_sync () {
  _sync "$@"
}

ssh_exec () {
  _exec "$@"
}

ssh_release () {
  echo "Releasing bare-metal target: ${TARGET_HOST}"
  _release_from_pool "${TARGET_HOST}"
}

# ===========================================================================
# Dispatcher — select backend based on TARGET_BACKEND
# ===========================================================================
case "${TARGET_BACKEND}" in
  libvirt) BACKEND_PREFIX="libvirt" ;;
  ssh)     BACKEND_PREFIX="ssh" ;;
  *)
    echo "ERROR: Unknown TARGET_BACKEND '${TARGET_BACKEND}'. Valid values: libvirt, ssh" >&2
    exit 1
    ;;
esac

CMD="${1:?Usage: $0 <acquire|reset|sync|exec|release> [args...]}"
shift

case "$CMD" in
  acquire) "${BACKEND_PREFIX}_acquire" "$@" ;;
  reset)   "${BACKEND_PREFIX}_reset"   "$@" ;;
  sync)    "${BACKEND_PREFIX}_sync"    "$@" ;;
  exec)    "${BACKEND_PREFIX}_exec"    "$@" ;;
  release) "${BACKEND_PREFIX}_release" "$@" ;;
  *)
    echo "ERROR: Unknown command '${CMD}'. Valid commands: acquire reset sync exec release" >&2
    exit 1
    ;;
esac
