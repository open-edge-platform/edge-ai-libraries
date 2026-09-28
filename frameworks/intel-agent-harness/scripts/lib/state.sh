# shellcheck shell=bash
# State directory management — an owner-only, symlink-refusing state root
# under the user's home directory.

PLATFORM_STATE_DIRNAME="${PLATFORM_STATE_DIRNAME:-.intel-agent}"
# Host/IP advertised in printed endpoint URLs (OVMS, edge services, gateway
# routes). Defaults to loopback; Docker's -p already binds 0.0.0.0, so this
# only affects what gets displayed, not what's reachable. Captured before
# defaulting so resolve_advertised_host can tell "caller set it explicitly
# (even to 127.0.0.1)" apart from "never set" and let the former win over a
# persisted choice from a previous interactive prompt.
PLATFORM_ADVERTISED_HOST_WAS_SET="${PLATFORM_ADVERTISED_HOST+1}"
PLATFORM_ADVERTISED_HOST="${PLATFORM_ADVERTISED_HOST:-127.0.0.1}"

platform_state_root() {
  printf '%s/%s' "$HOME" "$PLATFORM_STATE_DIRNAME"
}

# Refuses any path outside the state root, or one with a symlink component.
assert_state_path_safe() {
  local target="$1" root current relative component
  root="$(platform_state_root)"
  case "$target" in
    "$root" | "$root"/*) ;;
    *) error "Refusing state path outside ${root}: ${target}" ;;
  esac
  current="$root"
  relative="${target#"$root"}"
  relative="${relative#/}"
  while [[ -n "$relative" ]]; do
    component="${relative%%/*}"
    current="${current}/${component}"
    [[ -L "$current" ]] && error "Refusing symlink in state path: ${current}"
    [[ "$relative" == "$component" ]] && break
    relative="${relative#*/}"
  done
}

ensure_state_dir() {
  local root
  root="$(platform_state_root)"
  assert_state_path_safe "$root"
  (umask 077 && mkdir -p "$root")
  chmod 700 "$root"
  assert_owned_by_current_user "$root"
  printf '%s' "$root"
}

# Refuses to trust a path whose owner isn't the current user — guards
# against another local account planting a file we'd otherwise read/replace.
assert_owned_by_current_user() {
  local target="$1" owner
  [[ -e "$target" || -L "$target" ]] || return 0
  owner="$(stat -c '%u' "$target" 2>/dev/null || stat -f '%u' "$target" 2>/dev/null || true)"
  [[ -n "$owner" && "$owner" == "$(id -u)" ]] \
    || error "Refusing to trust ${target}: not owned by the current user."
}

# Serializes read-modify-write sequences (e.g. registry updates) across
# concurrent installer invocations. Best-effort no-op if flock is unavailable.
with_state_lock() {
  local lock_name="$1"
  shift
  if ! command_exists flock; then
    "$@"
    return
  fi
  local lock_file
  lock_file="$(ensure_state_dir)/.${lock_name}.lock"
  (
    flock -w 30 200 || error "Could not acquire lock '${lock_name}' within 30s."
    "$@"
  ) 200>"$lock_file"
}

# Atomic write via mktemp+rename (same-filesystem rename is POSIX-atomic).
# Uses Node's O_NOFOLLOW when available for stronger symlink-swap protection.
# Re-verifies the result so a symlink-swap race during the write is caught.
atomic_write_file() {
  local path="$1" content="$2" tmp
  assert_state_path_safe "$path"
  if command_exists node; then
    node -e '
      const fs = require("node:fs");
      const path = process.argv[1];
      const content = fs.readFileSync(0, "utf8");
      const fd = fs.openSync(path, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_TRUNC | fs.constants.O_NOFOLLOW, 0o600);
      fs.writeFileSync(fd, content);
      fs.closeSync(fd);
    ' "$path" <<<"$content" || error "Could not write ${path}"
  else
    tmp="$(mktemp "${path}.tmp.XXXXXX")"
    chmod 600 "$tmp"
    printf '%s' "$content" >"$tmp"
    mv -f "$tmp" "$path"
  fi
  assert_state_path_safe "$path"
  assert_owned_by_current_user "$path"
}

# Reads a top-level string field from a small JSON file (falls back to sed
# when Node isn't installed yet, e.g. before the Node.js bootstrap step).
# Applies the strict state-path checks only to files actually under the
# state root; other callers (e.g. the repo-local notice.json) just get a
# symlink refusal, since they aren't part of the trusted state tree.
read_json_field() {
  local file="$1" field="$2" root
  [[ -f "$file" ]] || return 1
  root="$(platform_state_root)"
  case "$file" in
    "$root" | "$root"/*)
      assert_state_path_safe "$file"
      assert_owned_by_current_user "$file"
      ;;
    *)
      [[ ! -L "$file" ]] || error "Refusing to read symlinked file: ${file}"
      ;;
  esac
  if command_exists node; then
    node -e '
      try {
        const data = JSON.parse(require("node:fs").readFileSync(process.argv[1], "utf8"));
        const v = data[process.argv[2]];
        if (v !== undefined) process.stdout.write(String(v));
      } catch {}
    ' "$file" "$field"
  else
    sed -nE "s/^[[:space:]]*\"${field}\"[[:space:]]*:[[:space:]]*\"?([^\",}]*)\"?,?[[:space:]]*\$/\1/p" "$file" | head -1
  fi
}

platform_advertised_host_file() {
  printf '%s/advertised-host' "$(ensure_state_dir)"
}

# resolve_advertised_host — an explicit PLATFORM_ADVERTISED_HOST env var
# always wins (even if explicitly set to 127.0.0.1); otherwise falls back to
# a host previously chosen at the install prompt (persist_advertised_host),
# then loopback. Deliberately does not create the state dir on a pure read —
# callers like print_status are documented read-only and must not create
# ~/.intel-agent as a side effect of just checking status.
resolve_advertised_host() {
  local file
  if [[ -n "$PLATFORM_ADVERTISED_HOST_WAS_SET" || "$PLATFORM_ADVERTISED_HOST" != "127.0.0.1" ]]; then
    printf '%s' "$PLATFORM_ADVERTISED_HOST"
    return 0
  fi
  file="$(platform_state_root)/advertised-host"
  if [[ -f "$file" ]]; then
    assert_state_path_safe "$file"
    assert_owned_by_current_user "$file"
    tr -d '[:space:]' <"$file"
    return 0
  fi
  printf '127.0.0.1'
}

persist_advertised_host() {
  atomic_write_file "$(platform_advertised_host_file)" "$1"
}
